"""
deployer.py — Deploy fetched scripts, configs, and patched templates.

Handles:
  - Backing up existing config
  - Copying fetched scripts from staging to mpv config dir
  - Copying user's personal configs (script-opts, input.conf)
  - Patching template files (mpv.conf, autosubsync.conf)
  - Line ending normalization (CRLF→LF on Linux)
  - Creating required directories (shader_cache)
"""

import json
import os
import re
import shutil
from datetime import datetime

from deploy import ui
from deploy.registry import (
    MPV_EXPERIENCE_PROFILES,
    MPV_PROFILE_DEFAULT,
    PLATFORM_NATIVE_MPV_DEFAULTS,
    PLATFORM_REQUIRED_DEFAULTS,
)

LINUX_VISUAL_TUNING_BLOCK = (
    "# 1. إعدادات الواجهة (OSD) لرسائل النظام الديناميكية\n"
    "osd-font=\"Tahoma\"\n"
    "osd-font-size=50\n"
    "osd-scale-by-window=yes\n"
    "\n"
    "# 2. إعدادات الترجمة (SRT) الديناميكية (مريحة للعين)\n"
    "sub-font-provider=fontconfig\n"
    "sub-font=\"Tahoma\"\n"
    "sub-font-size=36\n"
    "sub-scale-by-window=yes\n"
    "sub-color=\"#FFFFFF\"\n"
    "sub-border-color=\"#000000\"\n"
    "sub-border-size=2\n"
    "sub-shadow-offset=1\n"
    "sub-margin-y=36\n"
    "\n"
    "# 3. Window Sizing Helpers (Convenience)\n"
    "geometry=50%x50%\n"
    "autofit-larger=90%x90%\n"
    "autofit-smaller=30%x30%\n"
)


# ─── Backup ────────────────────────────────────────────────────────────

def backup_existing(config_dir, audit_log=None):
    """
    If config_dir exists, back it up with a timestamp.

    Parameters
    ----------
    audit_log:
        Optional :class:`~deploy.audit_log.AuditLog`.  When supplied the
        created backup path is recorded in the active session.

    Returns backup path or None.
    """
    if not os.path.isdir(config_dir):
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"{config_dir}.backup.{timestamp}"

    ui.step(f"Backing up existing config → {backup_dir}")
    try:
        shutil.copytree(config_dir, backup_dir, symlinks=False, ignore=shutil.ignore_patterns(".git"))
        ui.success(f"Backup created: {backup_dir}")
        if audit_log:
            audit_log.record_backup(backup_dir)
            audit_log.record_file(config_dir, "backup", "ok", f"backed up to {backup_dir}", backup_path=backup_dir)
        return backup_dir
    except Exception as e:
        ui.error(f"Backup failed: {e}")
        if audit_log:
            audit_log.record_file(config_dir, "backup", "failed", str(e))
        raise


def list_backups(config_dir):
    """Return available backup directories for config_dir (newest first)."""
    parent = os.path.dirname(config_dir) or "."
    base = os.path.basename(config_dir)
    prefix = f"{base}.backup."

    backups = []
    if not os.path.isdir(parent):
        return backups

    for name in os.listdir(parent):
        if not name.startswith(prefix):
            continue
        full_path = os.path.join(parent, name)
        if os.path.isdir(full_path):
            backups.append(full_path)

    backups.sort(key=_safe_mtime, reverse=True)
    return backups


def _remove_path(path):
    """Remove file/dir/symlink path safely."""
    if os.path.islink(path) or os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)


def _safe_mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return float("-inf")


