"""
deployer.py — Deploy fetched scripts, configs, and patched templates.

Back up configuration, prepare replacements offline, render platform defaults,
and apply updates without changing personal settings or playback presets.
"""

import argparse
import inspect
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from deploy import transaction as tx
from deploy import ui
from deploy.audit_log import AuditLog
from deploy.detector import detect
from deploy.fetcher import fetch_all
from deploy.installer import install_deps
from deploy.planner import build_install_plan, build_update_plan, confirm_plan, display_plan
from deploy.registry import (
    ANIME4K_CHAINS,
    MPV_EXPERIENCE_PROFILES,
    MPV_PROFILE_DEFAULT,
    PLATFORM_NATIVE_MPV_DEFAULTS,
    PLATFORM_REQUIRED_DEFAULTS,
    SCALER_TIERS,
    SCRIPTS,
    SHADERS,
    SYSTEM_DEPS,
)
from deploy.verifier import verify

LINUX_VISUAL_TUNING_BLOCK = (
    "# 1. إعدادات الواجهة (OSD) لرسائل النظام الديناميكية\n"
    'osd-font="Tahoma"\n'
    "osd-font-size=50\n"
    "osd-scale-by-window=yes\n"
    "\n"
    "# 2. إعدادات الترجمة (SRT) الديناميكية (مريحة للعين)\n"
    "sub-font-provider=fontconfig\n"
    'sub-font="Tahoma"\n'
    "sub-font-size=36\n"
    "sub-scale-by-window=yes\n"
    'sub-color="#FFFFFF"\n'
    'sub-border-color="#000000"\n'
    "sub-border-size=2\n"
    "sub-shadow-offset=1\n"
    "sub-margin-y=36\n"
    "\n"
    "# 3. Window Sizing Helpers (Convenience)\n"
    "geometry=50%x50%\n"
    "autofit-larger=90%x90%\n"
    "autofit-smaller=30%x30%\n"
)


CONDITIONAL_BLOCK_PATTERN = re.compile(r"\{\{#if (\w+)\}\}(.*?)\{\{/if\}\}\n*", flags=re.DOTALL)


def _process_conditionals(content, blocks):
    """Process {{#if NAME}}...{{/if}} blocks atomically per named block."""
    return CONDITIONAL_BLOCK_PATTERN.sub(
        lambda m: m.group(2) if blocks.get(m.group(1)) else "", content
    )


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
            audit_log.record_file(
                config_dir, "backup", "ok", f"backed up to {backup}", backup_path=backup
            )
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
        if (
            os.path.isdir(full_path)
            and not os.path.islink(full_path)
            and not tx.is_junction(full_path)
        ):
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
        audit_log.record_file(
            config_dir, "backup", "ok", f"restored from {backup_path}", backup_path=safety_backup
        )
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
    elif (
        env.os == "windows"
        and defaults.get("gpu_api") == "vulkan"
        and selected_profile == "linux-like"
    ):
        defaults.update(PLATFORM_NATIVE_MPV_DEFAULTS.get("windows", {}))
    return selected_profile, defaults


def _detect_display_fps(env):
    """Detect the actual display refresh rate to avoid hardcoded fallbacks."""
    import re
    import subprocess

    try:
        if env.os == "windows":
            cmd = [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance -ClassName Win32_VideoController).CurrentRefreshRate / 1.0",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip():
                try:
                    fps_val = float(res.stdout.strip())
                    if fps_val > 0:
                        fps_int = int(round(fps_val))
                        exact_map = {
                            144: "143.981",
                            120: "119.880",
                            60: "59.940",
                            165: "164.999",
                            240: "239.760",
                        }
                        return exact_map.get(fps_int, f"{fps_val:.3f}")
                except ValueError:
                    pass
        elif env.os == "linux":
            try:
                res = subprocess.run(
                    ["xrandr", "--current"], capture_output=True, text=True, timeout=2
                )
                if res.returncode == 0:
                    match = re.search(r"\b(\d+(?:\.\d+)?)(?:\s*\*|\*)", res.stdout)
                    if match:
                        return match.group(1)
            except Exception:
                pass
            try:
                res = subprocess.run(
                    ["kscreen-doctor", "-o"], capture_output=True, text=True, timeout=2
                )
                if res.returncode == 0:
                    match = re.search(r"@(\d+(?:\.\d+)?)", res.stdout)
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
            audit_log.record_note(
                "display_mode", "auto → fixed (vrr requires explicit --display-mode vrr)"
            )
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
        if (
            env.gpu_vendor == "nvidia"
            and env.os == "linux"
            and base_hwdec in {"auto", "auto-copy", "auto-safe"}
        ):
            hwdec = "nvdec"
    replacements["{{HWDEC}}"] = hwdec
    replacements["{{GPU_CONTEXT}}"] = gpu_context
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)
    content = _process_conditionals(
        content,
        {
            "GPU_CONTEXT": gpu_context,
            "NATIVE_FS": native_fs_value,
            "D3D11_FLIP": display_settings["d3d11_flip"] if env.os == "windows" else "",
        },
    )
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(content)


