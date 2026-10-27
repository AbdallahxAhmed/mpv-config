"""
ui.py — Beautiful terminal output with colors and status indicators.

Provides a consistent, clean interface for all user-facing messages.
Uses Rich if available, falling back to basic ANSI otherwise.
Handles Windows cp1252 gracefully.
"""

import os
import sys
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
    from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn
    from rich.prompt import Confirm
    from rich.rule import Rule
    from rich.table import Table

    _RICH_AVAILABLE = True
    _console = Console()
except ImportError:
    _RICH_AVAILABLE = False
    _console = None

# ─── ANSI Fallback Infrastructure ─────────────────────────────────────


def _supports_color():
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
    try:
        enc = getattr(sys.stdout, "encoding", "") or ""
        return enc.lower().replace("-", "") in ("utf8", "utf16", "utf32", "utf_8")
    except Exception:
        return False


USE_COLOR = _supports_color()
USE_UNICODE = _supports_unicode()


class S:
    if USE_UNICODE:
        CHECK = "✓"
        CROSS = "✗"
        WARN = "!"
        ARROW = ">"
        INFO = "i"
        BULLET = "*"
        SKIP = "o"
        BLOCK = "#"
        LIGHT = "."
    else:
        CHECK = "+"
        CROSS = "x"
        WARN = "!"
        ARROW = ">"
        INFO = "i"
        BULLET = "*"
        SKIP = "o"
        BLOCK = "#"
        LIGHT = "."


class _C:
    if USE_COLOR:
        RESET = "\033[0m"
        BOLD = "\033[1m"
        DIM = "\033[2m"
        RED = "\033[91m"
        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        BLUE = "\033[94m"
        MAGENTA = "\033[95m"
        CYAN = "\033[96m"
        WHITE = "\033[97m"
        GRAY = "\033[90m"
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
        _print(
            f"\n{_C.CYAN}{_C.BOLD}+======================================================+\n|              MPV Auto-Deploy System v1.0             |\n+======================================================+{_C.RESET}\n"
        )


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
            _print(
                f"    {_C.WHITE}{S.BULLET}{_C.RESET} {name} {_C.DIM}({detail}){_C.RESET}", **kwargs
            )
        else:
            _print(f"    {_C.WHITE}{S.BULLET}{_C.RESET} {name}", **kwargs)


def progress(current, total, name):
    pct = int((current / total) * 100) if total > 0 else 0
    bar_len = 20
    filled = int(bar_len * current / total) if total > 0 else 0
    bar = f"{S.BLOCK * filled}{S.LIGHT * (bar_len - filled)}"

    if _RICH_AVAILABLE:
        # Simple inline progress for backwards compatibility with single calls
        _print(
            f"\r  \033[96m{bar}\033[0m {pct:3d}% ({current}/{total}) {name}    ", end="", flush=True
        )
    else:
        _print(
            f"\r  {_C.CYAN}{bar}{_C.RESET} {pct:3d}% {_C.DIM}({current}/{total}){_C.RESET} {name}    ",
            end="",
            flush=True,
        )

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
        _print("  Summary")
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


def is_interactive():
    """True when stdin is a TTY — i.e. safe to prompt without an EOF crash."""
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def confirm(text):
    if _RICH_AVAILABLE:
        try:
            return Confirm.ask(f"[yellow]?[/yellow] {text}")
        except (EOFError, KeyboardInterrupt):
            # Piped sessions (curl | bash) cannot answer prompts; treat as
            # "no" instead of crashing with "Fatal error: EOF when reading a line".
            print()
            return False
    else:
        try:
            reply = input(f"  {_C.YELLOW}?{_C.RESET} {text} [Y/n] ").strip().lower()
            return reply in ("", "y", "yes")
        except (EOFError, KeyboardInterrupt):
            print()
            return False