def rollback_config(config_dir, backup_path=None, dry_run=False, audit_log=None):
    """
    Restore config_dir from a backup.

    If backup_path is None, restores from the latest available backup.

    Parameters
    ----------
    audit_log:
        Optional :class:`~deploy.audit_log.AuditLog`.  When supplied the
        rollback operation (source, outcome) is recorded in the active session.
    """
    backup_source = backup_path
    if backup_source:
        backup_source = os.path.abspath(os.path.expanduser(backup_source))
    else:
        backups = list_backups(config_dir)
        if not backups:
            raise FileNotFoundError(f"No backups found for: {config_dir}")
        backup_source = backups[0]

    if not os.path.isdir(backup_source):
        raise FileNotFoundError(f"Backup not found: {backup_source}")

    if dry_run:
        ui.info(f"[DRY RUN] Would rollback {config_dir} from {backup_source}")
        if audit_log:
            audit_log.record_file(config_dir, "backup", "skipped", f"dry run — would restore from {backup_source}")
        return {
            "name": "rollback",
            "status": "skipped",
            "detail": f"dry run ({backup_source})",
        }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_restore = f"{config_dir}.rollback.tmp.{timestamp}"
    safety_backup = None

    try:
        ui.step(f"Preparing rollback from: {backup_source}")
        shutil.copytree(backup_source, temp_restore, ignore=shutil.ignore_patterns(".git"))

        if os.path.isdir(config_dir):
            safety_backup = f"{config_dir}.pre-rollback.{timestamp}"
            ui.step(f"Saving current config → {safety_backup}")
            shutil.copytree(config_dir, safety_backup, ignore=shutil.ignore_patterns(".git"))
            # Remove old config — skip .git, force-clear attributes on Windows
            import stat
            import time

            def _on_rm_error(func, path, exc_info):
                """Clear read-only/hidden/system flags and retry."""
                os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
                func(path)

            for attempt in range(3):
                try:
                    # Remove everything except .git
                    for item in os.listdir(config_dir):
                        if item == ".git":
                            continue
                        item_path = os.path.join(config_dir, item)
                        if os.path.isdir(item_path) and not os.path.islink(item_path):
                            shutil.rmtree(item_path, onerror=_on_rm_error)
                        else:
                            try:
                                os.remove(item_path)
                            except PermissionError:
                                os.chmod(item_path, stat.S_IWRITE)
                                os.remove(item_path)
                    break
                except PermissionError:
                    if attempt < 2:
                        ui.warn(f"Files locked, retrying in 2s... (attempt {attempt + 1}/3)")
                        time.sleep(2)
                    else:
                        raise

        # Move restored files into config_dir (which still exists with .git)
        for item in os.listdir(temp_restore):
            src = os.path.join(temp_restore, item)
            dst = os.path.join(config_dir, item)
            if os.path.exists(dst):
                _remove_path(dst)
            shutil.move(src, dst)
        _remove_path(temp_restore)
        
        # Clean up any leftover symlinks pointing to 'deployed'
        try:
            for item in os.listdir(config_dir):
                p = os.path.join(config_dir, item)
                if os.path.islink(p):
                    target = os.readlink(p)
                    if "deployed" in target:
                        os.unlink(p)
        except Exception as e:
            ui.warn(f"Failed to clean up remaining symlinks: {e}")
            
        ui.success(f"Rollback completed from: {backup_source}")
        if safety_backup:
            ui.success(f"Current config saved as: {safety_backup}")

        if audit_log:
            audit_log.record_file(
                config_dir, "backup", "ok",
                f"restored from {backup_source}",
                backup_path=safety_backup,
            )

        return {
            "name": "rollback",
            "status": "ok",
            "detail": backup_source,
        }
    except Exception as e:
        ui.error(f"Rollback failed: {e}")
        if audit_log:
            audit_log.record_file(config_dir, "backup", "failed", str(e))
        if os.path.isdir(temp_restore):
            try:
                _remove_path(temp_restore)
            except Exception as cleanup_err:
                ui.warn(f"Could not clean temporary rollback directory: {cleanup_err}")
        if safety_backup and os.path.isdir(safety_backup):
            ui.info(f"Restoring previous config from: {safety_backup}")
            if os.path.lexists(config_dir):
                _remove_path(config_dir)
            shutil.move(safety_backup, config_dir)
        raise


# ─── Template Patching ─────────────────────────────────────────────────

def _resolve_mpv_profile(env, mpv_profile):
    """Resolve selected profile into effective mpv behavior defaults."""
    selected_profile = mpv_profile or MPV_PROFILE_DEFAULT
    fallback_profile = MPV_EXPERIENCE_PROFILES.get(MPV_PROFILE_DEFAULT, {})
    if selected_profile == "native":
        defaults = dict(PLATFORM_NATIVE_MPV_DEFAULTS.get(env.platform_key, {}))
    else:
        defaults = dict(MPV_EXPERIENCE_PROFILES.get(selected_profile, fallback_profile))

    return selected_profile, defaults


