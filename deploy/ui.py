"""
ui.py — Beautiful terminal output with colors and status indicators.

Provides a consistent, clean interface for all user-facing messages
without any external dependencies. Handles Windows cp1252 gracefully.
"""

import sys
import os

# ─── Force UTF-8 on Windows ──────────────────────────────────────────

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # Fallback: ASCII symbols will be used

# ─── ANSI Color Support Detection ─────────────────────────────────────

def _supports_color():
    """Detect if the terminal supports ANSI colors."""
    if os.getenv("NO_COLOR"):
        return False
    if os.getenv("FORCE_COLOR"):
        return True
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except Exception:
            return os.getenv("WT_SESSION") is not None
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

def _supports_unicode():
    """Check if stdout can handle unicode."""
    try:
        enc = getattr(sys.stdout, "encoding", "") or ""
        return enc.lower().replace("-", "") in ("utf8", "utf16", "utf32", "utf_8")
    except Exception:
        return False

USE_COLOR = _supports_color()
USE_UNICODE = _supports_unicode()

# ─── Symbols ──────────────────────────────────────────────────────────

class S:
    """Symbols with ASCII fallbacks."""
    if USE_UNICODE:
        CHECK    = "✓"
        CROSS    = "✗"
        WARN     = "!"
        ARROW    = ">"
        INFO     = "i"
        BULLET   = "*"
        SKIP     = "o"
        BLOCK    = "#"
        LIGHT    = "."
        STAR     = "*"
    else:
        CHECK    = "+"
        CROSS    = "x"
        WARN     = "!"
        ARROW    = ">"
        INFO     = "i"
        BULLET   = "*"
        SKIP     = "o"
        BLOCK    = "#"
        LIGHT    = "."
        STAR     = "*"

# ─── Color Codes ──────────────────────────────────────────────────────

class C:
    """ANSI color codes, empty strings if unsupported."""
    if USE_COLOR:
        RESET   = "\033[0m"
        BOLD    = "\033[1m"
        DIM     = "\033[2m"
        RED     = "\033[91m"
        GREEN   = "\033[92m"
        YELLOW  = "\033[93m"
        BLUE    = "\033[94m"
        MAGENTA = "\033[95m"
        CYAN    = "\033[96m"
        WHITE   = "\033[97m"
        GRAY    = "\033[90m"
    else:
        RESET = BOLD = DIM = RED = GREEN = YELLOW = ""
        BLUE = MAGENTA = CYAN = WHITE = GRAY = ""

# ─── Safe Print ───────────────────────────────────────────────────────

def _print(text, **kwargs):
    """Print with encoding error handling."""
    try:
        print(text, **kwargs)
    except UnicodeEncodeError:
        # Fallback: strip non-ASCII
        safe = text.encode("ascii", errors="replace").decode("ascii")
        print(safe, **kwargs)

# ─── Output Functions ─────────────────────────────────────────────────

def banner():
    """Print the startup banner."""
    _print(f"""
{C.CYAN}{C.BOLD}+======================================================+
|              MPV Auto-Deploy System v1.0             |
+======================================================+{C.RESET}
""")

def header(text):
    """Print a section header."""
    _print(f"\n{C.BOLD}{C.BLUE}{'=' * 56}")
    _print(f"  {text}")
    _print(f"{'=' * 56}{C.RESET}\n")

def step(text):
    """Print a step indicator."""
    _print(f"  {C.CYAN}{S.ARROW}{C.RESET} {text}")

def success(text):
    """Print a success message."""
    _print(f"  {C.GREEN}{S.CHECK}{C.RESET} {text}")

def warn(text):
    """Print a warning message."""
    _print(f"  {C.YELLOW}{S.WARN}{C.RESET} {text}")

def error(text):
    """Print an error message."""
    _print(f"  {C.RED}{S.CROSS}{C.RESET} {text}")

def info(text):
    """Print an info message."""
    _print(f"  {C.DIM}{S.INFO}{C.RESET} {text}")

def item(name, detail=""):
    """Print a list item."""
    if detail:
        _print(f"    {C.WHITE}{S.BULLET}{C.RESET} {name} {C.DIM}({detail}){C.RESET}")
    else:
        _print(f"    {C.WHITE}{S.BULLET}{C.RESET} {name}")

def progress(current, total, name):
    """Print a progress indicator."""
    pct = int((current / total) * 100) if total > 0 else 0
    bar_len = 20
    filled = int(bar_len * current / total) if total > 0 else 0
    bar = f"{S.BLOCK * filled}{S.LIGHT * (bar_len - filled)}"
    try:
        print(f"\r  {C.CYAN}{bar}{C.RESET} {pct:3d}% {C.DIM}({current}/{total}){C.RESET} {name}    ", end="", flush=True)
    except UnicodeEncodeError:
        print(f"\r  {bar} {pct:3d}% ({current}/{total}) {name}    ", end="", flush=True)
    if current == total:
        print()

def summary(results):
    """Print a final summary table of results."""
    _print(f"\n{C.BOLD}{'=' * 56}")
    _print(f"  Summary")
    _print(f"{'=' * 56}{C.RESET}")

    ok_count = sum(1 for r in results if r["status"] == "ok")
    skip_count = sum(1 for r in results if r["status"] == "skipped")
    fail_count = sum(1 for r in results if r["status"] == "failed")

    for r in results:
        if r["status"] == "ok":
            icon = f"{C.GREEN}{S.CHECK}{C.RESET}"
        elif r["status"] == "skipped":
            icon = f"{C.YELLOW}{S.SKIP}{C.RESET}"
        else:
            icon = f"{C.RED}{S.CROSS}{C.RESET}"
        detail = f" {C.DIM}-- {r.get('detail', '')}{C.RESET}" if r.get("detail") else ""
        _print(f"  {icon} {r['name']}{detail}")

    _print(f"\n  {C.GREEN}{ok_count} succeeded{C.RESET}", end="")
    if skip_count:
        _print(f"  {C.YELLOW}{skip_count} skipped{C.RESET}", end="")
    if fail_count:
        _print(f"  {C.RED}{fail_count} failed{C.RESET}", end="")
    _print(f"\n{'=' * 56}\n")

def confirm(text):
    """Ask for user confirmation. Returns True/False."""
    try:
        reply = input(f"  {C.YELLOW}?{C.RESET} {text} [Y/n] ").strip().lower()
        return reply in ("", "y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