def ensure_mpv_conf_user(config_dir, audit_log=None):
    """Seed personal overrides, with legacy self-include repair when called explicitly."""
    user_path = os.path.join(config_dir, "mpv.conf.user")
    if not os.path.exists(user_path):
        with open(user_path, "w", encoding="utf-8") as f:
            f.write(
                "# mpv.conf.user — personal overrides.\n"
                "# Loaded LAST by mpv.conf; values here always win.\n"
                "# Re-running the installer never touches this file.\n"
            )
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
            cleaned_content = (
                re.sub(
                    r"\[protocol\.http\]\s*(?=\Z|\[)", "", cleaned_content, flags=re.MULTILINE
                ).strip()
                + "\n"
            )
            if modified or cleaned_content.strip() != content.strip():
                with open(user_path, "w", encoding="utf-8") as f:
                    f.write(cleaned_content)
                if audit_log:
                    audit_log.record_file(
                        user_path, "modify", "ok", "stripped self-referential includes"
                    )
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
    mpv_exe = shutil.which("mpv.exe") or shutil.which("mpv")
    if mpv_exe and mpv_exe.lower().endswith(".com"):
        candidate_exe = os.path.splitext(mpv_exe)[0] + ".exe"
        if os.path.isfile(candidate_exe):
            mpv_exe = candidate_exe
    if not mpv_exe or not os.path.isfile(mpv_exe):
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
            input=json.dumps(
                {
                    "exe": mpv_exe,
                    "userprofile": userprofile,
                    "start_menu": start_menu_lnk,
                    "desktop": desktop_lnk,
                }
            ),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if res.returncode != 0:
            err_msg = res.stderr.strip() if res.stderr and res.stderr.strip() else ""
            ui.warn(
                f"PowerShell could not update mpv shortcuts: {err_msg}"
                if err_msg
                else "PowerShell could not update mpv shortcuts"
            )
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
            ffsubsync_candidates.extend(
                [
                    os.path.join(ffsubsync_bin_dir, "ffsubsync.exe"),
                    os.path.join(ffsubsync_bin_dir, "ffsubsync.cmd"),
                    os.path.join(ffsubsync_bin_dir, "ffsubsync"),
                ]
            )
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            ffsubsync_candidates.append(
                os.path.join(appdata, "uv", "tools", "ffsubsync", "Scripts", "ffsubsync.exe")
            )
        userprofile = os.environ.get("USERPROFILE", "")
        if userprofile:
            ffsubsync_candidates.append(os.path.join(userprofile, ".local", "bin", "ffsubsync.exe"))
        alass_candidates = []
        if alass_dir:
            alass_candidates.extend(
                [
                    os.path.join(alass_dir, "alass.exe"),
                    os.path.join(alass_dir, "alass-cli.exe"),
                ]
            )
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
        candidates.extend(
            [
                os.path.join(prog_files, "mpv", "yt-dlp", "yt-dlp.exe"),
                os.path.join(prog_files, "mpv", "yt-dlp.exe"),
            ]
        )
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(os.path.join(appdata, "mpv", "tools", "yt-dlp.exe"))
            candidates.append(os.path.join(appdata, "mpv", "tools", "yt-dlp", "yt-dlp.exe"))
    else:
        candidates.extend(
            [
                os.path.expanduser("~/.local/bin/yt-dlp"),
                "/usr/local/bin/yt-dlp",
                "/usr/bin/yt-dlp",
            ]
        )
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


