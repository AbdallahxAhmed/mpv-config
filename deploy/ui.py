"""
ui.py — Beautiful terminal output with colors and status indicators.

Provides a consistent, clean interface for all user-facing messages.
Uses Rich if available, falling back to basic ANSI otherwise.
Handles Windows cp1252 gracefully.
"""

import sys
import os
from contextlib import contextmanager

# ─── Force UTF-8 on Windows ──────────────────────────────────────────

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # Fallback: ASCII symbols will be used

# ─── Rich Integration ─────────────────────────────────────────────────

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import Progress, BarColumn, TaskProgressColumn, TextColumn
    from rich.prompt import Confirm
    from rich.status import Status
    from rich.rule import Rule
    _RICH_AVAILABLE = True
    _console = Console()
except ImportError:
    _RICH_AVAILABLE = False
    _console = None

# ─── ANSI Fallback Infrastructure ─────────────────────────────────────

def _supports_color():
    if os.getenv("NO_COLOR"): return False
    if os.getenv("FORCE_COLOR"): return True
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
    try:
        enc = getattr(sys.stdout, "encoding", "") or ""
        return enc.lower().replace("-", "") in ("utf8", "utf16", "utf32", "utf_8")
    except Exception:
        return False

USE_COLOR = _supports_color()
USE_UNICODE = _supports_unicode()

class S:
    if USE_UNICODE:
        CHECK = "✓"; CROSS = "✗"; WARN = "!"; ARROW = ">"; INFO = "i"; BULLET = "*"; SKIP = "o"; BLOCK = "#"; LIGHT = "."
    else:
        CHECK = "+"; CROSS = "x"; WARN = "!"; ARROW = ">"; INFO = "i"; BULLET = "*"; SKIP = "o"; BLOCK = "#"; LIGHT = "."