def ask_choice(text, choices, default=None):
    """Ask the user to pick one of ``choices``; Enter accepts ``default``.

    ``default`` (when given) must be one of ``choices`` and is the pre-selected
    answer shown with the prompt. Invalid input re-prompts. Under the plain
    (non-rich) fallback, EOF/Ctrl+C exits with status 0 — callers that want to
    keep their own default must catch (EOFError, KeyboardInterrupt).
    """
    if default is not None and default not in choices:
        raise ValueError(f"default {default!r} is not one of {list(choices)}")
    if _RICH_AVAILABLE:
        from rich.prompt import Prompt

        if default is not None:
            return str(Prompt.ask(f"[yellow]?[/yellow] {text}", choices=choices, default=default))
        return str(Prompt.ask(f"[yellow]?[/yellow] {text}", choices=choices))
    while True:
        try:
            reply = input(f"  {_C.YELLOW}?{_C.RESET} {text} [{'/'.join(choices)}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if not reply and default is not None:
            return default
        if reply in choices:
            return reply
        print(f"  {_C.RED}Invalid choice.{_C.RESET}")


# ─── Numbered Menu (install-time preset pickers) ─────────────────────


def _ensure_windows_vt():
    """Best-effort enable of VT sequences on the Windows console (redraw needs them)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass


def _menu_legend(items, default_index):
    """Footer hint line; ASCII arrow words when the terminal is not UTF-8."""
    up, down = ("↑", "↓") if USE_UNICODE else ("Up", "Down")
    default_value = items[default_index][0]
    return (
        f"  Use {up}/{down} arrows + Enter, or press 1-{len(items)} directly "
        f"(Esc = default {default_value})"
    )


def _menu_rows(items, highlight_index):
    """The numbered menu rows; highlight formatting is fixed-width per row so
    an in-place repaint overwrites cleanly. Colors degrade to plain text."""
    width = max(len(value) for value, _label in items)
    rows = []
    for index, (value, label) in enumerate(items):
        cursor = f"{index + 1}) {value:<{width}}"
        if index == highlight_index:
            rows.append(f"  {_C.CYAN}{_C.BOLD}>{_C.RESET} {_C.CYAN}{cursor}{_C.RESET} {label}")
        else:
            rows.append(f"    {_C.WHITE}{cursor}{_C.RESET} {_C.DIM}{label}{_C.RESET}")
    return rows


def _menu_frame(items, highlight_index, default_index):
    """Item rows + the legend BELOW them as the final frame line.

    The frame emits exactly ``len(items)`` newlines (rows joined, one break
    before the legend, no trailing newline) and the cursor rests at the END
    of the legend line — _repaint_menu climbs up by exactly this newline
    count to land back on row 1, and the menu repaint test pins the
    equality so the pair can never drift.
    Also shared by the line fallback, where the layout is identical."""
    clear = "\x1b[K" if USE_COLOR else ""
    rows = "\n".join(row + clear for row in _menu_rows(items, highlight_index))
    return f"{rows}\n{_C.DIM}{_menu_legend(items, default_index)}{clear}{_C.RESET}"


def _repaint_menu(items, highlight_index, default_index):
    """Redraw the frame in place: climb from the end of the legend line up
    by exactly the newline count the frame emitted (one per frame line),
    then re-print it. A non-color terminal cannot move the cursor, so it
    scroll re-prints for readability."""
    frame = _menu_frame(items, highlight_index, default_index)
    if not USE_COLOR:
        _print(frame)
        return
    climb = frame.count("\n")
    # A single-row menu would emit \x1b[0A, which some emulations treat as a
    # misleading "up one line" — keep the ambiguous case out of the stream.
    if climb:
        _print(f"\x1b[{climb}A\r", end="")
    _print(frame, end="")


def _windows_key_reader():
    """Single-keystroke reader for the Windows console (no state to restore)."""
    import msvcrt

    _ensure_windows_vt()

    def read_key():
        char = msvcrt.getwch()
        if char in ("\x00", "\xe0"):
            return {"H": "up", "P": "down"}.get(msvcrt.getwch())
        if char in ("\r", "\n"):
            return "enter"
        if char == "\x1b":
            return "esc"
        if char == "\x03":
            raise KeyboardInterrupt
        return char  # digits "1".."N"; anything else is ignored by the menu loop

    return read_key


def _posix_key_reader():
    """Single-keystroke reader in cbreak mode; arrow keys arrive as CSI sequences.

    Returns the reader plus a state-restore callable so the terminal
    re-enters cooked mode once the menu loop ends."""
    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    def read_key():
        first = sys.stdin.read(1)
        if first == "":
            raise EOFError
        if first in ("\r", "\n"):
            return "enter"
        if first == "\x1b":
            # A bare Esc starts no CSI sequence: nothing follows within the
            # window, so treat it as Esc rather than hanging on read().
            if not select.select([sys.stdin], [], [], 0.05)[0]:
                return "esc"
            if sys.stdin.read(1) != "[":
                return "esc"
            return {"A": "up", "B": "down"}.get(sys.stdin.read(1))
        return first

    def restore():
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, original)
        except Exception:
            pass

    return read_key, restore


def _make_raw_key_reader():
    """Single-keystroke reader for an interactive console plus its state restore.

    Returns ``(None, None)`` unless BOTH stdin and stdout are a TTY — piped
    stdin and unit tests fall through to the line fallback. Any failure
    resolving a platform reader also degrades to the fallback."""
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return None, None
        if sys.platform == "win32":
            return _windows_key_reader(), None
        return _posix_key_reader()
    except Exception:
        return None, None


def _resolve_menu_reply(reply, items, default_index):
    """Index selected by a typed fallback reply, or None when invalid.

    Enter (an empty reply) accepts ``default_index``; a 1-based row number
    picks that row directly; the preset name itself works too, case-insensitive."""
    reply = (reply or "").strip()
    if not reply:
        return default_index
    if reply.isdigit():
        index = int(reply) - 1
        return index if 0 <= index < len(items) else None
    lower = reply.lower()
    for index, (value, _label) in enumerate(items):
        if value.lower() == lower:
            return index
    return None


def _keep_default(default_value):
    """Warn + release the default row per the shared cancel contract."""
    _print()
    warn(f"No selection made; keeping {default_value} (default).")
    return default_value


def _run_keystroke_menu(text, items, default_index, read_key):
    """Repainting menu driven by single keystrokes from ``read_key``.

    The static head is just the question line; the frame below it carries
    the rows with the legend as its final line. _repaint_menu restarts
    exactly at the frame's top edge, so the never-touch-the-head rule keeps
    the whole session visually stable."""
    highlight_index = default_index
    _print(f"  {_C.YELLOW}?{_C.RESET} {_C.BOLD}{text}{_C.RESET}")
    _print(_menu_frame(items, highlight_index, default_index), end="")
    while True:
        key = read_key()
        if key in ("up", "down"):
            direction = 1 if key == "down" else -1
            highlight_index = (highlight_index + direction) % len(items)
            _repaint_menu(items, highlight_index, default_index)
        elif key == "enter":
            _print()
            return items[highlight_index][0]
        elif key == "esc":
            return _keep_default(items[default_index][0])
        elif isinstance(key, str) and key.isdigit():
            index = int(key) - 1
            if 0 <= index < len(items):
                _print()
                return items[index][0]
        # unknown keys are silently ignored — the menu stays open, no repaint


def _run_line_menu(text, items, default_index):
    """Typed line fallback for piped stdin, tests, and TTY-less hosts.
    Renders the same rows + trailing legend layout as the interactive frame."""
    _print()
    _print(f"  {_C.YELLOW}?{_C.RESET} {_C.BOLD}{text}{_C.RESET}")
    _print(_menu_frame(items, default_index, default_index))
    default_value = items[default_index][0]
    prompt = f"  {_C.YELLOW}?{_C.RESET} {text} [1-{len(items)} or name, Enter = {default_value}]: "
    while True:
        try:
            reply = input(prompt)
        except (EOFError, KeyboardInterrupt):
            return _keep_default(default_value)
        index = _resolve_menu_reply(reply, items, default_index)
        if index is None:
            _print(f"  {_C.RED}{S.CROSS}{_C.RESET} Choose 1-{len(items)} or a preset name.")
            continue
        return items[index][0]


def menu_select(text, items, default_index=0, _read_key=None):
    """Ask the user to pick one row of a numbered menu; returns the chosen value.

    ``items`` is an ordered sequence of ``(value, description)`` pairs. In a
    real interactive TTY the rows are highlighted by the Up/Down arrow keys,
    Enter confirms the highlighted row, digits 1..N select instantly, and
    Esc/Ctrl+C/EOF keep the pre-selected ``default_index`` row. Everything
    else (piped stdin, unit tests, non-TTY hosts, reader failure) uses the
    plain numbered fallback: Enter accepts the default, a number picks a row,
    the preset name works too — and EOF/Ctrl+C keep the default instead of
    looping forever. ``menu_select`` never raises KeyboardInterrupt and never
    re-prompts on EOF.

    ``_read_key`` (for tests and demos) replaces the platform key reader.
    """
    if not items:
        raise ValueError("menu_select requires at least one item")
    if not 0 <= default_index < len(items):
        raise ValueError(f"default_index {default_index!r} is outside {len(items)} item(s)")

    default_value = items[default_index][0]
    restore = None
    reader = _read_key
    if reader is None:
        reader, restore = _make_raw_key_reader()
    if reader is None:
        return _run_line_menu(text, items, default_index)
    try:
        try:
            return _run_keystroke_menu(text, items, default_index, reader)
        except (EOFError, KeyboardInterrupt):
            return _keep_default(default_value)
    finally:
        if restore is not None:
            restore()


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
            console=_console,
        )
    return None