def _deploy_ytdlp_plugins_and_config(env, repo_dir):
    """Deploy custom yt-dlp extractors and global turbo configuration on Windows."""
    try:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return

        ytdl_dir = os.path.join(appdata, "yt-dlp")
        os.makedirs(ytdl_dir, exist_ok=True)

        # 1. Global yt-dlp config (16 connections, 1080p cap)
        conf_file = os.path.join(ytdl_dir, "config")
        config_text = (
            "# Turbo Multi-Connection Downloader (bypasses server per-connection rate limits)\n"
            "--downloader http:aria2c\n"
            "--downloader https:aria2c\n"
            '--downloader-args "aria2c:-x 16 -s 16 -k 1M --file-allocation=none --check-certificate=false"\n'
            "\n"
            "# Concurrent fragments for HLS / DASH streams\n"
            "--concurrent-fragments 16\n"
            "\n"
            "# Quality Ceiling: Best quality up to 1080p (prevents 4K / 2160p bloat)\n"
            '-f "bestvideo[height<=?1080]+bestaudio/best[height<=?1080]/best"\n'
            "\n"
            "# File naming & safety\n"
            "--windows-filenames\n"
            "--no-mtime\n"
        )
        with open(conf_file, "w", encoding="utf-8") as f:
            f.write(config_text)

        # 2. Extractors
        extractor_src = os.path.join(repo_dir, "tools", "yt_dlp_plugins", "extractor")
        if os.path.isdir(extractor_src):
            for fname in os.listdir(extractor_src):
                if fname.endswith(".py"):
                    base = os.path.splitext(fname)[0]
                    target_plugin_dir = os.path.join(
                        ytdl_dir, "plugins", base, "yt_dlp_plugins", "extractor"
                    )
                    os.makedirs(target_plugin_dir, exist_ok=True)
                    shutil.copy2(
                        os.path.join(extractor_src, fname), os.path.join(target_plugin_dir, fname)
                    )

                    # Also copy to Program Files\\mpv if present
                    prog_mpv = os.path.join(
                        os.environ.get("ProgramFiles", r"C:\Program Files"),
                        "mpv",
                        "yt_dlp_plugins",
                        "extractor",
                    )
                    try:
                        if os.path.isdir(os.path.dirname(prog_mpv)):
                            os.makedirs(prog_mpv, exist_ok=True)
                            shutil.copy2(
                                os.path.join(extractor_src, fname), os.path.join(prog_mpv, fname)
                            )
                    except Exception:
                        pass
        # 3. Register Browser Extension & Native Messaging Host
        reg_script = os.path.join(repo_dir, "tools", "register_extension.py")
        if os.path.isfile(reg_script):
            try:
                import subprocess

                subprocess.run(
                    [sys.executable, reg_script],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
        ui.success(
            "Deployed custom yt-dlp extractor plugins, companion extension, and global turbo config"
        )
    except Exception as exc:
        ui.warn(f"Notice: yt-dlp plugin deployment: {exc}")


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
    lockfile=None,
    verify_callback=None,
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
                if (
                    os.path.isfile(src)
                    and not name.endswith(".template")
                    and not os.path.exists(dst)
                ):
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
            _patch_mpv_conf(
                os.path.join(config_src, "mpv.conf.template"),
                os.path.join(prepared, "mpv.conf"),
                env,
                selected,
                defaults,
                anime_preset=anime_preset,
                scaler_tier=scaler_tier,
                display_mode=display_mode,
                dither_depth=dither_depth,
            )
            names.append("mpv.conf")
            newly_managed.append("mpv.conf")
        else:
            ui.info("Preserved existing mpv.conf; profile flags only seed new configs.")
        if not os.path.lexists(os.path.join(config_dir, "input.conf")):
            _patch_input_conf(
                os.path.join(config_src, "input.conf.template"),
                os.path.join(prepared, "input.conf"),
                env,
            )
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
                audit_log.record_file(
                    os.path.join(config_dir, name), "copy", "ok", "transaction committed"
                )
        # Apply uosc Timeline mouse-leave patch to ensure thumbnail cleanup on window exit
        try:
            from pathlib import Path

            from tools.patch_uosc_timeline_thumb import get_default_uosc_dir, run_patcher

            uosc_dir = Path(config_dir) / "scripts" / "uosc"
            if not uosc_dir.exists():
                uosc_dir = get_default_uosc_dir()
            if uosc_dir.exists():
                run_patcher(uosc_dir)
                results.append(
                    {
                        "name": "uosc-timeline-thumb-patch",
                        "status": "ok",
                        "detail": "mouse-leave cleanup patched",
                    }
                )
        except Exception as exc:
            results.append(
                {"name": "uosc-timeline-thumb-patch", "status": "warn", "detail": str(exc)}
            )
    if env.os == "windows":
        ensure_windows_shortcuts(env, audit_log=audit_log)
        _deploy_ytdlp_plugins_and_config(env, repo_dir)
    return results


def _migrate_input_conf(input_conf_path, audit_log=None):
    """Update stale system keybindings in input.conf while preserving custom keybindings."""
    if not os.path.isfile(input_conf_path):
        return False

    with open(input_conf_path, "r", encoding="utf-8") as f:
        content = f.read()

    updated_content = content

    # 1. Migrate F8 night mode binding
    new_f8_binding = (
        "F8 cycle-values af "
        '"lavfi=[dynaudnorm=f=500:g=15:p=0.95:m=10],lavfi=[alimiter=limit=0.9:level=false]" ""'
    )

    pattern_f8 = re.compile(
        r'^[ \t]*F8[ \t]+cycle-values[ \t]+af[ \t]+["\']lavfi=\[dynaudnorm=[^"\']*\]["\'][ \t]+["\']["\'][ \t]*$',
        re.MULTILINE,
    )

    if pattern_f8.search(updated_content):
        updated_content = pattern_f8.sub(new_f8_binding, updated_content)
        old_comment = (
            "# F8: (جديد) تفعيل/تعطيل توحيد مستوى الصوت (Stable Volume / Night Mode)\n"
            "# مفيد جداً في الأنمي والأفلام التي يكون فيها صوت الحوار منخفضاً والمؤثرات عالية"
        )
        new_comment = (
            "# F8: تفعيل/تعطيل توحيد مستوى الصوت (Stable Volume / Night Mode)\n"
            "# مفيد جداً في الأنمي والأفلام التي يكون فيها صوت الحوار منخفضاً والمؤثرات عالية\n"
            '# f=500   : نافذة تحليل أطول = استجابة أهدأ، لا "تنفس" مسموع\n'
            "# g=15    : أقصى رفع 15dB بدلاً من 31 — لا يضخم هسهسة الخلفية\n"
            "# p=0.95  : هدف قمة قريب من المستوى الكامل، لا ضغط حاد نحو 50%\n"
            "# m=10    : سقف لمعدل تغير الكسب لكل إطار — يقتل ضخّ الكسب المفاجئ\n"
            "# alimiter: جدار حماية نهائي يمنع القص الرقمي عند رفع volume فوق 100%"
        )
        if old_comment in updated_content:
            updated_content = updated_content.replace(old_comment, new_comment)

    # 2. Migrate / ensure MBTN_RIGHT and MBTN_RIGHT_DBL mouse bindings
    mbtn_right_match = re.search(
        r"^[ \t]*MBTN_RIGHT[ \t]+([^\r\n#]+)", updated_content, re.MULTILINE
    )
    if mbtn_right_match:
        current_cmd = mbtn_right_match.group(1).strip()
        if current_cmd in ("context-menu", "show-text context-menu"):
            updated_content = re.sub(
                r"^[ \t]*MBTN_RIGHT[ \t]+[^\r\n#]+",
                "MBTN_RIGHT       cycle pause",
                updated_content,
                count=1,
                flags=re.MULTILINE,
            )
    else:
        mouse_block = (
            "\n# ── Mouse Bindings ── Restore classic right-click pause over native context menu\n"
            "MBTN_RIGHT       cycle pause\n"
            "MBTN_RIGHT_DBL   ignore\n"
        )
        updated_content = updated_content.rstrip() + "\n" + mouse_block

    mbtn_right_dbl_match = re.search(
        r"^[ \t]*MBTN_RIGHT_DBL[ \t]+([^\r\n#]+)", updated_content, re.MULTILINE
    )
    if not mbtn_right_dbl_match:
        updated_content = re.sub(
            r"(^[ \t]*MBTN_RIGHT[ \t]+[^\r\n]+)",
            r"\1\nMBTN_RIGHT_DBL   ignore",
            updated_content,
            count=1,
            flags=re.MULTILINE,
        )
    elif mbtn_right_dbl_match.group(1).strip() in (
        "context-menu",
        "show-text context-menu",
    ):
        updated_content = re.sub(
            r"^[ \t]*MBTN_RIGHT_DBL[ \t]+[^\r\n#]+",
            "MBTN_RIGHT_DBL   ignore",
            updated_content,
            count=1,
            flags=re.MULTILINE,
        )

    # 3. Clean up manual clipboard loadfile overrides and migrate to smart_paste
    updated_content = re.sub(
        r"^[ \t]*Ctrl\+(?:Shift\+)?[vV][ \t]+loadfile[^\r\n]*\r?\n?",
        "",
        updated_content,
        flags=re.MULTILINE,
    )
    ctrl_v_match = re.search(
        r"^[ \t]*Ctrl\+v[ \t]+([^\r\n#]+)", updated_content, re.IGNORECASE | re.MULTILINE
    )
    smart_clipboard_block = (
        "\n# Instant play from clipboard (with automatic URL normalization & instant OSD)\n"
        "Ctrl+v           script-binding smart_paste/paste-to-open\n"
        "Ctrl+V           script-binding smart_paste/paste-to-open\n"
        "Ctrl+Shift+v     script-binding smart_paste/paste-to-playlist\n"
        "Ctrl+Shift+V     script-binding smart_paste/paste-to-playlist\n"
    )
    if not ctrl_v_match:
        updated_content = updated_content.rstrip() + "\n" + smart_clipboard_block
    elif "smart_paste" not in ctrl_v_match.group(1):
        updated_content = re.sub(
            r"^[ \t]*Ctrl\+(?:Shift\+)?[vV][ \t]+[^\r\n]+\r?\n?",
            "",
            updated_content,
            flags=re.MULTILINE,
        )
        updated_content = updated_content.rstrip() + "\n" + smart_clipboard_block

    # 4. Migrate / ensure Arabic bilingual twin keybindings
    updated_content = re.sub(
        r"^[ \t]*Ctrl\+(?:Shift\+)?(?:ر|Ø±)[ \t]+loadfile[^\r\n]*\r?\n?",
        "",
        updated_content,
        flags=re.MULTILINE,
    )
    if not re.search(r"^[ \t]*ا[ \t]+script-binding", updated_content, re.MULTILINE):
        arabic_bindings = (
            "\n# ─── Arabic Bilingual Twin Bindings (Arabic 101/102 Layout) ───\n"
            "# History (memo) — ا = h (History)\n"
            "ا        script-binding memo-history\n\n"
            "# SponsorBlock voting — ﻻ = B (Upvote), Shift+ﻻ / ﻵ = Shift+B (Downvote)\n"
            "ﻻ        script-binding sponsorblock_upvote\n"
            "Ctrl+ﻻ   script-binding sponsorblock_downvote\n"
            "ﻵ        script-binding sponsorblock_downvote\n\n"
            "# SponsorBlock segment marking / submission — ل = g, Shift+ل / إ = G\n"
            "ل        script-binding sponsorblock_set_segment\n"
            "Shift+ل  script-binding sponsorblock_submit_segment\n"
            "إ        script-binding sponsorblock_submit_segment\n\n"
            "# Explicit Latin bindings for SponsorBlock segment marking\n"
            "g        script-binding sponsorblock_set_segment\n"
            "G        script-binding sponsorblock_submit_segment\n\n"
            "# Subtitle sync (autosubsync) — ى = n (syNc)\n"
            "ى        script-binding autosubsync-menu\n\n"
            "# Instant play from clipboard — Ctrl+ر = Ctrl+v\n"
            "Ctrl+ر           script-binding smart_paste/paste-to-open\n"
            "Ctrl+Shift+ر     script-binding smart_paste/paste-to-playlist\n"
        )
        updated_content = updated_content.rstrip() + "\n" + arabic_bindings
    else:
        ctrl_ar_match = re.search(
            r"^[ \t]*Ctrl\+(?:ر|Ø±)[ \t]+([^\r\n#]+)", updated_content, re.MULTILINE
        )
        if not ctrl_ar_match or "smart_paste" not in ctrl_ar_match.group(1):
            updated_content = re.sub(
                r"^[ \t]*Ctrl\+(?:Shift\+)?(?:ر|Ø±)[ \t]+[^\r\n]+\r?\n?",
                "",
                updated_content,
                flags=re.MULTILINE,
            )
            updated_content = updated_content.rstrip() + (
                "\n# Instant play from clipboard — Ctrl+ر = Ctrl+v\n"
                "Ctrl+ر           script-binding smart_paste/paste-to-open\n"
                "Ctrl+Shift+ر     script-binding smart_paste/paste-to-playlist\n"
            )

    if updated_content != content:
        with open(input_conf_path, "w", encoding="utf-8") as f:
            f.write(updated_content)
        if audit_log:
            audit_log.record_file(
                input_conf_path,
                "modify",
                "ok",
                "migrated input.conf bindings (F8, mouse, clipboard, arabic)",
            )
        return True

    return False


def _extract_overrides(content, defaults):
    """Extract user overrides from an existing mpv.conf compared to template defaults."""
    overrides = {}
    order = []
    current_section = None
    placeholder_pattern = re.compile(r"\{\{[A-Z0-9_]+\}\}")

    def _ensure_section(section):
        if section not in overrides:
            overrides[section] = []
            order.append(section)

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1]
            continue
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key.lower() == "include":
            continue
        default_value = defaults.get(current_section, {}).get(key)
        if default_value is None:
            keep = True
        else:
            default_value = default_value.strip()
            if placeholder_pattern.search(default_value):
                keep = False
            else:
                keep = value != default_value
        if keep:
            _ensure_section(current_section)
            overrides[current_section].append((key, value))

    return order, overrides