def _patch_mpv_conf(
    template_path,
    dest_path,
    env,
    selected_profile,
    resolved_defaults,
):
    """Patch mpv.conf.template with profile-aware + platform-required values."""
    linux_visual_tuning = LINUX_VISUAL_TUNING_BLOCK if env.os == "linux" else ""

    # Platform-conditional: border=no on Windows (clean borderless), yes on Linux (KDE needs it)
    border_value = "no" if env.os == "windows" else "yes"
    # native-fs=no only on Linux (prevents KDE compositor desync); omitted on Windows
    native_fs_value = "no" if env.os == "linux" else ""

    defaults = resolved_defaults
    required = PLATFORM_REQUIRED_DEFAULTS.get(env.platform_key, {})

    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    shader_sep = required.get("shader_sep", ";")

    replacements = {
        "{{GPU_API}}": defaults.get("gpu_api", "auto"),
        "{{HWDEC}}": defaults.get("hwdec", "auto"),
        "{{VO}}": defaults.get("vo", "gpu-next"),
        "{{SHADER_SEP}}": shader_sep,
        "{{LINUX_VISUAL_TUNING}}": linux_visual_tuning,
        "{{BORDER}}": border_value,
        "{{NATIVE_FS}}": native_fs_value,
    }

    # GPU context: detect wayland vs x11 when profile requests automatic context.
    gpu_context = defaults.get("gpu_context", "")
    base_hwdec = defaults.get("hwdec", "auto")
    hwdec = base_hwdec

    if gpu_context == "auto":
        if env.display == "wayland":
            gpu_context = "waylandvk"
        elif env.display == "x11":
            gpu_context = "x11vk"
        else:
            gpu_context = ""

    # Keep legacy vendor-specific Linux hwdec optimization in native mode.
    # Also avoid copy-path overhead on Linux/NVIDIA in default profile.
    if selected_profile == "native":
        if env.gpu_vendor == "nvidia" and env.os == "linux":
            hwdec = "nvdec"
        elif env.gpu_vendor == "amd" and env.os == "linux":
            hwdec = "vaapi"
        elif env.gpu_vendor == "intel" and env.os == "linux":
            hwdec = "vaapi"
    elif selected_profile == "windows-like":
        if env.gpu_vendor == "nvidia" and env.os == "linux" and base_hwdec in {"auto", "auto-copy", "auto-safe"}:
            hwdec = "nvdec"

    replacements["{{HWDEC}}"] = hwdec
    replacements["{{GPU_CONTEXT}}"] = gpu_context

    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)

    # Handle conditional blocks: {{#if BLOCK}}...{{/if}}
    for block_name, block_value in [("GPU_CONTEXT", gpu_context), ("NATIVE_FS", native_fs_value)]:
        if not block_value:
            content = re.sub(
                r'\{\{#if ' + block_name + r'\}\}.*?\{\{/if\}\}\n?',
                '', content, flags=re.DOTALL
            )
        else:
            content = content.replace("{{#if " + block_name + "}}", "")
            # Only remove the {{/if}} that follows this block
            content = content.replace("{{/if}}", "", 1)

    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(content)


def _patch_autosubsync_conf(template_path, dest_path, env):
    """Patch autosubsync.conf.template with platform-specific paths."""
    defaults = PLATFORM_REQUIRED_DEFAULTS.get(env.platform_key, {})

    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    # For 'auto' values on Windows, try to find actual paths
    ffmpeg_path = defaults.get("ffmpeg_path", "ffmpeg")
    ffsubsync_path = defaults.get("ffsubsync_path", "ffsubsync")
    alass_path = defaults.get("alass_path", "alass")

    if ffmpeg_path == "auto":
        ffmpeg_path = _find_binary("ffmpeg", env) or "ffmpeg"
    if ffsubsync_path in ("auto", "ffsubsync"):
        ffsubsync_path = _find_binary("ffsubsync", env) or "ffsubsync"
    if alass_path in ("auto", "alass", "alass-cli"):
        if alass_path == "alass-cli":
            alass_path = _find_binary("alass-cli", env) or _find_binary("alass", env) or "alass-cli"
        else:
            alass_path = _find_binary("alass", env) or _find_binary("alass-cli", env) or "alass"

    content = content.replace("{{FFMPEG_PATH}}", ffmpeg_path)
    content = content.replace("{{FFSUBSYNC_PATH}}", ffsubsync_path)
    content = content.replace("{{ALASS_PATH}}", alass_path)

    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(content)


