"""
deployer.py — Deploy fetched scripts, configs, and patched templates.

Back up configuration, prepare replacements offline, render platform defaults,
and apply updates without changing personal settings or playback presets.
"""

import json
import os
import re
import shutil
import tempfile

from deploy import ui
from deploy import transaction as tx
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


def backup_existing(config_dir, audit_log=None):
    """Create a unique self-contained backup before any live replacement."""
    backup = tx.snapshot_config(config_dir)
    if backup:
        ui.success(f"Backup created: {backup}")
        if audit_log:
            audit_log.record_backup(backup)
            audit_log.record_file(config_dir, "backup", "ok", f"backed up to {backup}", backup_path=backup)
    return backup


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
        if os.path.isdir(full_path) and not os.path.islink(full_path) and not tx.is_junction(full_path):
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
    """Restore a snapshot via reversible renames, retaining .git and safety backup."""
    if backup_path is None:
        backups = list_backups(config_dir)
        if not backups:
            raise FileNotFoundError(f"No backups found for: {config_dir}")
        backup_path = backups[0]
    safety_backup = tx.restore_snapshot(config_dir, backup_path, dry_run=dry_run)
    if dry_run:
        ui.info(f"[DRY RUN] Would restore {config_dir} from {backup_path}")
        return {"name": "rollback", "status": "skipped", "detail": f"dry run ({backup_path})"}
    if safety_backup:
        ui.success(f"Pre-rollback config saved as: {safety_backup}")
    if audit_log:
        if safety_backup:
            audit_log.record_backup(safety_backup)
        audit_log.record_file(config_dir, "backup", "ok", f"restored from {backup_path}", backup_path=safety_backup)
    return {"name": "rollback", "status": "ok", "detail": str(backup_path)}


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

    # Experience presets must still use a backend supported on the host.
    if env.os == "macos":
        defaults.update(PLATFORM_NATIVE_MPV_DEFAULTS.get("macos", {}))
    elif env.os == "windows" and defaults.get("gpu_api") == "vulkan" and selected_profile == "linux-like":
        defaults.update(PLATFORM_NATIVE_MPV_DEFAULTS.get("windows", {}))
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
            try:
                res = subprocess.run(["xrandr", "--current"], capture_output=True, text=True, timeout=2)
                if res.returncode == 0:
                    match = re.search(r'\b(\d+(?:\.\d+)?)(?:\s*\*|\*)', res.stdout)
                    if match:
                        return match.group(1)
            except Exception:
                pass
            try:
                res = subprocess.run(["kscreen-doctor", "-o"], capture_output=True, text=True, timeout=2)
                if res.returncode == 0:
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
    border_value = "no" if env.os == "windows" else "yes"
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
    if selected_profile == "native":
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
    content = _process_conditionals(content, {
        "GPU_CONTEXT": gpu_context,
        "NATIVE_FS": native_fs_value,
    })
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(content)


def ensure_mpv_conf_user(config_dir, audit_log=None):
    """Seed personal overrides, with legacy self-include repair when called explicitly."""
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
    """Ensure Windows shortcuts use the user's home as WorkingDirectory."""
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
    ps_script = """
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
$data = [Console]::In.ReadToEnd() | ConvertFrom-Json
$sh = New-Object -ComObject WScript.Shell
$mpvExe = $data.exe
$userProfile = $data.userprofile
$targets = @(
    @{ Path = $data.start_menu; Always = $true },
    @{ Path = $data.desktop; Always = $false }
)
foreach ($t in $targets) {
    $p = $t.Path
    if ((Test-Path -LiteralPath $p) -or $t.Always) {
        $dir = Split-Path -Parent $p
        [System.IO.Directory]::CreateDirectory($dir) | Out-Null
        $sc = $sh.CreateShortcut($p)
        $sc.TargetPath = $mpvExe
        $sc.WorkingDirectory = $userProfile
        $sc.IconLocation = "$mpvExe,0"
        $sc.Save()
        Write-Output "SHORTCUT_OK: $p"
    }
}
"""
    updated = []
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            input=json.dumps({"exe": mpv_exe, "userprofile": userprofile,
                              "start_menu": start_menu_lnk, "desktop": desktop_lnk}),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if res.returncode != 0:
            ui.warn("PowerShell could not update mpv shortcuts")
            return []
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


