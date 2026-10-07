# Implementation Plan: Installer & KDE Fixes

**Branch**: `003-installer-and-kde-fixes` | **Date**: 2026-04-25
**Spec**: `specs/003-installer-and-kde-fixes/spec.md`

---

## SECTION 1 — `_print()` fix

### Root cause

`deploy/ui.py` line 76 defines:

```python
def _print(text, **kwargs):
```

`text` is a **required** positional argument. Line 273 calls `_print()` with
zero arguments → `TypeError: _print() missing 1 required positional argument: 'text'`.

This crashes when the ANSI fallback path renders a table (e.g. the
`display_plan()` call inside `cmd_install()` on a system where Rich is
available but the table fallback is hit, or any path through `ui.table()`
when `_RICH_AVAILABLE` is `False`).

### Corrected signature

```python
def _print(text="", **kwargs):
    try:
        print(text, **kwargs)
    except UnicodeEncodeError:
        safe = text.encode("ascii", errors="replace").decode("ascii")
        print(safe, **kwargs)
```

Change: make `text` default to `""` so bare `_print()` emits an empty line.

### Call sites — exhaustive list

All internal to `deploy/ui.py`. No other file calls `_print` directly
(`_print` is module-private). Every call is already correct **except**
line 273 which relies on the default being added above.

| Line | Call | Status |
|------|------|--------|
| 90 | `_print(f"...")` | OK — passes string |
| 98 | `_print(f"...")` | OK |
| 99 | `_print(f"  {text}")` | OK |
| 100 | `_print(f"...")` | OK |
| 106 | `_print(f"...")` | OK |
| 112 | `_print(f"...")` | OK |
| 118 | `_print(f"...")` | OK |
| 124 | `_print(f"...")` | OK |
| 130 | `_print(f"...")` | OK |
| 140 | `_print(f"...")` | OK |
| 142 | `_print(f"...")` | OK |
| 196 | `_print(f"...")` | OK |
| 197 | `_print(f"  Summary")` | OK |
| 198 | `_print(f"...")` | OK |
| 212 | `_print(f"...")` | OK |
| 214 | `_print(f"...", end="")` | OK — `**kwargs` passes `end` through |
| 216 | `_print(f"...", end="")` | OK |
| 218 | `_print(f"...", end="")` | OK |
| 219 | `_print(f"...")` | OK |
| 254 | `_print(f"...")` | OK |
| 267 | `_print(f"...")` | OK |
| 269 | `_print(f"...")` | OK |
| 270 | `_print(f"...")` | OK |
| 272 | `_print("  " + ...)` | OK |
| **273** | **`_print()`** | **BUG — no args → TypeError. Fixed by default `text=""`** |
| 280 | `_print(f"...")` | OK |
| 281 | `_print(f"...")` | OK |
| 282 | `_print(f"...")` | OK |

**Files to edit**: `deploy/ui.py` line 76 only (change `text` → `text=""`).

---

## SECTION 2 — Rich bootstrap guard

### Exact location in `setup.py`

The guard must go **after** `sys.path.insert` (current line 31) and
**before** all `from deploy import ...` statements (current lines 33–44).

Current lines 29–44:

```python
# line 30
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# line 31
sys.path.insert(0, SCRIPT_DIR)
# line 33  ← CRASH POINT if rich missing
from deploy import ui
```

### Replacement block (lines 29–44 become)

