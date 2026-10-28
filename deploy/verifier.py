"""Structure/binary checks and a script-disabled mpv startup sanity check.

These checks do not establish real GPU, HDR, subtitle, or network playback
correctness. See docs/AUDIT.md for the manual playback validation checklist.
"""

import os
import re
import shutil
import subprocess
import sys

from deploy import ui


def _run_check(cmd):
    """Run a bounded, non-interactive command and return whether it succeeded."""
    try:
        subprocess.run(
            cmd,
            capture_output=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            check=True,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _read_os_release_text():
    """Raw /etc/os-release text, '' when unusable (bootstraps no distro tricks)."""
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as stream:
            return stream.read()
    except OSError:
        return ""


# yt-dlp floor: extracts keep working only against recent builds. The
# deployer self-refreshes (registry refresh_days) — this row only REPORTS
# stale installs (old dpkg/fedora packages, missed refreshes).
_YTDLP_MINIMUM = (2025, 1, 1)


def _ytdlp_freshness_row(env):
    """Soft informational row: is the yt-dlp the hook will spawn recent?

    Returns a result row or None when yt-dlp is absent/version unparseable.
    """
    from deploy.deployer import _resolve_ytdl_path

    resolved = _resolve_ytdl_path(env)
    binary = resolved if os.path.isabs(resolved) else shutil.which(resolved) or resolved
    if not shutil.which(binary) and not os.path.isfile(binary):
        return None
    try:
        proc = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(
        r"(\d{4})\.(\d{2})\.(\d{2})",
        (proc.stdout or "") + (proc.stderr or ""),
    )
    if not match:
        return None
    version = tuple(int(part) for part in match.groups())
    row_name = f"yt-dlp recent enough (>= {'.'.join(map(str, _YTDLP_MINIMUM))})"
    label = ".".join(map(str, version))
    if version >= _YTDLP_MINIMUM:
        return {"name": row_name, "status": "ok", "detail": label}
    return {
        "name": row_name,
        "status": "skipped",
        "detail": f"installed {label} — old builds break against current YouTube; "
        "re-run the deployer to refresh (prefers the standalone GitHub binary)",
    }


def _mpv_repo_source():
    """Which repo the installed mpv came from (`pacman -Qi mpv` → 'Repository:').

    '' when pacman/mpv is unavailable or output is unparseable.
    """
    try:
        proc = subprocess.run(
            ["pacman", "-Qi", "mpv"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        return ""
    match = re.search(r"^Repository\s*:\s*(\S+)", proc.stdout or "", re.MULTILINE)
    return match.group(1) if match else ""


def _mpv_optimization_row(env):
    """Verifier row confirming the installed mpv is an x86-64-v3/v4 build.

    CachyOS rebuilds the whole extra repo for v3/v4 CPUs (cachyos-extra-v3
    carries e.g. mpv 1:0.41.0-...-x86_64_v3). pacman prefers those repos by
    pacman.conf order, so a normal CachyOS install just gets the optimized
    build — but an mpv installed earlier from plain `extra` is retained by
    `--needed` even on an optimized machine. This row confirms the good
    case and otherwise points at the exact repair command. Pure-Arch
    machines have no optimized repos: the check stays out of their way.
    (Linux/Arch mpv packages are not name-tagged 'v3' like Windows's
    mpv-x86_64-v3 assets — the repo source is the signal there.)

    Returns the result row, or None when the check does not apply.
    """
    if env.os != "linux" or env.distro != "arch":
        return None
    if not shutil.which("mpv") or not shutil.which("pacman"):
        return None
    if "cachyos" not in _read_os_release_text().lower():
        return None  # plain Arch/EndeavourOS/Manjaro: no optimized repos exist
    repo = _mpv_repo_source()
    if not repo:
        return None  # cannot read source; don't invent a verdict
    if "cachyos" in repo and ("v3" in repo or "v4" in repo):
        return {
            "name": "mpv optimized build (x86-64-v3/v4)",
            "status": "ok",
            "detail": f"installed from {repo}",
        }
    return {
        "name": "mpv optimized build (x86-64-v3/v4)",
        "status": "skipped",
        "detail": f"installed from '{repo}' — baseline build; on CachyOS run "
        "`sudo pacman -Syyu mpv` with the cachyos-v3 repos enabled to switch to "
        "the x86-64-v3 optimized build",
    }


def verify(config_dir, env):
    """Verify the explicitly selected configuration, without running its Lua scripts."""
    ui.header("Verifying Deployment")
    results = []
    checks_passed = 0
    checks_total = 0

    def check(name, condition, detail=""):
        nonlocal checks_passed, checks_total
        checks_total += 1
        if condition:
            checks_passed += 1
        results.append({"name": name, "status": "ok" if condition else "failed", "detail": detail})

    def check_file(name, rel_path):
        check(name, os.path.isfile(os.path.join(config_dir, rel_path)), rel_path)

    def check_dir(name, rel_path, min_files=0):
        path = os.path.join(config_dir, rel_path)
        exists = os.path.isdir(path)
        count = sum(len(files) for _, _, files in os.walk(path)) if exists else 0
        check(name, exists and count >= min_files, f"{count} files" if exists else "missing")

    def check_binary(name, cmd, optional=False):
        ok = _run_check(cmd)
        if optional and not ok:
            results.append({"name": f"{name} binary", "status": "skipped", "detail": "optional"})
        else:
            check(f"{name} binary", ok)

    def check_directory_or_link(name, rel_path):
        path = os.path.join(config_dir, rel_path)
        check(
            name,
            os.path.isdir(path),
            "valid directory/link" if os.path.isdir(path) else "missing or broken link",
        )

    ui.step("Checking binaries...")
    # mpv is required for playback but deliberately not fatal for deployment:
    # config deployment remains valid while the player is missing/slow to
    # install. The mpv launch test below only runs when a binary exists.
    if shutil.which("mpv") or _run_check(["mpv", "--version"]):
        check("mpv binary", True)
        from deploy.registry import MPV_MINIMUM_VERSION

        if env.mpv_version is not None:
            if env.mpv_version >= MPV_MINIMUM_VERSION:
                check(
                    f"mpv version >= {'.'.join(map(str, MPV_MINIMUM_VERSION))}",
                    True,
                    f"installed {'.'.join(map(str, env.mpv_version))}",
                )
            else:
                # Informational: the deployed config was adapted to this
                # version (newer-only options commented out), so it parses
                # and plays — the check is a nudge to upgrade, not a fault.
                results.append(
                    {
                        "name": f"mpv version >= {'.'.join(map(str, MPV_MINIMUM_VERSION))}",
                        "status": "skipped",
                        "detail": f"installed {'.'.join(map(str, env.mpv_version))} — "
                        "config adapted (newer-only options commented out); upgrade mpv, "
                        "then re-run `mpv-config install` to restore them",
                    }
                )
    else:
        results.append(
            {
                "name": "mpv binary",
                "status": "skipped",
                "detail": "not installed — config deployed without a player; install "
                "mpv and re-run `mpv-config verify`",
            }
        )
    # nvdec needs libcuda (NVIDIA userland driver) but is only wanted on
    # PURE NVIDIA Linux machines — on hybrid/Optimus layouts decode belongs
    # on the rendering iGPU (vaapi), so the notice would be noise there.
    # Informational only: mpv still plays via auto-safe fallbacks, so a
    # missing driver stack must not abort a deployment.
    if (
        env.os == "linux"
        and env.gpu_vendor == "nvidia"
        and not getattr(env, "gpu_hybrid", False)
    ):
        if getattr(env, "has_libcuda", False):
            check("cuda runtime (nvdec in-VRAM decode)", True, "libcuda available")
        else:
            results.append(
                {
                    "name": "cuda runtime (nvdec in-VRAM decode)",
                    "status": "skipped",
                    "detail": "no libcuda — install the NVIDIA userland driver "
                    "(Arch/CachyOS: sudo pacman -S nvidia-utils) and reinstall",
                }
            )
    mpv_build_row = _mpv_optimization_row(env)
    if mpv_build_row is not None:
        results.append(mpv_build_row)
    check_binary("ffmpeg", ["ffmpeg", "-version"])
    if env.os == "windows":
        check_binary("ffprobe", ["ffprobe", "-version"])
        check_binary("ffplay", ["ffplay", "-version"])
    from deploy.deployer import _resolve_ytdl_path

    check_binary("yt-dlp", [_resolve_ytdl_path(env), "--version"])
    ytdlp_fresh_row = _ytdlp_freshness_row(env)
    if ytdlp_fresh_row is not None:
        results.append(ytdlp_fresh_row)
    check_binary("python", [env.python_cmd, "--version"])
    # uv is an installer convenience, not a required mpv runtime dependency.
    check_binary("uv", ["uv", "--version"], optional=True)
    ffsubsync_bin = "ffsubsync"
    if env.os == "windows":
        candidates = [
            os.path.join(
                os.environ.get("APPDATA", ""),
                "uv",
                "tools",
                "ffsubsync",
                "Scripts",
                "ffsubsync.exe",
            ),
            os.path.join(os.environ.get("USERPROFILE", ""), ".local", "bin", "ffsubsync.exe"),
            os.path.join(
                os.environ.get("ProgramFiles", r"C:\Program Files"),
                "mpv",
                "ffsubsync",
                "ffsubsync.exe",
            ),
        ]
        for c in candidates:
            if os.path.isfile(c):
                ffsubsync_bin = c
                break
    check_binary("ffsubsync", [ffsubsync_bin, "--version"], optional=True)
    if _run_check(["alass", "--version"]) or _run_check(["alass-cli", "--version"]):
        check("alass binary", True)
    else:
        results.append({"name": "alass binary", "status": "skipped", "detail": "optional"})

    ui.step("Checking config files...")
    check_file("mpv.conf", "mpv.conf")
    check_file("input.conf", "input.conf")
    check_file("mpv.conf.user", "mpv.conf.user")

    ui.step("Checking scripts...")
    check_directory_or_link("scripts directory", "scripts")
    check_dir("uosc", "scripts/uosc", min_files=1)
    ziggy_name = {"linux": "ziggy-linux", "macos": "ziggy-darwin"}.get(env.os)
    if ziggy_name:
        relative = f"scripts/uosc/bin/{ziggy_name}"
        ziggy = os.path.join(config_dir, relative)
        check(f"uosc {ziggy_name}", os.path.isfile(ziggy), relative)
        check(f"uosc {ziggy_name} executable", os.access(ziggy, os.X_OK), "must be executable")
    for name in (
        "thumbfast",
        "SmartSkip",
        "smart-paste",
        "sub_backdrop",
        "ytdl_hook",
        "ytdl-sub-menu",
        "sponsorblock",
        "autoload",
        "memo",
        "evafast",
        "pause-when-minimize",
        "smart_motion",
        "profile_picker",
        "sub_sanitizer",
        "fast_close",
    ):
        check_file(name, f"scripts/{name}.lua")
    check_file("sponsorblock.py", "scripts/sponsorblock_shared/sponsorblock.py")
    check_dir("autosubsync", "scripts/autosubsync", min_files=1)

    ui.step("Checking shaders and fonts...")
    check_directory_or_link("shaders directory", "shaders")
    check_dir("Anime4K shaders", "shaders", min_files=10)
    check_dir("uosc fonts", "fonts", min_files=1)
    if env.os == "linux":
        xdg_data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        font_dir = os.path.join(xdg_data, "fonts", "mpv-uosc")
        has_fonts = os.path.isdir(font_dir) and any(os.scandir(font_dir))
        check("uosc fontconfig cache", has_fonts, "~/.local/share/fonts/mpv-uosc")

    ui.step("Checking script-opts...")
    for name in ("uosc", "SmartSkip", "autosubsync", "evafast", "memo", "ytdl_hook", "thumbfast"):
        check_file(name + ".conf", f"script-opts/{name}.conf")
    # stream_quality.conf only ships in full installs; a partial/manual
    # deployment without it just means ytdl_hook uses its built-in default.
    if os.path.isfile(os.path.join(config_dir, "script-opts", "stream_quality.conf")):
        with open(os.path.join(config_dir, "script-opts", "stream_quality.conf"), "r", encoding="utf-8") as stream:
            quality_content = "\n".join(line for line in stream if not line.lstrip().startswith("#"))
        has_quality_value = "default_quality=" in quality_content
        quality_value = next(
            (
                line.strip()
                for line in quality_content.splitlines()
                if line.strip().startswith("default_quality=")
            ),
            "",
        )
        check(
            "stream_quality.conf default_quality line present",
            has_quality_value,
            quality_value
            or "script-opts/stream_quality.conf is missing a default_quality=<n> line",
        )
    if os.path.isfile(os.path.join(config_dir, "script-opts", "smart_motion.conf")):
        check_file("smart_motion.conf", "script-opts/smart_motion.conf")

    for relative in ("mpv.conf", "input.conf", "script-opts/autosubsync.conf"):
        path = os.path.join(config_dir, relative)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as stream:
                content = "\n".join(line for line in stream if not line.lstrip().startswith("#"))
            has_placeholders = "{{" in content
            check(
                f"{relative}: no unresolved placeholders",
                not has_placeholders,
                "unresolved template" if has_placeholders else "clean",
            )

    ui.step("Testing selected config startup (scripts disabled)...")
    if shutil.which("mpv") is None:
        # No player installed — the launch test would fail on a missing
        # binary, not on a config problem. Everything else just verified;
        # a later `mpv-config verify` validates startup once mpv exists.
        results.append(
            {
                "name": "mpv launch test",
                "status": "skipped",
                "detail": "mpv not installed — run `mpv-config verify` after installing",
            }
        )
    else:
        mpv_ok = _run_check(
            [
                "mpv",
                f"--config-dir={os.path.abspath(config_dir)}",
                "--load-scripts=no",
                "--no-video",
                "--no-audio",
                "--frames=0",
                "--really-quiet",
                "--idle=no",
            ]
        )
        check("mpv launch test", mpv_ok, "startup only; real playback/GPU not tested")
    rows = []
    for result in results:
        label = {
            "ok": "[green]OK[/green]",
            "failed": "[red]FAILED[/red]",
            "skipped": "[dim]SKIPPED[/dim]",
        }[result["status"]]
        rows.append([label, result["name"], result["detail"]])
    ui.table("Verification Results", ["Status", "Check", "Detail"], rows)
    if checks_passed == checks_total:
        ui.success(
            f"All {checks_total} automated checks passed; manual playback validation remains."
        )
    else:
        ui.warn(f"{checks_passed}/{checks_total} checks passed")
    return results