# ---------------------------------------------------------------------------
# Command-line entry point
#
# ``python -m deploy.deployer --install`` is the process the ``mpv-config`` CLI
# (and, through it, install.sh / install.ps1) delegates to. This section is
# orchestration only: the transactional work lives in deploy() and the helpers
# above, none of which are changed here.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent

# deploy()'s own keyword defaults are the CLI defaults, so the two cannot drift.
_DEPLOY_DEFAULTS = {
    name: param.default
    for name, param in inspect.signature(deploy).parameters.items()
    if param.default is not inspect.Parameter.empty
}


def _is_interactive_session():
    return hasattr(sys.stdin, "isatty") and sys.stdin.isatty()


def _audit_log_for(env):
    """Return an AuditLog pointing at the config directory's log file."""
    return AuditLog(os.path.join(env.config_dir, ".audit-log.json"))


def _require_complete_fetch(results):
    """Refuse to continue unless every expected script and the shader pack arrived."""
    expected = [entry["name"] for entry in SCRIPTS] + [SHADERS["name"]]
    names = [result.get("name") for result in results]
    if (
        len(names) != len(expected)
        or set(names) != set(expected)
        or any(result.get("status") != "ok" for result in results)
    ):
        raise RuntimeError("Fetch was incomplete; no live configuration was replaced")


