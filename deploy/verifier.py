"""Structure/binary checks and a script-disabled mpv startup sanity check.

These checks do not establish real GPU, HDR, subtitle, or network playback
correctness. See docs/AUDIT.md for the manual playback validation checklist.
"""

import os
import subprocess
import sys

from deploy import ui


def _run_check(cmd):
    """Run a bounded, non-interactive command and return whether it succeeded."""
    try:
        subprocess.run(
            cmd, capture_output=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            check=True,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


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
        check(name, os.path.isdir(path), "valid directory/link" if os.path.isdir(path) else "missing or broken link")

    ui.step("Checking binaries...")
    check_binary("mpv", ["mpv", "--version"])
    check_binary("ffmpeg", ["ffmpeg", "-version"])
    if env.os == "windows":
        check_binary("ffprobe", ["ffprobe", "-version"])
        check_binary("ffplay", ["ffplay", "-version"])
    from deploy.deployer import _resolve_ytdl_path
    check_binary("yt-dlp", [_resolve_ytdl_path(env), "--version"])
    check_binary("python", [env.python_cmd, "--version"])
    # uv is an installer convenience, not a required mpv runtime dependency.
    check_binary("uv", ["uv", "--version"], optional=True)
    check_binary("ffsubsync", ["ffsubsync", "--version"], optional=True)
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
    for name in ("thumbfast", "SmartSkip", "smart-paste", "ytdl_hook", "ytdl-sub-menu", "sponsorblock", "autoload", "memo", "evafast", "pause-when-minimize"):
        check_file(name, f"scripts/{name}.lua")
    check_file("sponsorblock.py", "scripts/sponsorblock_shared/sponsorblock.py")
    check_dir("autosubsync", "scripts/autosubsync", min_files=1)

    ui.step("Checking shaders and fonts...")
    check_directory_or_link("shaders directory", "shaders")
    check_dir("Anime4K shaders", "shaders", min_files=10)
    check_dir("uosc fonts", "fonts", min_files=1)

    ui.step("Checking script-opts...")
    for name in ("uosc", "SmartSkip", "autosubsync", "evafast", "memo", "ytdl_hook", "thumbfast"):
        check_file(name + ".conf", f"script-opts/{name}.conf")

    for relative in ("mpv.conf", "input.conf", "script-opts/autosubsync.conf"):
        path = os.path.join(config_dir, relative)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as stream:
                content = "\n".join(line for line in stream if not line.lstrip().startswith("#"))
            has_placeholders = "{{" in content
            check(f"{relative}: no unresolved placeholders", not has_placeholders,
                  "unresolved template" if has_placeholders else "clean")

    ui.step("Testing selected config startup (scripts disabled)...")
    mpv_ok = _run_check([
        "mpv", f"--config-dir={os.path.abspath(config_dir)}", "--load-scripts=no",
        "--no-video", "--no-audio", "--frames=0", "--really-quiet", "--idle=no",
    ])
    check("mpv launch test", mpv_ok, "startup only; real playback/GPU not tested")
    rows = []
    for result in results:
        label = {"ok": "[green]OK[/green]", "failed": "[red]FAILED[/red]", "skipped": "[dim]SKIPPED[/dim]"}[result["status"]]
        rows.append([label, result["name"], result["detail"]])
    ui.table("Verification Results", ["Status", "Check", "Detail"], rows)
    if checks_passed == checks_total:
        ui.success(f"All {checks_total} automated checks passed; manual playback validation remains.")
    else:
        ui.warn(f"{checks_passed}/{checks_total} checks passed")
    return results