```python
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# ── Rich bootstrap guard ───────────────────────────────────────
# Rich is needed by deploy.ui. If it is missing we must install it
# BEFORE importing anything from deploy/.
def _bootstrap_rich():
    """Install rich via system package manager or isolated venv, then re-exec."""
    import subprocess, platform

    # ── Try system package manager first ────────────────────────
    if sys.platform != "win32":
        try:
            with open("/etc/os-release") as f:
                os_release = f.read().lower()
        except FileNotFoundError:
            os_release = ""

        if "arch" in os_release or "cachyos" in os_release or "endeavour" in os_release:
            print("[bootstrap] Trying: sudo pacman -S --noconfirm python-rich")
            rc = subprocess.call(
                ["sudo", "pacman", "-S", "--noconfirm", "--needed", "python-rich"]
            )
            if rc == 0:
                # Verify import works after system install
                try:
                    import rich as _test  # noqa: F811
                    return  # success — continue in this process
                except ImportError:
                    pass

        elif any(d in os_release for d in ("ubuntu", "debian", "mint", "pop")):
            print("[bootstrap] Trying: sudo apt install -y python3-rich")
            rc = subprocess.call(["sudo", "apt", "install", "-y", "python3-rich"])
            if rc == 0:
                try:
                    import rich as _test  # noqa: F811
                    return
                except ImportError:
                    pass

    # ── Venv fallback ───────────────────────────────────────────
    venv_dir = os.path.expanduser("~/.local/share/mpv-config/venv")
    venv_python = (
        os.path.join(venv_dir, "Scripts", "python.exe")
        if sys.platform == "win32"
        else os.path.join(venv_dir, "bin", "python")
    )
    venv_pip = (
        os.path.join(venv_dir, "Scripts", "pip.exe")
        if sys.platform == "win32"
        else os.path.join(venv_dir, "bin", "pip")
    )

    # Create or recreate venv if stale
    needs_create = True
    if os.path.isdir(venv_dir) and os.path.isfile(venv_python):
        # Check if rich is already importable inside existing venv
        r = subprocess.run(
            [venv_python, "-c", "import rich"],
            capture_output=True,
        )
        if r.returncode == 0:
            # Rich available in venv — re-exec into it
            print("[bootstrap] Rich found in existing venv. Re-executing...")
            os.execv(venv_python, [venv_python] + sys.argv)
        else:
            # Venv exists but rich broken — recreate
            import shutil
            shutil.rmtree(venv_dir, ignore_errors=True)

    if needs_create:
        print(f"[bootstrap] Creating venv at {venv_dir} ...")
        import venv as _venv_mod
        _venv_mod.create(venv_dir, with_pip=True)

    # pip install inside venv (ONLY place pip runs outside a venv is never)
    print("[bootstrap] Installing rich inside venv ...")
    subprocess.check_call([venv_pip, "install", "--quiet", "rich>=13.0.0"])

    # Re-exec setup.py under the venv python
    print("[bootstrap] Re-executing under venv python ...")
    os.execv(venv_python, [venv_python] + sys.argv)


try:
    import rich  # noqa: F401
except ImportError:
    _bootstrap_rich()

# ── Now safe to import deploy modules ───────────────────────────
from deploy import ui
from deploy.registry import SCRIPTS, SHADERS, MPV_EXPERIENCE_PROFILES, MPV_PROFILE_DEFAULT
from deploy.detector import detect
from deploy.installer import install_deps, uninstall_deps
from deploy.fetcher import fetch_all
from deploy.deployer import deploy, rollback_config, list_backups, _remove_path as remove_path_safe
from deploy.verifier import verify
from deploy.audit_log import AuditLog
from deploy.planner import (
    build_install_plan, build_update_plan, build_uninstall_plan,
    display_plan, confirm_plan,
)
```

### Key properties

- All `print()` calls use plain `print()` — no Rich, no `ui.*`.
- The `os.execv` call replaces the current process; it does not return.
- If system package install succeeds, no venv is created — the function
  returns and the existing process continues.
- If the venv already exists but Rich is broken inside it, the venv is
  deleted and recreated.
- `pip` is **only** invoked via the venv's own `pip` executable, never
  system-wide.

---

## SECTION 3 — Dependency category split

### 3.1  `deploy/registry.py` — updated `SYSTEM_DEPS`

Replace lines 156–196 entirely:

```python
SYSTEM_DEPS = {
    # ── Category A — CLI executables ── NEVER pip ──────────────
    "mpv": {
        "windows": {"method": "winget", "id": "mpv-player.mpv"},
        "arch":    {"method": "pacman", "pkg": "mpv"},
        "ubuntu":  {"method": "apt",    "pkg": "mpv"},
        "fedora":  {"method": "dnf",    "pkg": "mpv"},
        "macos":   {"method": "brew",   "pkg": "mpv"},
        "verify":  ["mpv", "--version"],
    },
    "yt-dlp": {
        "windows": {"method": "winget", "id": "yt-dlp.yt-dlp"},
        "arch":    {"method": "pacman", "pkg": "yt-dlp"},
        "ubuntu":  {"method": "apt",    "pkg": "yt-dlp"},        # was pip
        "fedora":  {"method": "dnf",    "pkg": "yt-dlp"},
        "macos":   {"method": "brew",   "pkg": "yt-dlp"},
        "verify":  ["yt-dlp", "--version"],
    },
    "ffmpeg": {
        "windows": {"method": "winget", "id": "Gyan.FFmpeg"},
        "arch":    {"method": "pacman", "pkg": "ffmpeg"},
        "ubuntu":  {"method": "apt",    "pkg": "ffmpeg"},
        "fedora":  {"method": "dnf",    "pkg": "ffmpeg"},
        "macos":   {"method": "brew",   "pkg": "ffmpeg"},
        "verify":  ["ffmpeg", "-version"],
    },
    "python": {
        "windows": {"method": "winget",  "id": "Python.Python.3.11"},
        "arch":    {"method": "pacman",  "pkg": "python"},
        "ubuntu":  {"method": "apt",     "pkg": "python3"},
        "fedora":  {"method": "dnf",     "pkg": "python3"},
        "macos":   {"method": "brew",    "pkg": "python@3"},
        "verify":  ["python", "--version"],
        "verify_alt": ["python3", "--version"],
    },
    "ffsubsync": {
        "arch":    {"method": "aur", "pkg": "ffsubsync"},         # was pip+break-system-packages
        "ubuntu":  {"method": "apt", "pkg": "ffsubsync"},
        "fedora":  {"method": "dnf", "pkg": "ffsubsync"},
        "macos":   {"method": "brew", "pkg": "ffsubsync"},
        "windows": {"method": "winget", "id": "ffsubsync"},       # fallback manual if missing
        "verify":  ["ffsubsync", "--version"],
    },
    "alass": {
        "arch":    {"method": "aur", "pkg": "alass-bin", "fallback_pkg": "alass"},
        "windows": {"method": "manual", "url": "https://github.com/kaegi/alass/releases"},
        "verify":  ["alass", "--version"],
    },
}
```

### 3.2  Lines containing `--break-system-packages` — DELETE

| File | Line | Content | Action |
|------|------|---------|--------|
| `deploy/registry.py` | 188 | `"arch": {"method": "pip", "pkg": "ffsubsync", "flags": ["--user", "--break-system-packages"]}` | Replace with `{"method": "aur", "pkg": "ffsubsync"}` |

That is the **only** occurrence in the codebase (confirmed via grep).

### 3.3  Lines using `method: "pip"` for Category A tools — DELETE

| File | Line | Current | Replacement |
|------|------|---------|-------------|
| `deploy/registry.py` | 167 | `"ubuntu": {"method": "pip", "pkg": "yt-dlp"}` | `"ubuntu": {"method": "apt", "pkg": "yt-dlp"}` |
| `deploy/registry.py` | 187 | `"all": {"method": "pip", "pkg": "ffsubsync"}` | **Delete** this `"all"` fallback; add per-platform entries instead |

### 3.4  `deploy/installer.py` — remove `_get_pip_args` and pip code path

After the registry changes above, no Category A dependency uses
`method: "pip"` on any platform. The entire pip install machinery in
`installer.py` is now dead code for Category A tools:

- Lines 36–94: `_get_pip_args()` — **delete entirely** (or keep only if
  you want a future Category B venv helper; for now it is unused).
- Lines 121–138: the `elif method == "pip":` branch in `_install_one()` —
  **delete entirely**.