def cmd_install(args):
    """Fail-closed install: fetch, dependencies, recoverable deployment, verification.

    Nothing live is touched until every download has succeeded and every
    dependency step has passed. deploy() then swaps the configuration in
    transactionally and rolls back if the verification callback raises.
    """
    ui.banner()
    env = detect()
    plan = build_install_plan(env)
    display_plan(plan, "Installation Plan")
    if args.dry_run:
        ui.info("[DRY RUN] No downloads, installs, audit writes, or replacements.")
        return 0
    if _is_interactive_session() and not confirm_plan(plan, "installation"):
        ui.warn("Installation cancelled by user.")
        return 0

    config_dir = tx.config_path(env.config_dir)
    tx.assert_disjoint(config_dir, str(REPO_ROOT))
    with tx.operation_lock(config_dir):
        parent = os.path.dirname(config_dir)
        with tempfile.TemporaryDirectory(prefix=".mpv-install-stage-", dir=parent) as staging:
            # Download first: a failed fetch must not install any dependencies.
            fetch_results, lockfile = fetch_all(SCRIPTS, SHADERS, staging)
            ui.summary(fetch_results)
            _require_complete_fetch(fetch_results)
            tx.validate_staging(staging)

            audit_log = _audit_log_for(env)
            audit_log.start_session("install", env)
            try:
                dep_results = install_deps(
                    env, dry_run=False, audit_log=audit_log, mpv_version=args.mpv_version
                )
                ui.summary(dep_results)
                if any(result.get("status") == "failed" for result in dep_results):
                    raise RuntimeError(
                        "Dependency installation failed; configuration was not replaced"
                    )

                verify_results = []

                def check_install():
                    verify_results.extend(verify(config_dir, env))
                    if any(result.get("status") == "failed" for result in verify_results):
                        ui.summary(verify_results)
                        raise RuntimeError(
                            "Verification failed; restoring the previous configuration"
                        )

                deploy_results = deploy(
                    staging,
                    env,
                    str(REPO_ROOT),
                    audit_log=audit_log,
                    mpv_profile=args.mpv_profile,
                    anime_preset=args.anime_preset,
                    scaler_tier=args.scaler_tier,
                    display_mode=args.display_mode,
                    dither_depth=args.dither_depth,
                    lockfile=lockfile,
                    verify_callback=check_install,
                )
                if any(result.get("status") == "failed" for result in deploy_results):
                    raise RuntimeError("Deployment reported a failure")
                ui.summary(deploy_results + verify_results)
                audit_log.complete_session("completed")
                ui.panel(
                    f"Deployment complete. Config: {config_dir}", title="Success", style="green"
                )
            except BaseException as exc:
                status = "cancelled" if isinstance(exc, KeyboardInterrupt) else "failed"
                audit_log.complete_session(status)
                raise
    return 0


def cmd_verify(args):
    """Verify the deployed configuration; fail loudly if any check fails."""
    ui.banner()
    env = detect()
    results = verify(env.config_dir, env)
    ui.summary(results)
    if any(result.get("status") == "failed" for result in results):
        raise RuntimeError("Installation verification failed")
    return 0


def cmd_update(args):
    """Update only assets after complete fetch, keeping a recoverable backup."""
    ui.banner()
    env = detect()
    plan = build_update_plan(env)
    display_plan(plan, "Update Plan")
    if args.dry_run:
        ui.info("[DRY RUN] No downloads, audit writes, staging, or replacements.")
        return 0
    if _is_interactive_session() and not confirm_plan(plan, "update"):
        ui.warn("Update cancelled by user.")
        return 0
    config_dir = tx.config_path(env.config_dir)
    tx.assert_disjoint(config_dir, str(REPO_ROOT))
    with tx.operation_lock(config_dir):
        parent = os.path.dirname(config_dir)
        with tempfile.TemporaryDirectory(prefix=".mpv-update-stage-", dir=parent) as staging:
            fetch_results, lockfile = fetch_all(SCRIPTS, SHADERS, staging)
            ui.summary(fetch_results)
            _require_complete_fetch(fetch_results)
            backup = tx.update_assets(config_dir, staging, str(REPO_ROOT), lockfile)
        audit_log = _audit_log_for(env)
        audit_log.start_session("update", env)
        if backup:
            audit_log.record_backup(backup)
            ui.success(f"Previous configuration saved as: {backup}")
        audit_log.record_file(
            config_dir,
            "copy",
            "ok",
            "assets and manifest committed; personal configuration preserved",
        )
        audit_log.complete_session("completed")
        ui.panel(
            "Update complete. Personal configuration was preserved.",
            title="Success",
            style="green",
        )
    return 0


