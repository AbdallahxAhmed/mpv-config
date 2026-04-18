"""
verifier.py — Post-deployment verification.

Runs a comprehensive check suite to ensure everything was deployed
correctly and works as expected.
"""

import os
import subprocess
import sys

from deploy import ui


def _run_check(cmd):
    """Run a command silently, return success."""
    try:
        subprocess.run(
            cmd, capture_output=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return True
    except Exception:
        return False


def verify(config_dir, env):
    """
    Run verification checks on the deployed configuration.
    Returns list of result dicts.
    """
    ui.header("Verifying Deployment")

    results = []
    checks_passed = 0
    checks_total = 0

    def check(name, condition, detail=""):
        nonlocal checks_passed, checks_total
        checks_total += 1
        if condition:
            checks_passed += 1
            ui.success(name)
            results.append({"name": name, "status": "ok", "detail": detail})
        else:
            ui.error(name)
            results.append({"name": name, "status": "failed", "detail": detail})

    def check_file(name, rel_path):
        path = os.path.join(config_dir, rel_path)
        check(f"{name}", os.path.isfile(path), rel_path)

    def check_dir(name, rel_path, min_files=0):
        path = os.path.join(config_dir, rel_path)
        exists = os.path.isdir(path)
        count = 0
        if exists:
            count = sum(len(f) for _, _, f in os.walk(path))
        ok = exists and count >= min_files
        check(name, ok, f"{count} files" if exists else "missing")

    def check_binary(name, cmd):
        ok = _run_check(cmd)
        check(f"{name} binary", ok)

    # ─── Binary checks ──────────────────────────────────────────────

    ui.step("Checking binaries...")
    check_binary("mpv", ["mpv", "--version"])
    check_binary("ffmpeg", ["ffmpeg", "-version"])
    check_binary("yt-dlp", ["yt-dlp", "--version"])

    python_cmd = env.python_cmd
    check_binary("python", [python_cmd, "--version"])

    # Optional
    if _run_check(["ffsubsync", "--version"]):
        check("ffsubsync binary", True)
    else:
        ui.warn("ffsubsync: not found (optional)")
        results.append({"name": "ffsubsync binary", "status": "skipped", "detail": "optional"})

    # ─── Config files ────────────────────────────────────────────────

    ui.step("Checking config files...")
    check_file("mpv.conf", "mpv.conf")
    check_file("input.conf", "input.conf")

    # ─── Scripts ─────────────────────────────────────────────────────

    ui.step("Checking scripts...")
    check_dir("uosc", "scripts/uosc", min_files=1)
    # env.os is normalized by detector.py to "windows" | "linux" | "macos".
    ziggy_by_os = {"linux": "ziggy-linux", "macos": "ziggy-darwin"}
    ziggy_name = ziggy_by_os.get(env.os)
    if ziggy_name:
        rel = f"scripts/uosc/bin/{ziggy_name}"
        ziggy = os.path.join(config_dir, rel)
        check(f"uosc {ziggy_name}", os.path.isfile(ziggy), rel)
        check(f"uosc {ziggy_name} executable", os.access(ziggy, os.X_OK), "must be executable")
    check_file("thumbfast", "scripts/thumbfast.lua")
    check_file("SmartSkip", "scripts/SmartSkip.lua")
    check_file("sponsorblock", "scripts/sponsorblock.lua")
    check_file("sponsorblock.py", "scripts/sponsorblock_shared/sponsorblock.py")
    check_dir("autosubsync", "scripts/autosubsync", min_files=1)
    check_file("autoload", "scripts/autoload.lua")
    check_file("memo", "scripts/memo.lua")
    check_file("evafast", "scripts/evafast.lua")
    check_file("pause-when-minimize", "scripts/pause-when-minimize.lua")

    # ─── Shaders ─────────────────────────────────────────────────────

    ui.step("Checking shaders...")
    check_dir("Anime4K shaders", "shaders", min_files=10)

    # ─── Fonts ───────────────────────────────────────────────────────

    ui.step("Checking fonts...")
    check_dir("uosc fonts", "fonts", min_files=1)

    # ─── Script-opts ─────────────────────────────────────────────────

    ui.step("Checking script-opts...")
    check_file("uosc.conf", "script-opts/uosc.conf")
    check_file("SmartSkip.conf", "script-opts/SmartSkip.conf")
    check_file("autosubsync.conf", "script-opts/autosubsync.conf")
    check_file("evafast.conf", "script-opts/evafast.conf")
    check_file("memo.conf", "script-opts/memo.conf")

    # ─── Config content checks ───────────────────────────────────────

    ui.step("Validating config content...")

    # Check all template-generated files for unresolved placeholders
    for conf_name, conf_path in [
        ("mpv.conf", os.path.join(config_dir, "mpv.conf")),
        ("input.conf", os.path.join(config_dir, "input.conf")),
        ("autosubsync.conf", os.path.join(config_dir, "script-opts", "autosubsync.conf")),
    ]:
        if os.path.isfile(conf_path):
            with open(conf_path, "r", encoding="utf-8") as f:
                content = f.read()
            has_placeholders = "{{" in content
            check(f"{conf_name}: no unresolved placeholders", not has_placeholders,
                  f"found {{{{...}}}} in {conf_name}" if has_placeholders else "clean")

    # ─── mpv launch test ─────────────────────────────────────────────

    ui.step("Testing mpv launch...")
    mpv_ok = _run_check(["mpv", "--no-video", "--no-audio", "--frames=0", "--really-quiet"])
    check("mpv launch test", mpv_ok, "mpv runs without errors")

    # ─── Summary ─────────────────────────────────────────────────────

    print()
    if checks_passed == checks_total:
        ui.success(f"All {checks_total} checks passed! ✨")
    else:
        ui.warn(f"{checks_passed}/{checks_total} checks passed")

    return results