def deploy(
    staging_dir, env, repo_dir, dry_run=False, audit_log=None,
    mpv_profile=MPV_PROFILE_DEFAULT, anime_preset="A", scaler_tier="balanced",
    display_mode="fixed", dither_depth="auto", lockfile=None, verify_callback=None,
):
    """Prepare a complete config offline, then apply recoverable replacements.

    Existing mpv.conf/input.conf/user overrides and script-opts are preserved.
    Profile flags seed NEW configurations; migration is an explicit command.
    Dependencies and Windows shortcuts are outside the filesystem transaction.
    """
    if dry_run:
        return [{"name": "deploy", "status": "skipped", "detail": "dry run"}]
    config_dir = tx.config_path(env.config_dir)
    tx.assert_disjoint(config_dir, staging_dir, repo_dir)
    tx.validate_staging(staging_dir)
    config_src = os.path.join(repo_dir, "config")
    tx.regular_tree(config_src)
    for template in ("mpv.conf.template", "input.conf.template"):
        if not os.path.isfile(os.path.join(config_src, template)):
            raise FileNotFoundError(f"Required template is missing: {template}")
    parent = os.path.dirname(config_dir)
    os.makedirs(parent, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix=".mpv-install-prepared-", dir=parent) as prepared:
        tx.prepare_assets(config_dir, staging_dir, repo_dir, prepared)
        names = list(tx.ASSET_DIRS)
        newly_managed = []
        opts_src = os.path.join(config_src, "script-opts")
        opts_old = os.path.join(config_dir, "script-opts")
        opts_dst = os.path.join(prepared, "script-opts")
        if os.path.lexists(opts_old):
            tx.copy_overlay(opts_old, opts_dst)
        else:
            os.mkdir(opts_dst)
        if os.path.isdir(opts_src):
            for name in os.listdir(opts_src):
                src, dst = os.path.join(opts_src, name), os.path.join(opts_dst, name)
                if os.path.isfile(src) and not name.endswith(".template") and not os.path.exists(dst):
                    shutil.copy2(src, dst)
                    newly_managed.append("script-opts/" + name)
        ytdl_dest = os.path.join(opts_dst, "ytdl_hook.conf")
        # Only localize a newly supplied default, not a personal existing path.
        if not os.path.exists(os.path.join(opts_old, "ytdl_hook.conf")):
            with open(ytdl_dest, "w", encoding="utf-8") as stream:
                stream.write(f"ytdl_path={_resolve_ytdl_path(env)}\n")
            if "script-opts/ytdl_hook.conf" not in newly_managed:
                newly_managed.append("script-opts/ytdl_hook.conf")
        ass_template = os.path.join(opts_src, "autosubsync.conf.template")
        ass_dest = os.path.join(opts_dst, "autosubsync.conf")
        if os.path.isfile(ass_template) and not os.path.exists(ass_dest):
            _patch_autosubsync_conf(ass_template, ass_dest, env)
            newly_managed.append("script-opts/autosubsync.conf")
        names.append("script-opts")
        selected, defaults = _resolve_mpv_profile(env, mpv_profile)
        if not os.path.lexists(os.path.join(config_dir, "mpv.conf")):
            _patch_mpv_conf(os.path.join(config_src, "mpv.conf.template"),
                            os.path.join(prepared, "mpv.conf"), env, selected, defaults,
                            anime_preset=anime_preset, scaler_tier=scaler_tier,
                            display_mode=display_mode, dither_depth=dither_depth)
            names.append("mpv.conf")
            newly_managed.append("mpv.conf")
        else:
            ui.info("Preserved existing mpv.conf; profile flags only seed new configs.")
        if not os.path.lexists(os.path.join(config_dir, "input.conf")):
            _patch_input_conf(os.path.join(config_src, "input.conf.template"),
                              os.path.join(prepared, "input.conf"), env)
            names.append("input.conf")
            newly_managed.append("input.conf")
        if not os.path.lexists(os.path.join(config_dir, "mpv.conf.user")):
            ensure_mpv_conf_user(prepared)
            names.append("mpv.conf.user")  # personal overrides are NEVER owned for uninstall
        for name in ("shader_cache", "chapters"):
            live = os.path.join(config_dir, name)
            if not os.path.lexists(live):
                os.mkdir(os.path.join(prepared, name))
                names.append(name)
            elif not os.path.isdir(live):
                raise ValueError(f"Expected directory: {live}")
        if lockfile is not None:
            import hashlib
            metadata = tx.asset_manifest(lockfile, staging_dir, repo_dir, prepared)
            for relative in newly_managed:
                with open(os.path.join(prepared, *relative.split("/")), "rb") as stream:
                    metadata["managed_files"][relative] = hashlib.sha256(stream.read()).hexdigest()
            tx._write_json(os.path.join(prepared, tx.MANIFEST), metadata)
            names.append(tx.MANIFEST)
        backup = backup_existing(config_dir, audit_log=audit_log)
        if backup:
            results.append({"name": "backup", "status": "ok", "detail": backup})
        tx.replace_items(config_dir, prepared, names, verify_callback=verify_callback)
        for name in names:
            results.append({"name": name, "status": "ok", "detail": "recoverable replacement"})
            if audit_log:
                audit_log.record_file(os.path.join(config_dir, name), "copy", "ok", "transaction committed")
    if env.os == "windows":
        ensure_windows_shortcuts(env, audit_log=audit_log)
    return results