def _match_backup(config_dir, requested, backups):
    """Return the entry of ``backups`` that ``requested`` names (full path or bare name)."""
    parent = os.path.dirname(config_dir)
    known = {os.path.normcase(os.path.realpath(path)): path for path in backups}
    for candidate in (requested, os.path.join(parent, requested)):
        match = known.get(os.path.normcase(os.path.realpath(candidate)))
        if match is not None:
            return match
    return None


def cmd_rollback(args):
    """Restore configuration from backup, retaining a safety snapshot."""
    ui.banner()
    env = detect()
    requested = getattr(args, "backup_path", None) or getattr(args, "rollback", None)
    if requested in (None, "", "LATEST", "__latest__", True):
        requested = None
    config_dir = tx.config_path(env.config_dir)
    backups = list_backups(config_dir)
    if requested is None:
        if not backups:
            ui.warn(f"No backups found for {config_dir}. Cannot rollback.")
            return 1
        requested = backups[0]
    else:
        # restore_snapshot copies whatever directory it is given over the live configuration,
        # so only this configuration's own backups may be named here.
        match = _match_backup(config_dir, requested, backups)
        if match is None:
            ui.error(f"Not a backup of {config_dir}: {requested}")
            for path in backups[:5]:
                ui.info(f"Available backup: {path}")
            return 1
        requested = match
    if args.dry_run:
        result = rollback_config(config_dir, backup_path=requested, dry_run=True)
        ui.summary([result])
        return 0
    if _is_interactive_session() and not ui.confirm("Restore backup and retain a safety snapshot?"):
        ui.warn("Rollback cancelled by user.")
        return 0
    with tx.operation_lock(config_dir):
        audit_log = _audit_log_for(env)
        audit_log.start_session("rollback", env)
        try:
            result = rollback_config(config_dir, backup_path=requested, audit_log=audit_log)
            ui.summary([result])
            if result.get("status") != "ok":
                raise RuntimeError("Rollback did not complete")
            audit_log.complete_session("completed")
            ui.panel(
                f"Rollback complete!\nConfig dir: {config_dir}",
                title="Success",
                style="green",
            )
        except BaseException:
            audit_log.complete_session("failed")
            raise
    return 0


def cmd_status(args):
    """Show current install status vs available versions."""
    ui.banner()
    env = detect()

    lockfile_path = os.path.join(env.config_dir, ".deploy.lock.json")
    if not os.path.isfile(lockfile_path):
        ui.warn("No deployment lockfile found. Run 'mpv-config install' first.")
        return 0

    with open(lockfile_path, "r", encoding="utf-8") as f:
        lockfile = json.load(f)

    ui.header("Installed Scripts & Shaders")

    scripts_data = lockfile.get("scripts", {})
    for name, info in scripts_data.items():
        version = info.get("version", info.get("source", "unknown"))
        date = info.get("fetched_at", "")[:10]
        ui.success(f"{name}: {version} (fetched {date})")

    shaders_data = lockfile.get("shaders", {})
    if shaders_data:
        version = shaders_data.get("version", "unknown")
        date = shaders_data.get("fetched_at", "")[:10]
        ui.success(f"Anime4K shaders: {version} (fetched {date})")

    audit_log = _audit_log_for(env)
    sessions = audit_log.sessions()
    if sessions:
        last = sessions[-1]
        ui.header("Last Installer Session")
        ui.info(f"Operation : {last.get('operation', '?')}")
        ui.info(f"Status    : {last.get('status', '?')}")
        ui.info(f"Started   : {last.get('started_at', '?')}")
        ui.info(f"Completed : {last.get('completed_at', '?') or '(in progress)'}")
        pkg_safe = audit_log.get_packages_installed_by_us()
        if pkg_safe:
            ui.info(f"Installed by this tool: {', '.join(pkg_safe)}")

    ui.panel(
        f"Lockfile: {lockfile_path}\nConfig dir: {env.config_dir}",
        title="Environment Info",
        style="dim",
    )
    return 0


def cmd_sync_deps(args):
    """Sync MPV dependency suite (yt-dlp, ffmpeg-full, alass, ffsubsync)."""
    ui.banner()
    env = detect()
    if args.dry_run:
        ui.info("[DRY RUN] Read-only preview only. Dependency sync skipped.")
        return 0
    config_dir = tx.config_path(env.config_dir)
    with tx.operation_lock(config_dir):
        audit_log = _audit_log_for(env)
        audit_log.start_session("sync-deps", env)
        try:
            from deploy.installer import sync_dependencies

            results = sync_dependencies(env=env, dry_run=False, audit_log=audit_log)
            ui.summary(results)
            failed = any(r.get("status") == "failed" for r in results)
            if failed:
                ui.panel(
                    "Dependency synchronization completed with failures.",
                    title="Warning",
                    style="yellow",
                )
                audit_log.complete_session("completed_with_errors")
                return 1
            ui.panel("Dependency synchronization complete!", title="Success", style="green")
            audit_log.complete_session("completed")
        except BaseException:
            audit_log.complete_session("failed")
            raise
    return 0