def _patch_input_conf(template_path, dest_path, env):
    """Patch input.conf.template — replace shader separator placeholder."""
    defaults = PLATFORM_REQUIRED_DEFAULTS.get(env.platform_key, {})
    shader_sep = defaults.get("shader_sep", ";")

    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.replace("{{SHADER_SEP}}", shader_sep)

    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(content)


def _find_binary(name, env):
    """Try to find the full path of a binary."""
    import shutil as sh
    path = sh.which(name)
    if path:
        if env.os == "windows":
            return path.replace("\\", "/")
        return path
    return None


# ─── Line Endings ──────────────────────────────────────────────────────

def _normalize_line_endings(directory, env):
    """Convert CRLF → LF on non-Windows systems."""
    if env.os == "windows":
        return

    count = 0
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
        for fname in files:
            if fname.endswith((".lua", ".conf", ".py", ".sh", ".glsl")):
                fpath = os.path.join(root, fname)
                if os.path.islink(fpath):
                    continue
                try:
                    with open(fpath, "rb") as f:
                        data = f.read()
                    if b"\r\n" in data:
                        data = data.replace(b"\r\n", b"\n")
                        with open(fpath, "wb") as f:
                            f.write(data)
                        count += 1
                except Exception:
                    pass

    if count > 0:
        ui.success(f"Normalized line endings for {count} file(s)")


# ─── Deploy Directory (Symlink/Copy) ───────────────────────────────────

def _is_symlink_safe(dst):
    """
    Check if target exists:
    if symlink pointing elsewhere -> safe to replace (return True)
    if real directory -> needs backup first (return False)
    if file -> raise error (unexpected state)
    if not exists -> safe (return True)
    """
    if not os.path.exists(dst) and not os.path.islink(dst):
        return True
    if os.path.islink(dst):
        return True
    if os.path.isdir(dst):
        return False
    raise RuntimeError(f"Unexpected file at target: {dst}")

def _deploy_directory(src, dst, env, audit_log=None):
    """
    Deploy a directory using symlinks on Linux/macOS and copytree on Windows.
    src must be an absolute path to the deployed staging folder (e.g. <config_dir>/deployed/scripts).
    dst is the target link/folder (e.g. <config_dir>/scripts).
    """
    if env.os in ("linux", "macos"):
        # OS-conditional: Symlink
        if not _is_symlink_safe(dst):
            # Target is a real dir, remove it since we already backed up the config
            shutil.rmtree(dst)
        elif os.path.islink(dst):
            os.unlink(dst)
        
        os.symlink(src, dst)
        method = "symlink"
    else:
        # Windows: Copy
        if os.path.exists(dst) or os.path.islink(dst):
            _remove_path(dst)
        shutil.copytree(src, dst)
        method = "copy"
        
    count = sum(len(files) for _, _, files in os.walk(src))
    if audit_log:
        audit_log.record_file(dst, method, "ok", f"{count} file(s) deployed via {method}")
    return count, method


# ─── Main Deploy ───────────────────────────────────────────────────────