class _C:
    if USE_COLOR:
        RESET = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"; RED = "\033[91m"; GREEN = "\033[92m"; YELLOW = "\033[93m"
        BLUE = "\033[94m"; MAGENTA = "\033[95m"; CYAN = "\033[96m"; WHITE = "\033[97m"; GRAY = "\033[90m"
    else:
        RESET = BOLD = DIM = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = GRAY = ""

def _print(text="", **kwargs):
    try:
        print(text, **kwargs)
    except UnicodeEncodeError:
        safe = text.encode("ascii", errors="replace").decode("ascii")
        print(safe, **kwargs)

# ─── Public API ───────────────────────────────────────────────────────

def banner():
    if _RICH_AVAILABLE:
        art = "[cyan][bold]+======================================================+\n|              MPV Auto-Deploy System v1.0             |\n+======================================================+[/bold][/cyan]"
        _console.print(art)
    else:
        _print(f"\n{_C.CYAN}{_C.BOLD}+======================================================+\n|              MPV Auto-Deploy System v1.0             |\n+======================================================+{_C.RESET}\n")

def header(text):
    if _RICH_AVAILABLE:
        _console.print()
        _console.print(Rule(f"[bold blue]{text}[/bold blue]", style="blue"))
        _console.print()
    else:
        _print(f"\n{_C.BOLD}{_C.BLUE}{'=' * 56}")
        _print(f"  {text}")
        _print(f"{'=' * 56}{_C.RESET}\n")

def step(text, **kwargs):
    if _RICH_AVAILABLE:
        _console.print(f"[cyan]>[/cyan] {text}", **kwargs)
    else:
        _print(f"  {_C.CYAN}{S.ARROW}{_C.RESET} {text}", **kwargs)

def success(text, **kwargs):
    if _RICH_AVAILABLE:
        _console.print(f"[green]✓[/green] {text}", **kwargs)
    else:
        _print(f"  {_C.GREEN}{S.CHECK}{_C.RESET} {text}", **kwargs)

def warn(text, **kwargs):
    if _RICH_AVAILABLE:
        _console.print(f"[yellow]![/yellow] {text}", **kwargs)
    else:
        _print(f"  {_C.YELLOW}{S.WARN}{_C.RESET} {text}", **kwargs)

def error(text, **kwargs):
    if _RICH_AVAILABLE:
        _console.print(Panel(text, title="Error", border_style="red"), **kwargs)
    else:
        _print(f"  {_C.RED}{S.CROSS}{_C.RESET} {text}", **kwargs)

def info(text, **kwargs):
    if _RICH_AVAILABLE:
        _console.print(f"[dim]ℹ[/dim] {text}", **kwargs)
    else:
        _print(f"  {_C.DIM}{S.INFO}{_C.RESET} {text}", **kwargs)

def item(name, detail="", **kwargs):
    if _RICH_AVAILABLE:
        if detail:
            _console.print(f"  [white]*[/white] {name} [dim]({detail})[/dim]", **kwargs)
        else:
            _console.print(f"  [white]*[/white] {name}", **kwargs)
    else:
        if detail:
            _print(f"    {_C.WHITE}{S.BULLET}{_C.RESET} {name} {_C.DIM}({detail}){_C.RESET}", **kwargs)
        else:
            _print(f"    {_C.WHITE}{S.BULLET}{_C.RESET} {name}", **kwargs)

def progress(current, total, name):
    pct = int((current / total) * 100) if total > 0 else 0
    bar_len = 20
    filled = int(bar_len * current / total) if total > 0 else 0
    bar = f"{S.BLOCK * filled}{S.LIGHT * (bar_len - filled)}"

    if _RICH_AVAILABLE:
        # Simple inline progress for backwards compatibility with single calls
        _print(f"\r  \033[96m{bar}\033[0m {pct:3d}% ({current}/{total}) {name}    ", end="", flush=True)
    else:
        _print(f"\r  {_C.CYAN}{bar}{_C.RESET} {pct:3d}% {_C.DIM}({current}/{total}){_C.RESET} {name}    ", end="", flush=True)

    if current == total:
        _print()

def summary(results):
    if _RICH_AVAILABLE:
        table = Table(title="Summary", box=None)
        table.add_column("Status", justify="center")
        table.add_column("Name")
        table.add_column("Detail", style="dim")
        
        ok_count = skip_count = fail_count = 0
        
        for r in results:
            if r["status"] == "ok":
                icon = "[green]✓[/green]"
                ok_count += 1
            elif r["status"] == "skipped":
                icon = "[yellow]o[/yellow]"
                skip_count += 1
            else:
                icon = "[red]✗[/red]"
                fail_count += 1
            table.add_row(icon, r["name"], r.get("detail", ""))
            
        _console.print(table)
        
        msg = f"[green]{ok_count} succeeded[/green]"
        if skip_count:
            msg += f"  [yellow]{skip_count} skipped[/yellow]"
        if fail_count:
            msg += f"  [red]{fail_count} failed[/red]"
        _console.print(msg)
    else:
        _print(f"\n{_C.BOLD}{'=' * 56}")
        _print(f"  Summary")
        _print(f"{'=' * 56}{_C.RESET}")

        ok_count = sum(1 for r in results if r["status"] == "ok")
        skip_count = sum(1 for r in results if r["status"] == "skipped")
        fail_count = sum(1 for r in results if r["status"] == "failed")

        for r in results:
            if r["status"] == "ok":
                icon = f"{_C.GREEN}{S.CHECK}{_C.RESET}"
            elif r["status"] == "skipped":
                icon = f"{_C.YELLOW}{S.SKIP}{_C.RESET}"
            else:
                icon = f"{_C.RED}{S.CROSS}{_C.RESET}"
            detail = f" {_C.DIM}-- {r.get('detail', '')}{_C.RESET}" if r.get("detail") else ""
            _print(f"  {icon} {r['name']}{detail}")

        _print(f"\n  {_C.GREEN}{ok_count} succeeded{_C.RESET}", end="")
        if skip_count:
            _print(f"  {_C.YELLOW}{skip_count} skipped{_C.RESET}", end="")
        if fail_count:
            _print(f"  {_C.RED}{fail_count} failed{_C.RESET}", end="")
        _print(f"\n{'=' * 56}\n")

def confirm(text):
    if _RICH_AVAILABLE:
        return Confirm.ask(f"[yellow]?[/yellow] {text}")
    else:
        try:
            reply = input(f"  {_C.YELLOW}?{_C.RESET} {text} [Y/n] ").strip().lower()
            return reply in ("", "y", "yes")
        except (EOFError, KeyboardInterrupt):
            print()
            return False

def ask_choice(text, choices):
    if _RICH_AVAILABLE:
        from rich.prompt import IntPrompt
        return str(IntPrompt.ask(f"[yellow]?[/yellow] {text}", choices=choices))
    else:
        while True:
            try:
                reply = input(f"  {_C.YELLOW}?{_C.RESET} {text} [{'/'.join(choices)}]: ").strip()
                if reply in choices:
                    return reply
                print(f"  {_C.RED}Invalid choice.{_C.RESET}")
            except (EOFError, KeyboardInterrupt):
                print()
                sys.exit(0)

@contextmanager
def spinner(text):
    """Show a spinner during an operation."""
    if _RICH_AVAILABLE:
        with _console.status(text) as status:
            yield status
    else:
        _print(f"  {_C.CYAN}{S.ARROW}{_C.RESET} {text} ...")
        yield None

def table(title, columns, rows):
    """Render a table."""
    if _RICH_AVAILABLE:
        t = Table(title=title)
        for col in columns:
            t.add_column(col)
        for row in rows:
            t.add_row(*[str(x) for x in row])
        _console.print(t)
    else:
        _print(f"\n{_C.BOLD}--- {title} ---{_C.RESET}")
        header_str = " | ".join(columns)
        _print(f"  {header_str}")
        _print(f"  {'-' * len(header_str)}")
        for row in rows:
            _print("  " + " | ".join(str(x) for x in row))
        _print()

def panel(text, title=None, style=None):
    """Render a panel."""
    if _RICH_AVAILABLE:
        _console.print(Panel(text, title=title, border_style=style))
    else:
        _print(f"\n{_C.BOLD}--- {title or 'Info'} ---{_C.RESET}")
        _print(f"  {text}")
        _print(f"{_C.BOLD}{'-' * (len(title or 'Info') + 8)}{_C.RESET}\n")

def get_progress():
    """Return a rich Progress object if available."""
    if _RICH_AVAILABLE:
        return Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=_console
        )
    return None