def _remove_deployed_files(
    env, purge_config=False, remove_backups=False, dry_run=False, audit_log=None
):
    results = []
    config_dir = env.config_dir

    managed_entries = [
        "scripts",
        "shaders",
        "fonts",
        "script-opts",
        "shader_cache",
        "chapters",
        "mpv.conf",
        "input.conf",
        ".deploy.lock.json",
    ]

    if purge_config:
        if os.path.lexists(config_dir):
            is_symlink = os.path.islink(config_dir)
            kind = "symlink" if is_symlink else "config dir"
            if dry_run:
                ui.info(f"[DRY RUN] Would remove {kind}: {config_dir}")
                results.append({"name": "config_dir", "status": "skipped", "detail": "dry run"})
            else:
                if is_symlink:
                    os.unlink(config_dir)
                else:
                    _remove_path(config_dir)
                ui.success(f"Removed {kind}: {config_dir}")
                results.append({"name": "config_dir", "status": "ok", "detail": f"removed {kind}"})
                if audit_log:
                    audit_log.record_file(config_dir, "delete", "ok", f"full {kind} removed")
        else:
            results.append({"name": "config_dir", "status": "skipped", "detail": "not found"})
    else:
        for name in managed_entries:
            path = os.path.join(config_dir, name)
            if not os.path.lexists(path):
                continue
            is_symlink = os.path.islink(path)
            kind = "symlink" if is_symlink else "file/dir"
            if dry_run:
                ui.info(f"[DRY RUN] Would remove {kind}: {path}")
                results.append({"name": name, "status": "skipped", "detail": "dry run"})
            else:
                if is_symlink:
                    os.unlink(path)
                else:
                    _remove_path(path)
                ui.success(f"Removed {kind}: {path}")
                results.append({"name": name, "status": "ok", "detail": f"removed {kind}"})
                if audit_log:
                    audit_log.record_file(path, "delete", "ok", f"removed {kind} by uninstall")

    if remove_backups:
        backups = list_backups(config_dir)
        if not backups:
            results.append({"name": "backups", "status": "skipped", "detail": "none found"})
        for backup in backups:
            if dry_run:
                ui.info(f"[DRY RUN] Would remove backup: {backup}")
                results.append({"name": "backup", "status": "skipped", "detail": backup})
            else:
                shutil.rmtree(backup, ignore_errors=True)
                ui.success(f"Removed backup: {backup}")
                results.append({"name": "backup", "status": "ok", "detail": backup})
                if audit_log:
                    audit_log.record_file(backup, "delete", "ok", "backup removed by uninstall")

    return results


def _bootstrap_data_dir():
    """Directory where install.sh keeps its private virtual environment."""
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "mpv-config")


def _is_inside(path, directory):
    path, directory = os.path.realpath(path), os.path.realpath(directory)
    try:
        return os.path.commonpath([path, directory]) == directory
    except ValueError:  # different drives on Windows
        return False


def _is_bootstrap_venv(path):
    return os.path.isfile(os.path.join(path, "pyvenv.cfg"))


def _remove_launcher_and_install_dir(remove_install_dir=False, dry_run=False, audit_log=None):
    results = []
    default_launcher = os.path.expanduser("~/.local/bin/mpv-config")
    default_deploy_dir = os.path.expanduser("~/.mpv-config-deploy")
    data_dir = _bootstrap_data_dir()
    if os.path.lexists(default_launcher):
        # Only remove what install.sh created: a symlink into its private venv. A regular file,
        # or a link owned by another tool (pipx), is not ours to delete.
        if os.path.islink(default_launcher) and _is_inside(default_launcher, data_dir):
            if dry_run:
                ui.info(f"[DRY RUN] Would remove launcher: {default_launcher}")
                results.append({"name": "launcher", "status": "skipped", "detail": "dry run"})
            else:
                _remove_path(default_launcher)
                ui.success(f"Removed launcher: {default_launcher}")
                results.append({"name": "launcher", "status": "ok", "detail": "removed"})
                if audit_log:
                    audit_log.record_file(default_launcher, "delete", "ok", "launcher removed")
        else:
            ui.warn(f"Left {default_launcher} in place: it was not created by install.sh")
            results.append(
                {"name": "launcher", "status": "skipped", "detail": "not created by install.sh"}
            )

    if remove_install_dir and os.path.isdir(default_deploy_dir):
        if dry_run:
            ui.info(f"[DRY RUN] Would remove deploy dir: {default_deploy_dir}")
            results.append({"name": "deploy_dir", "status": "skipped", "detail": "dry run"})
        else:
            _remove_path(default_deploy_dir)
            ui.success(f"Removed deploy dir: {default_deploy_dir}")
            results.append({"name": "deploy_dir", "status": "ok", "detail": "removed"})

    venv = os.path.join(data_dir, "venv")
    if remove_install_dir and dry_run and _is_bootstrap_venv(venv):
        ui.info(f"[DRY RUN] Would remove private virtual environment: {venv}")
        results.append({"name": "venv", "status": "skipped", "detail": "dry run"})

    return results


def _remove_bootstrap_venv():
    """Delete the private venv install.sh created. Call it last: this process may run from it."""
    data_dir = _bootstrap_data_dir()
    venv = os.path.join(data_dir, "venv")
    if not _is_bootstrap_venv(venv):
        return
    ui.success(f"Removing private virtual environment: {venv}")
    try:
        shutil.rmtree(venv)
    except OSError as exc:
        ui.warn(f"Could not remove {venv}: {exc}")
        return
    try:
        os.rmdir(data_dir)
    except OSError:
        pass  # something else lives there; leave it