- Lines 223–228: the `elif method == "pip":` branch in `_uninstall_one()` —
  **delete entirely**.
- Lines 163–202: `_prepare_ffsubsync_build()` — **delete entirely**
  (ffsubsync is now installed from AUR/apt, not compiled from pip).
- Line 15: `FFSUBSYNC_SETUPTOOLS_PIN = "setuptools<74.0"` — **delete**.

Add a `"dnf"` handler to both `_install_one` and `_uninstall_one`:

```python
elif method == "dnf":
    return _run(["sudo", "dnf", "install", "-y", info["pkg"]])
```

```python
elif method == "dnf":
    return _run(["sudo", "dnf", "remove", "-y", info["pkg"]], check=False)
```

### 3.5  Category B (rich) — handled in `setup.py` bootstrap

Rich is the only Category B dependency. Its installation is fully
handled by the `_bootstrap_rich()` function in Section 2. The strategy:

1. Check system package manager first:
   - Arch: `sudo pacman -S --noconfirm --needed python-rich`
   - Debian/Ubuntu: `sudo apt install -y python3-rich`
2. If system package unavailable or failed: create venv at
   `~/.local/share/mpv-config/venv`, run `pip install rich>=13.0.0`
   **inside the venv only**, then `os.execv` re-exec.

Rich does **not** appear in `SYSTEM_DEPS` — it is not a CLI executable
and is not managed by `install_deps()`.

### 3.6  `install.sh` — fix bare pip calls

Lines 196–197 currently run system-wide pip. Replace with:

```bash
# ── Step 3b: Install rich (Category B) ─────────────────────────
# Try system package first, venv fallback handled by setup.py bootstrap
if command -v pacman &>/dev/null; then
    _gum_spin "Installing python-rich via pacman..." \
        sudo pacman -S --noconfirm --needed python-rich 2>/dev/null || true
elif command -v apt &>/dev/null; then
    _gum_spin "Installing python3-rich via apt..." \
        sudo apt install -y -qq python3-rich 2>/dev/null || true
elif command -v brew &>/dev/null; then
    _gum_spin "Installing rich via brew..." \
        brew install python-rich 2>/dev/null || true
fi

# If the above failed, setup.py's bootstrap guard will handle venv fallback
if ! $PYTHON -c "import rich" 2>/dev/null; then
    _styled_echo "dim" "  → rich not available as system package; setup.py will bootstrap via venv"
fi
```

Delete the old lines 196–197 entirely. Also delete line 196's
`pip install ... setuptools ... wheel` call — ffsubsync no longer needs
build-from-source.

### 3.7  Decision tree summary

```
Category A tool needed?
├─ Arch Linux
│  ├─ In official repos (mpv, yt-dlp, ffmpeg, python)? → pacman
│  └─ AUR only (ffsubsync, alass)?                     → paru
├─ Debian/Ubuntu                                        → apt
├─ Fedora                                               → dnf
├─ macOS                                                → brew
└─ Windows                                              → winget

Category B library needed (rich)?
├─ System package available?
│  ├─ Arch  → pacman -S python-rich
│  └─ Debian → apt install python3-rich
├─ System package failed/unavailable?
│  └─ Create venv at ~/.local/share/mpv-config/venv
│     ├─ pip install rich>=13.0.0 (inside venv ONLY)
│     └─ os.execv re-exec setup.py under venv python
└─ pip outside venv? → NEVER
```

---

## SECTION 4 — mpv config changes

### 4.1  `config/input.conf.template` — window close binding

Add these two lines at the end of the "useful shortcuts" section
(after line 104, before line 106):

```text
# ── Window close ── ensure WM close button kills mpv instantly ──
CLOSE_WIN quit
```

`CLOSE_WIN` is mpv's pseudo-key emitted when the window manager sends
a close event (clicking the X button on KDE). On Windows, mpv already
handles this natively. On KDE Wayland/X11, explicitly binding it to
`quit` ensures immediate termination.