def deploy(staging_dir, env, repo_dir, dry_run=False, audit_log=None, mpv_profile=MPV_PROFILE_DEFAULT):
    """
    Deploy everything from staging_dir + repo_dir/config/ to env.config_dir.

    staging_dir: contains fetched scripts/shaders
    repo_dir: the root of this repo (contains config/)
    env: Environment object
    audit_log: Optional AuditLog instance to record file operations.
    """
    config_dir = env.config_dir

    ui.header("Deploying Configuration")

    if dry_run:
        ui.info(f"[DRY RUN] Would deploy to: {config_dir}")
        return [{"name": "deploy", "status": "skipped", "detail": "dry run"}]

    results = []

    # 1. Backup existing
    try:
        backup = backup_existing(config_dir, audit_log=audit_log)
        if backup:
            results.append({"name": "backup", "status": "ok", "detail": backup})
    except Exception as e:
        results.append({"name": "backup", "status": "failed", "detail": str(e)})
        return results  # Can't continue without backup

    # 2. Create config dir
    os.makedirs(config_dir, exist_ok=True)

    # 3. Move staging to persistent deployed/ dir
    deployed_dir = os.path.join(config_dir, "deployed")
    if os.path.exists(deployed_dir):
        shutil.rmtree(deployed_dir)
    # The caller manages staging_dir, so we copy it to deployed_dir
    shutil.copytree(staging_dir, deployed_dir, symlinks=False)

    ui.step("Deploying scripts & shaders...")
    for item in ("scripts", "shaders", "fonts"):
        src = os.path.join(deployed_dir, item)
        dst = os.path.join(config_dir, item)
        if os.path.isdir(src):
            count, method = _deploy_directory(src, dst, env, audit_log)
            ui.success(f"{item}/: {count} file(s) deployed via {method}")
            results.append({"name": item, "status": "ok", "detail": f"{count} files via {method}"})

    # 4. Copy config files from repo
    config_src = os.path.join(repo_dir, "config")
    if os.path.isdir(config_src):

        # script-opts (static configs)
        opts_src = os.path.join(config_src, "script-opts")
        opts_dst = os.path.join(config_dir, "script-opts")
        os.makedirs(opts_dst, exist_ok=True)
        if os.path.isdir(opts_src):
            for fname in os.listdir(opts_src):
                src_path = os.path.join(opts_src, fname)
                if fname.endswith(".template"):
                    continue  # templates handled separately
                if os.path.isfile(src_path):
                    shutil.copy2(src_path, os.path.join(opts_dst, fname))
            ui.success("script-opts/ deployed")
            results.append({"name": "script-opts", "status": "ok"})
            if audit_log:
                audit_log.record_file(opts_dst, "copy", "ok", "script-opts deployed")

        # 5. Patch templates
        ui.step("Patching platform-specific configs...")

        # mpv.conf
        mpv_template = os.path.join(config_src, "mpv.conf.template")
        if os.path.isfile(mpv_template):
            dest = os.path.join(config_dir, "mpv.conf")
            selected_profile, resolved_defaults = _resolve_mpv_profile(env, mpv_profile)
            _patch_mpv_conf(
                mpv_template,
                dest,
                env,
                selected_profile=selected_profile,
                resolved_defaults=resolved_defaults,
            )
            sep = PLATFORM_REQUIRED_DEFAULTS[env.platform_key]["shader_sep"]
            resolved_gpu_api = resolved_defaults.get("gpu_api", "auto")
            ui.success(
                f"mpv.conf patched & deployed (profile={selected_profile}, gpu-api={resolved_gpu_api}, shader-sep='{sep}')"
            )
            results.append(
                {"name": "mpv.conf", "status": "ok", "detail": f"profile={selected_profile}, gpu-api={resolved_gpu_api}"}
            )
            if audit_log:
                audit_log.record_file(dest, "modify", "ok", "patched from template")

        # input.conf
        input_template = os.path.join(config_src, "input.conf.template")
        if os.path.isfile(input_template):
            dest = os.path.join(config_dir, "input.conf")
            _patch_input_conf(input_template, dest, env)
            ui.success("input.conf patched & deployed")
            results.append({"name": "input.conf", "status": "ok"})
            if audit_log:
                audit_log.record_file(dest, "modify", "ok", "patched from template")

        # autosubsync.conf
        ass_template = os.path.join(opts_src, "autosubsync.conf.template")
        if os.path.isfile(ass_template):
            dest = os.path.join(opts_dst, "autosubsync.conf")
            _patch_autosubsync_conf(ass_template, dest, env)
            ui.success("autosubsync.conf patched & deployed")
            results.append({"name": "autosubsync.conf", "status": "ok"})
            if audit_log:
                audit_log.record_file(dest, "modify", "ok", "patched from template")

    # 6. Create required directories
    for d in ("shader_cache", "chapters"):
        os.makedirs(os.path.join(config_dir, d), exist_ok=True)
    ui.success("Created shader_cache/ and chapters/")

    # 7. Normalize line endings
    _normalize_line_endings(config_dir, env)

    return results