def cmd_uninstall(args):
    """Remove deployed files and optionally dependencies."""
    ui.banner()
    env = detect()
    config_dir = tx.config_path(env.config_dir)
    audit_log = _audit_log_for(env)
    pre_existing_pkgs = audit_log.get_pre_existing_packages()

    if args.dry_run:
        remove_results = _remove_deployed_files(
            env,
            purge_config=args.purge_config,
            remove_backups=args.remove_backups,
            dry_run=True,
        )
        cleanup_results = _remove_launcher_and_install_dir(
            remove_install_dir=args.remove_install_dir, dry_run=True
        )
        ui.summary(remove_results + cleanup_results)
        return 0

    if _is_interactive_session():
        if not ui.confirm("Are you sure you want to uninstall MPV configuration?"):
            ui.warn("Uninstall cancelled by user.")
            return 0

    with tx.operation_lock(config_dir):
        audit_log.start_session("uninstall", env)
        try:
            if not args.remove_backups and os.path.isdir(config_dir):
                backup_existing(config_dir, audit_log=audit_log)
            remove_results = _remove_deployed_files(
                env,
                purge_config=args.purge_config,
                remove_backups=args.remove_backups,
                dry_run=False,
                audit_log=audit_log,
            )
            dep_results = []
            if args.remove_deps:
                from deploy.installer import uninstall_deps

                dep_results = uninstall_deps(
                    env,
                    remove_python=getattr(args, "remove_python", False),
                    dry_run=False,
                    pre_existing_pkgs=pre_existing_pkgs,
                    audit_log=audit_log,
                )
            cleanup_results = _remove_launcher_and_install_dir(
                remove_install_dir=args.remove_install_dir, dry_run=False, audit_log=audit_log
            )
            all_results = remove_results + dep_results + cleanup_results
            ui.summary(all_results)
            if any(result.get("status") == "failed" for result in all_results):
                raise RuntimeError("Uninstall completed with failures")
            audit_log.complete_session("completed")
            if args.purge_config and os.path.lexists(config_dir):
                # The audit log lives inside the config dir and was just written back into it.
                _remove_path(config_dir)
            ui.panel("Uninstall completed.", title="Success", style="green")
        except BaseException:
            audit_log.complete_session("failed")
            raise
    if args.remove_install_dir:
        _remove_bootstrap_venv()
    return 0


def build_arg_parser():
    """Build the deployer's argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m deploy.deployer",
        description="Deploy or manage the mpv configuration managed by this repository.",
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--install",
        action="store_true",
        help="full install: detect, plan, fetch, install dependencies, deploy, verify",
    )
    action.add_argument(
        "--verify", action="store_true", help="verify the current deployment (read-only)"
    )
    action.add_argument(
        "--update", action="store_true", help="update scripts and shaders to latest versions"
    )
    action.add_argument(
        "--rollback",
        nargs="?",
        const="__latest__",
        metavar="BACKUP_PATH",
        help="restore configuration from backup (default: latest)",
    )
    action.add_argument(
        "--status", action="store_true", help="show installed script/shader versions and status"
    )
    action.add_argument(
        "--sync-deps",
        action="store_true",
        help="synchronize external dependencies (yt-dlp, ffmpeg, etc.)",
    )
    action.add_argument(
        "--uninstall", action="store_true", help="remove files deployed by this tool"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="preview changes without modifying files"
    )
    parser.add_argument(
        "--purge-config",
        action="store_true",
        help="with --uninstall: remove entire mpv config directory",
    )
    parser.add_argument(
        "--remove-backups", action="store_true", help="with --uninstall: remove backup directories"
    )
    parser.add_argument(
        "--remove-deps",
        action="store_true",
        help="with --uninstall: uninstall managed dependencies",
    )
    parser.add_argument(
        "--remove-python",
        action="store_true",
        help="with --uninstall and --remove-deps: also remove Python packages",
    )
    parser.add_argument(
        "--remove-install-dir",
        action="store_true",
        help="with --uninstall: remove deploy repository and launcher",
    )
    parser.add_argument(
        "--mpv-profile",
        choices=sorted(MPV_EXPERIENCE_PROFILES),
        default=_DEPLOY_DEFAULTS["mpv_profile"],
        help="mpv behavior profile (default: %(default)s)",
    )
    parser.add_argument(
        "--anime-preset",
        choices=list(ANIME4K_CHAINS),
        default=_DEPLOY_DEFAULTS["anime_preset"],
        help="Anime4K shader chain preset (default: %(default)s)",
    )
    parser.add_argument(
        "--scaler-tier",
        choices=list(SCALER_TIERS),
        default=_DEPLOY_DEFAULTS["scaler_tier"],
        help="scaler tier for upscaling quality (default: %(default)s)",
    )
    parser.add_argument(
        "--display-mode",
        choices=["auto", "fixed", "vrr"],
        default=_DEPLOY_DEFAULTS["display_mode"],
        help="display sync mode; auto is an alias of fixed, vrr is opt-in (default: %(default)s)",
    )
    parser.add_argument(
        "--dither-depth",
        choices=["auto", "8", "10"],
        default=_DEPLOY_DEFAULTS["dither_depth"],
        help="dither depth: mpv auto-selection or explicit 8/10 bits (default: %(default)s)",
    )
    parser.add_argument(
        "--mpv-version",
        metavar="TAG",
        default=None,
        help="override the pinned mpv Windows build tag (e.g. 2025-01-15)",
    )
    return parser


def main(argv=None):
    """Run the deployer CLI; returns the process exit code (0 ok, 1 failed, 130 interrupted)."""
    args = build_arg_parser().parse_args(argv)
    try:
        if args.install:
            return cmd_install(args)
        if args.verify:
            return cmd_verify(args)
        if args.update:
            return cmd_update(args)
        if args.rollback is not None:
            return cmd_rollback(args)
        if args.status:
            return cmd_status(args)
        if args.sync_deps:
            return cmd_sync_deps(args)
        if args.uninstall:
            return cmd_uninstall(args)
        return 0
    except KeyboardInterrupt:
        ui.warn("Interrupted by user.")
        return 130
    except Exception as exc:
        ui.error(f"Fatal error: {exc}")
        if os.getenv("DEBUG"):
            raise
        return 1


if __name__ == "__main__":
    sys.exit(main())
