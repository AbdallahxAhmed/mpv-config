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
import uuid
from datetime import datetime

from deploy import ui
from deploy.registry import (
    ANIME4K_CHAINS,
    MPV_EXPERIENCE_PROFILES,
    MPV_PROFILE_DEFAULT,
    PLATFORM_NATIVE_MPV_DEFAULTS,
    PLATFORM_REQUIRED_DEFAULTS,
    SCALER_TIERS,
    SYSTEM_DEPS,
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


CONDITIONAL_BLOCK_PATTERN = re.compile(r'\{\{#if (\w+)\}\}(.*?)\{\{/if\}\}\n*', flags=re.DOTALL)


def _process_conditionals(content, blocks):
    """Process {{#if NAME}}...{{/if}} blocks atomically per named block."""
    return CONDITIONAL_BLOCK_PATTERN.sub(lambda m: m.group(2) if blocks.get(m.group(1)) else "", content)


def _resolve_screenshot_dir(env):
    if env.os == "windows":
        userprofile = os.environ.get("USERPROFILE", "")
        return f"{userprofile}/Pictures/mpv-screenshots".replace("\\", "/")
    return "~/Pictures/mpv-screenshots"


def _resolve_anime_chain(preset, shader_sep):
    chain = ANIME4K_CHAINS.get(preset, ANIME4K_CHAINS["A"])
    if not chain:
        return ""
    parts = [name.strip() for name in chain.split(";") if name.strip()]
    return shader_sep.join(f"~~/shaders/{name}.glsl" for name in parts)


def _resolve_scaler_tier(tier):
    return SCALER_TIERS.get(tier, SCALER_TIERS["balanced"])


def _resolve_display_mode(mode):
    if mode == "vrr":
        return {
            "video_sync": "audio",
            "interpolation": "no",
            "d3d11_flip": "no",
        }
    return {
        "video_sync": "display-resample",
        "interpolation": "yes",
        "d3d11_flip": "yes",
    }


BPP_10BIT = 30
BPP_8BIT_MIN = 1


def _detect_dither_depth(env):
    # CurrentBitsPerPixel reflects packed framebuffer format, not reliable
    # per-channel output depth; keep mpv default auto-selection.
    return None


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

    config_dir = os.path.abspath(os.path.expanduser(config_dir))
    backup_source = os.path.abspath(os.path.expanduser(backup_source))
    if backup_source == config_dir or backup_source.startswith(config_dir + os.sep):
        raise ValueError("Backup path cannot be inside config directory")
    if config_dir.startswith(backup_source + os.sep):
        raise ValueError("Config directory cannot be nested inside backup path")

    unique = uuid.uuid4().hex
    temp_restore = f"{config_dir}.rollback.tmp.{unique}"
    safety_backup = None

    try:
        ui.step(f"Preparing rollback from: {backup_source}")
        shutil.copytree(backup_source, temp_restore, ignore=shutil.ignore_patterns(".git"))

        if os.path.isdir(config_dir):
            safety_backup = f"{config_dir}.pre-rollback.{unique}"
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

        if not os.path.isdir(config_dir):
            os.makedirs(config_dir, exist_ok=True)

        # Move restored files into config_dir (which still exists with .git)
        try:
            same_drive = os.stat(temp_restore).st_dev == os.stat(config_dir).st_dev
        except OSError:
            drive_temp = os.path.splitdrive(temp_restore)[0]
            drive_config = os.path.splitdrive(config_dir)[0]
            same_drive = bool(drive_temp) and drive_temp.lower() == drive_config.lower()
        for item in os.listdir(temp_restore):
            src = os.path.join(temp_restore, item)
            dst = os.path.join(config_dir, item)
            if os.path.exists(dst):
                _remove_path(dst)
            if same_drive:
                shutil.move(src, dst)
            else:
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
        _remove_path(temp_restore)
            
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
            os.makedirs(config_dir, exist_ok=True)
            for item in os.listdir(config_dir):
                if item == ".git":
                    continue
                _remove_path(os.path.join(config_dir, item))
            for item in os.listdir(safety_backup):
                src = os.path.join(safety_backup, item)
                dst = os.path.join(config_dir, item)
                if os.path.exists(dst):
                    _remove_path(dst)
                shutil.move(src, dst)
            _remove_path(safety_backup)
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
        if selected_profile == "windows-like" and env.os != "windows":
            linux_fallback = MPV_EXPERIENCE_PROFILES.get("linux-like", {})
            defaults.update(linux_fallback)

    return selected_profile, defaults


def _detect_display_fps(env):
    """Detect the actual display refresh rate to avoid hardcoded fallbacks."""
    import subprocess
    import re
    try:
        if env.os == "windows":
            cmd = ["powershell", "-NoProfile", "-Command", "(Get-CimInstance -ClassName Win32_VideoController).CurrentRefreshRate / 1.0"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip():
                try:
                    fps_val = float(res.stdout.strip())
                    if fps_val > 0:
                        fps_int = int(round(fps_val))
                        exact_map = {
                            144: "143.981",
                            120: "119.880",
                            60:  "59.940",
                            165: "164.999",
                            240: "239.760"
                        }
                        return exact_map.get(fps_int, f"{fps_val:.3f}")
                except ValueError:
                    pass
        elif env.os == "linux":
            # Try xrandr first (works for X11 and XWayland wrappers)
            try:
                res = subprocess.run(["xrandr", "--current"], capture_output=True, text=True, timeout=2)
                if res.returncode == 0:
                    # Look for the current mode marked with '*' (e.g. "  1920x1080 (0x46) 144.000Hz *+")
                    # Sometimes it's just "   60.00*+" or similar.
                    # We'll just look for a number before an asterisk
                    match = re.search(r'\b(\d+(?:\.\d+)?)(?:\s*\*|\*)', res.stdout)
                    if match:
                        return match.group(1)
            except Exception:
                pass
            
            # Fallback to kscreen-doctor for KDE Wayland natively
            try:
                res = subprocess.run(["kscreen-doctor", "-o"], capture_output=True, text=True, timeout=2)
                if res.returncode == 0:
                    # Looks for something like "1920x1080@143" or "2560x1440@60"
                    match = re.search(r'@(\d+(?:\.\d+)?)', res.stdout)
                    if match:
                        return match.group(1)
            except Exception:
                pass
    except Exception:
        pass
    
    return None


def _patch_mpv_conf(
    template_path,
    dest_path,
    env,
    selected_profile,
    resolved_defaults,
    anime_preset="A",
    scaler_tier="balanced",
    display_mode="fixed",
    dither_depth="auto",
    audit_log=None,
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
    anime_chain = _resolve_anime_chain(anime_preset, shader_sep)
    scalers = _resolve_scaler_tier(scaler_tier)
    display_settings = _resolve_display_mode(display_mode)
    screenshot_dir = _resolve_screenshot_dir(env)

    dither_value = dither_depth
    if dither_depth == "auto":
        dither_value = _detect_dither_depth(env) or "auto"

    if audit_log:
        display_fps = _detect_display_fps(env)
        detail = display_fps or "unknown"
        audit_log.record_note("display_fps_detected", f"detected_display_fps={detail}")
        if display_mode == "auto":
            audit_log.record_note("display_mode", "auto → fixed (vrr requires explicit --display-mode vrr)")

    replacements = {
        "{{GPU_API}}": defaults.get("gpu_api", "auto"),
        "{{HWDEC}}": defaults.get("hwdec", "auto"),
        "{{VO}}": defaults.get("vo", "gpu-next"),
        "{{SHADER_SEP}}": shader_sep,
        "{{LINUX_VISUAL_TUNING}}": linux_visual_tuning,
        "{{BORDER}}": border_value,
        "{{NATIVE_FS}}": native_fs_value,
        "{{SCREENSHOT_DIR}}": screenshot_dir,
        "{{ANIME_CHAIN}}": anime_chain,
        "{{SCALE}}": scalers["scale"],
        "{{CSCALE}}": scalers["cscale"],
        "{{DSCALE}}": scalers["dscale"],
        "{{D3D11_FLIP}}": display_settings["d3d11_flip"],
        "{{VIDEO_SYNC}}": display_settings["video_sync"],
        "{{INTERPOLATION}}": display_settings["interpolation"],
        "{{DITHER_DEPTH}}": str(dither_value),
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
        # On Windows, "native" resolves to an empty profile; never let hwdec
        # fall back to "auto" (which can select a -copy path and double the
        # frame-delivery time). Pin zero-copy d3d11va to match the validated
        # Windows/NVIDIA pipeline (1.4ms vs 5.3ms avg frame time).
        if env.os == "windows" and base_hwdec in {"", "auto", "auto-copy", "auto-safe"}:
            hwdec = "d3d11va"
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
    content = _process_conditionals(content, {
        "GPU_CONTEXT": gpu_context,
        "NATIVE_FS": native_fs_value,
    })

    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(content)


def ensure_mpv_conf_user(config_dir, audit_log=None):
    """Create an empty mpv.conf.user if absent so the template's trailing
    `include = "~~/mpv.conf.user"` never dangles on a fresh install.
    NEVER overwrites — existing user tweaks are the whole point of the file.
    Sanitizes any accidental recursive self-includes (e.g. include = "~~/mpv.conf.user")."""
    user_path = os.path.join(config_dir, "mpv.conf.user")
    if not os.path.exists(user_path):
        with open(user_path, "w", encoding="utf-8") as f:
            f.write("# mpv.conf.user — personal overrides.\n"
                    "# Loaded LAST by mpv.conf; values here always win.\n"
                    "# Re-running the installer never touches this file.\n")
        if audit_log:
            audit_log.record_file(user_path, "create", "ok", "seeded empty user override")
    else:
        try:
            with open(user_path, "r", encoding="utf-8") as f:
                content = f.read()
            cleaned_lines = []
            modified = False
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("include") and "mpv.conf.user" in stripped:
                    modified = True
                    continue
                cleaned_lines.append(line)
            cleaned_content = "\n".join(cleaned_lines)
            cleaned_content = re.sub(
                r'\[protocol\.http\]\s*(?=\Z|\[)',
                '',
                cleaned_content,
                flags=re.MULTILINE
            ).strip() + "\n"
            if modified or cleaned_content.strip() != content.strip():
                with open(user_path, "w", encoding="utf-8") as f:
                    f.write(cleaned_content)
                if audit_log:
                    audit_log.record_file(user_path, "modify", "ok", "stripped self-referential includes")
        except Exception as e:
            ui.warn(f"Could not sanitize mpv.conf.user: {e}")


def ensure_windows_shortcuts(env, audit_log=None):
    """Ensure Windows Start Menu and Desktop shortcuts for mpv enforce
    WorkingDirectory pointing to %USERPROFILE%."""
    if env.os != "windows":
        return []

    import subprocess
    userprofile = os.environ.get("USERPROFILE") or os.path.expandvars("%USERPROFILE%")
    appdata = os.environ.get("APPDATA") or os.path.expandvars("%APPDATA%")
    if not userprofile or not appdata:
        return []

    mpv_exe = shutil.which("mpv")
    if not mpv_exe:
        candidates = [
            os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "mpv", "mpv.exe"),
            r"C:\Program Files\mpv\mpv.exe",
        ]
        for candidate in candidates:
            if os.path.isfile(candidate):
                mpv_exe = candidate
                break

    if not mpv_exe or not os.path.isfile(mpv_exe):
        return []

    start_menu_lnk = os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\mpv.lnk")
    desktop_lnk = os.path.join(userprofile, r"Desktop\mpv.lnk")

    mpv_exe_escaped = mpv_exe.replace('\\', '\\\\')
    userprofile_escaped = userprofile.replace('\\', '\\\\')
    start_menu_escaped = start_menu_lnk.replace('\\', '\\\\')
    desktop_escaped = desktop_lnk.replace('\\', '\\\\')

    ps_script = f"""
$sh = New-Object -ComObject WScript.Shell
$mpvExe = "{mpv_exe_escaped}"
$userProfile = "{userprofile_escaped}"

$targets = @(
    @{{ Path = "{start_menu_escaped}"; Always = $true }},
    @{{ Path = "{desktop_escaped}"; Always = $false }}
)

foreach ($t in $targets) {{
    $p = $t.Path
    if ((Test-Path $p) -or $t.Always) {{
        $dir = Split-Path -Parent $p
        if (-not (Test-Path $dir)) {{
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }}
        $sc = $sh.CreateShortcut($p)
        $sc.TargetPath = $mpvExe
        $sc.WorkingDirectory = $userProfile
        $sc.IconLocation = "$mpvExe,0"
        $sc.Save()
        Write-Output "SHORTCUT_OK: $p"
    }}
}}
"""
    updated = []
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=15,
        )
        for line in res.stdout.splitlines():
            if line.startswith("SHORTCUT_OK:"):
                lnk_path = line.split(":", 1)[1].strip()
                updated.append(lnk_path)
                ui.success(f"Shortcut updated: {lnk_path} (WorkingDirectory: {userprofile})")
                if audit_log:
                    audit_log.record_file(
                        lnk_path, "modify", "ok", f"enforced WorkingDirectory={userprofile}"
                    )
    except Exception as e:
        ui.warn(f"Could not update Windows shortcuts: {e}")

    return updated


def _normalize_windows_path(path):
    return os.path.normpath(path).replace("\\", "/")


def _patch_autosubsync_conf(template_path, dest_path, env):
    """Patch autosubsync.conf.template with platform-specific paths."""
    defaults = PLATFORM_REQUIRED_DEFAULTS.get(env.platform_key, {})

    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    def _pick_first_existing(candidates):
        for path in candidates:
            if path and os.path.isfile(path):
                return path
        return None

    # For 'auto' values on Windows, try to find actual paths
    ffmpeg_path = defaults.get("ffmpeg_path", "ffmpeg")
    ffsubsync_path = defaults.get("ffsubsync_path", "ffsubsync")
    alass_path = defaults.get("alass_path", "alass")

    if env.os == "windows":
        ffmpeg_root = SYSTEM_DEPS.get("ffmpeg", {}).get("windows", {}).get("install_dir")
        ffmpeg_bin_subdir = SYSTEM_DEPS.get("ffmpeg", {}).get("windows", {}).get("bin_subdir")
        ffsubsync_bin_dir = SYSTEM_DEPS.get("ffsubsync", {}).get("windows", {}).get("bin_dir")
        alass_dir = SYSTEM_DEPS.get("alass", {}).get("windows", {}).get("install_dir")

        ffmpeg_candidates = []
        if ffmpeg_root:
            if ffmpeg_bin_subdir:
                ffmpeg_candidates.append(os.path.join(ffmpeg_root, ffmpeg_bin_subdir, "ffmpeg.exe"))
            ffmpeg_candidates.append(os.path.join(ffmpeg_root, "ffmpeg.exe"))
            ffmpeg_candidates.append(os.path.join(ffmpeg_root, "bin", "ffmpeg.exe"))

        ffsubsync_candidates = []
        if ffsubsync_bin_dir:
            ffsubsync_candidates.extend([
                os.path.join(ffsubsync_bin_dir, "ffsubsync.exe"),
                os.path.join(ffsubsync_bin_dir, "ffsubsync.cmd"),
                os.path.join(ffsubsync_bin_dir, "ffsubsync"),
            ])

        alass_candidates = []
        if alass_dir:
            alass_candidates.extend([
                os.path.join(alass_dir, "alass.exe"),
                os.path.join(alass_dir, "alass-cli.exe"),
            ])

        if ffmpeg_path == "auto":
            ffmpeg_path = _pick_first_existing(ffmpeg_candidates) or ffmpeg_path
        if ffsubsync_path in ("auto", "ffsubsync"):
            ffsubsync_path = _pick_first_existing(ffsubsync_candidates) or ffsubsync_path
        if alass_path in ("auto", "alass", "alass-cli"):
            alass_path = _pick_first_existing(alass_candidates) or alass_path

    if ffmpeg_path == "auto":
        ffmpeg_path = _find_binary("ffmpeg", env) or "ffmpeg"
    if ffsubsync_path in ("auto", "ffsubsync"):
        ffsubsync_path = _find_binary("ffsubsync", env) or "ffsubsync"
    if alass_path in ("auto", "alass", "alass-cli"):
        if alass_path == "alass-cli":
            alass_path = _find_binary("alass-cli", env) or _find_binary("alass", env) or "alass-cli"
        else:
            alass_path = _find_binary("alass", env) or _find_binary("alass-cli", env) or "alass"

    if env.os == "windows":
        ffmpeg_path = _normalize_windows_path(ffmpeg_path)
        ffsubsync_path = _normalize_windows_path(ffsubsync_path)
        alass_path = _normalize_windows_path(alass_path)

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


def _resolve_ytdl_path(env):
    """Resolve localized yt-dlp binary path dynamically."""
    candidates = []
    if env.os == "windows":
        prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidates.extend([
            os.path.join(prog_files, "mpv", "yt-dlp", "yt-dlp.exe"),
            os.path.join(prog_files, "mpv", "yt-dlp.exe"),
        ])
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(os.path.join(appdata, "mpv", "tools", "yt-dlp.exe"))
            candidates.append(os.path.join(appdata, "mpv", "tools", "yt-dlp", "yt-dlp.exe"))
    else:
        candidates.extend([
            os.path.expanduser("~/.local/bin/yt-dlp"),
            "/usr/local/bin/yt-dlp",
            "/usr/bin/yt-dlp",
        ])

    for c in candidates:
        if os.path.isfile(c):
            if env.os == "windows":
                return _normalize_windows_path(c)
            return c

    which_path = _find_binary("yt-dlp", env)
    if which_path:
        return which_path

    return "yt-dlp"



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

def deploy(
    staging_dir,
    env,
    repo_dir,
    dry_run=False,
    audit_log=None,
    mpv_profile=MPV_PROFILE_DEFAULT,
    anime_preset="A",
    scaler_tier="balanced",
    display_mode="fixed",
    dither_depth="auto",
):
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

    # 3b. Override with repo-vendored/patched scripts (ensures patches like thumbfast storyboard, smart-paste, SmartSkip & ytdl_hook persist across installs)
    repo_scripts = os.path.join(repo_dir, "scripts")
    if os.path.isdir(repo_scripts):
        scripts_dst = os.path.join(config_dir, "scripts")
        os.makedirs(scripts_dst, exist_ok=True)
        for sname in os.listdir(repo_scripts):
            s_src = os.path.join(repo_scripts, sname)
            s_dst = os.path.join(scripts_dst, sname)
            if os.path.isfile(s_src):
                shutil.copy2(s_src, s_dst)
                if audit_log:
                    audit_log.record_file(s_dst, "copy", "ok", f"deployed repo script {sname}")
        ui.success("repo scripts/ deployed & patched")

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

        # Dynamic local deployment artifact: ytdl_hook.conf
        resolved_ytdl = _resolve_ytdl_path(env)
        ytdl_dest = os.path.join(opts_dst, "ytdl_hook.conf")
        with open(ytdl_dest, "w", encoding="utf-8") as f:
            f.write(f"ytdl_path={resolved_ytdl}\n")
        ui.success(f"ytdl_hook.conf deployed (ytdl_path={resolved_ytdl})")
        results.append({"name": "ytdl_hook.conf", "status": "ok", "detail": f"ytdl_path={resolved_ytdl}"})
        if audit_log:
            audit_log.record_file(ytdl_dest, "modify", "ok", f"localized ytdl_path={resolved_ytdl}")

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
                anime_preset=anime_preset,
                scaler_tier=scaler_tier,
                display_mode=display_mode,
                dither_depth=dither_depth,
                audit_log=audit_log,
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
            ensure_mpv_conf_user(config_dir, audit_log=audit_log)

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

    # 7. Enforce Windows shortcuts with user WorkingDirectory
    if env.os == "windows":
        ensure_windows_shortcuts(env, audit_log=audit_log)

    # 8. Normalize line endings
    _normalize_line_endings(config_dir, env)

    return results