> **Note on `MBTN_CLOSE`**: This key name does not exist in mpv's input
> system. The correct key is `CLOSE_WIN`. The spec's mention of
> `MBTN_CLOSE` was a naming error — the mouse-button family is
> `MBTN_LEFT`, `MBTN_RIGHT`, `MBTN_MID`, `MBTN_BACK`, `MBTN_FORWARD`.
> Window close comes through as `CLOSE_WIN`.

### 4.2  `config/mpv.conf.template` — fullscreen fix

Add the following block after the `force-window` line (after current
line 20), inside the general settings section:

```ini
# ── KDE Plasma fullscreen synchronization ────────────────────────
# On Wayland, tell mpv to use its own fullscreen mechanism rather than
# relying solely on the compositor. This keeps mpv's internal
# 'fullscreen' property in sync with the actual window state, which
# in turn keeps the uosc fullscreen button icon correct.
native-fs               = no
```

Additionally, add the following template variable block (Linux-only,
injected by the deployer via `{{LINUX_VISUAL_TUNING}}`):

In the `LINUX_VISUAL_TUNING` template expansion in `deploy/deployer.py`,
add (this is the existing injection point at line 56 of the template):

```ini
# ── Window geometry helpers (does NOT control snap) ──────────────
geometry                = 50%x50%
autofit-larger          = 90%x90%
autofit-smaller         = 30%x30%
```

### 4.3  Scope boundary: window snap

> **Window snap is KDE compositor scope — NOT mpv.**
>
> Window snap preview (the translucent guide shown when dragging a
> window toward screen edges) is provided by KWin on KDE Plasma and
> by DWM on Windows. mpv has zero control over this behavior.
>
> **This is explicitly OUT OF SCOPE for mpv configuration changes.**
>
> mpv options that **partially help** with initial window sizing:
>
> | Option | Effect |
> |--------|--------|
> | `geometry=50%x50%` | Set initial window size to 50% of screen |
> | `autofit-larger=90%x90%` | Prevent window from exceeding 90% of screen |
> | `autofit-smaller=30%x30%` | Prevent window from being too small |
>
> These are convenience options for initial window placement. They do
> **not** replicate, control, or influence the OS-level snap grid.
> Snap behavior is entirely controlled by the desktop environment's
> compositor settings (KDE System Settings → Window Management →
> Window Behavior → Screen Edges).

---

## Constitution compliance check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Boundary Separation | ✅ | KDE fixes in `config/` only; bootstrap in `setup.py` only |
| II. Cross-Platform Parity | ✅ | `CLOSE_WIN quit` is harmless on Windows; geometry opts are template-injected |
| III. Dependency Classification | ✅ | All Category A → OS pkg mgr; Category B → system pkg then venv |
| IV. Shell Compatibility | ✅ | `install.sh` changes use existing `_gum_spin`/`_styled_echo` wrappers |
| V. Aesthetic CLI UX | ✅ | Bootstrap uses plain `print()` only during the Rich-unavailable window |
| VI. User Customization | ✅ | No user files overwritten without backup |
| VII. Idempotent & Safe | ✅ | Bootstrap detects existing venv; pacman `--needed` is idempotent |

---

## Files modified (complete list)

| File | Changes |
|------|---------|
| `deploy/ui.py` | Line 76: `text` → `text=""` |
| `setup.py` | Lines 29–44: replace imports with bootstrap guard + guarded imports |
| `deploy/registry.py` | Lines 156–196: full SYSTEM_DEPS rewrite (no pip for Cat A, no break-system-packages) |
| `deploy/installer.py` | Delete `_get_pip_args`, `_prepare_ffsubsync_build`, pip branches; add dnf handler |
| `install.sh` | Lines 196–197: replace bare pip with system-pkg-then-fallback |
| `config/input.conf.template` | Add `CLOSE_WIN quit` binding |
| `config/mpv.conf.template` | Add `native-fs=no`; geometry/autofit in LINUX_VISUAL_TUNING |
