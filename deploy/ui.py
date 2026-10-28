"""
ui.py — Beautiful terminal output with colors and status indicators.

Provides a consistent, clean interface for all user-facing messages.
Uses Rich if available, falling back to basic ANSI otherwise.
Handles Windows cp1252 gracefully.
"""

import os
import shutil
import sys
import threading
import time
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


# ─── Inline Download Progress (system deps + fetcher) ────────────────


def _human_bytes(num_bytes):
    """Compact byte count for progress lines ("999.0 B", "12.4 MB")."""
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


class InlineDownloadProgress:
    """In-place, single-line progress for binary HTTP downloads.

    Renders on a TTY while the transfer runs and is fully silent on piped
    output (curl | bash, CI logs) — matching the previous behavior there.
    Same visual language as the rest of the output (rich/ui.py): heavy
    unicode bar glyphs when the terminal can encode them, ASCII otherwise:

        > yt-dlp.exe  ━━━━━━━━━━━━━━━━━━━━━━  45%  8.4/18.7 MB  2.1 MB/s  ETA 5s

    Whole-transfer average speed keeps the readout stable; updates are
    throttled so a hot chunk cadence does not redraw faster than the eye.

    No-wrap contract: the rendered line is clamped to the terminal width
    (budget = columns - 1) so an 80-column terminal can never auto-wrap the
    row and let the carriage-return overwrite smear wrapped leftovers down
    the screen. The shrink ladder keeps the line informative longest: the
    bar collapses to zero first, then ETA, then speed, then the label —
    pct and byte counts always stay.
    """

    BAR_WIDTH = 24

    def __init__(self, label, total=None, stdout=None, clock=time.monotonic,
                 update_interval=0.1, tick_interval=1.0, theme=None,
                 width_fn=None):
        self.label = (label or "download")
        if len(self.label) > 40:
            self.label = self.label[:37] + "..."
        try:
            self.total = int(total) if total is not None and int(total) > 0 else None
        except (TypeError, ValueError):
            self.total = None
        self._stdout = stdout if stdout is not None else sys.stdout
        self._clock = clock
        self._width_fn = width_fn or self._default_width
        self._interval = max(0.0, update_interval)
        self._tick_interval = max(0.0, tick_interval)
        if theme == "unicode" or (theme is None and USE_UNICODE):
            # Matches the rich Progress bars the rest of the output paints.
            self._bar_full, self._bar_empty = "━", "─"
        else:
            self._bar_full, self._bar_empty = S.BLOCK, S.LIGHT
        self._done = 0
        self._started = None
        self._last_render = float("-inf")
        self._last_len = 0
        self._rendered = False
        self._stop_ticks = None
        self._tick_thread = None
        try:
            self._tty = bool(self._stdout.isatty())
        except Exception:
            self._tty = False

    def start(self):
        """Anchor the elapsed-time base (called when the transfer begins)."""
        if self._started is None:
            self._started = self._clock()
        self._stop_ticks_and_join()

    def settle(self):
        """First byte arrived: restart the elapsed clock on the body phase.

        Speed/ETA then reflect the actual transfer rate instead of being
        diluted by the (sometimes slow) connect time before it.
        """
        self._started = self._clock()
        self._stop_ticks_and_join()

    def start_connect_ticks(self):
        """Liveness during the connect phase (DNS/TLS/CDN), where no bytes flow.

        urlopen() blocks the main thread; a 30+ s connect previously looked
        identical to a hang. A tick thread re-renders 'connecting Ns' every
        second until the first byte arrives.
        """
        self._started = self._clock()
        self._stop_ticks_and_join()
        if not self._tty:
            return
        self._stop_ticks = threading.Event()
        self._write_line(self._connect_line())
        event = self._stop_ticks
        self._tick_thread = threading.Thread(
            target=self._tick_loop, args=(event,), daemon=True
        )
        self._tick_thread.start()

    def _tick_loop(self, stop_event):
        while not stop_event.wait(self._tick_interval):
            self._write_line(self._connect_line())

    def _connect_line(self):
        elapsed = self._clock() - self._started
        line = f"> {self.label}  connecting" + (f" {int(elapsed)}s" if elapsed >= 1 else "")
        budget = self._budget()
        if len(line) > budget:
            # Narrow terminal: chop the tail (elapsed digits) rather than
            # let the tick frame wrap and smear like a mid-transfer row.
            line = line[:budget]
        return line

    def _stop_ticks_and_join(self):
        event = self._stop_ticks
        if event is None:
            return
        self._stop_ticks = None
        event.set()
        thread = self._tick_thread
        self._tick_thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def update(self, chunk_size):
        """Account for one received chunk; render when the throttle allows."""
        self.start()
        self._done += max(0, int(chunk_size))
        now = self._clock()
        if self._tty and now - self._last_render >= self._interval:
            self._render()

    def finish(self):
        """Final render at the real byte count, then close the line."""
        self._stop_ticks_and_join()
        if not self._tty:
            return
        self._render()
        if self._rendered:
            self._stdout.write("\n")
            self._stdout.flush()

    def abort(self):
        """Close the in-place line after a failure so logs stay readable."""
        self._stop_ticks_and_join()
        if self._tty and self._rendered:
            self._stdout.write("\n")
            self._stdout.flush()

    def _render(self):
        now = self._clock()
        self._last_render = now
        elapsed = now - self._started if self._started is not None else 0.0
        speed = self._done / elapsed if elapsed > 0 else 0.0
        speed_text = f"{_human_bytes(speed)}/s"
        if self.total and self._done <= self.total and speed > 0:
            eta = max(0, int((self.total - self._done) / speed))
            full_extra = f"{speed_text}  ETA {eta}s"
        else:
            full_extra = speed_text
        plain_line, shown_line = self._compose(
            budget=self._budget(), full_extra=full_extra, speed_text=speed_text
        )
        self._write_line(plain_line, shown_line)

    @staticmethod
    def _default_width():
        try:
            return shutil.get_terminal_size((80, 20)).columns
        except Exception:
            return 80

    def _budget(self):
        """Visible columns one render row may occupy (one short of wrap).

        Floor of one column: a zero/negative report still renders a stub
        rather than an empty line.
        """
        try:
            columns = int(self._width_fn())
        except Exception:
            columns = 80
        return max(1, columns - 1)

    def _pairs(self, bar_width, extra_text, label=None):
        """(plain, decorated) pairs for one render state.

        The plain text drives the overwrite-pad math so ANSI escape bytes
        never distort visible-length accounting. Only the arrow and the bar
        take color — numbers stay greppable. ``extra_text`` carries the
        speed readout (with or without ETA) so the width ladder can drop
        pieces without rebuilding the structure.
        """
        label = self.label if label is None else label
        cyan, dim, reset = _C.CYAN, _C.DIM, _C.RESET
        if USE_COLOR:
            pairs = [(f"> ", f"{cyan}>{reset} ")]
        else:
            pairs = [("> ", None)]
        pairs.append((label, None))

        if self.total and self._done <= self.total:
            pct = min(100, int(self._done * 100 / self.total))
            filled = int(bar_width * self._done / self.total)
            rest = bar_width - filled
            bar_plain = self._bar_full * filled + self._bar_empty * rest
            if USE_COLOR:
                bar_rich = (
                    f"{cyan}{self._bar_full * filled}{reset}"
                    f"{dim}{self._bar_empty * rest}{reset}"
                )
            else:
                bar_rich = None
            pairs.append(("  " + bar_plain, None if bar_rich is None else "  " + bar_rich))
            pairs.append((f"  {pct:3d}%", None))
            pairs.append(
                (f"  {_human_bytes(self._done)}/{_human_bytes(self.total)}", None)
            )
            if extra_text:
                pairs.append(("  " + extra_text, None))
        else:
            pairs.append((f"  {_human_bytes(self._done)}", None))
            if extra_text:
                pairs.append(("  " + extra_text, None))
        return pairs

    def _compose(self, budget, full_extra, speed_text):
        """Pick the widest render state that fits inside ``budget``.

        Shrink ladder, per the no-wrap contract: the bar collapses to zero
        first, then ETA is dropped, then speed; the label is cut last and
        pct + byte counts always stay. Same ladder for the unknown-total
        shape, where the bar/pct simply never exist.
        """
        label = self.label
        attempts = [(width, full_extra) for width in range(self.BAR_WIDTH, -1, -1)]
        attempts += [(0, speed_text), (0, "")]
        plain = ""
        pairs = []
        for bar_width, extra in attempts:
            pairs = self._pairs(bar_width, extra, label)
            plain = "".join(p[0] for p in pairs)
            if len(plain) <= budget:
                break
        if len(plain) > budget:
            # Even the bare skeleton overflows: truncate the label so pct
            # and the byte counts survive, then slice as the absolute
            # guarantee on absurdly tiny budgets.
            overflow = len(plain) - budget
            keep = max(1, len(label) - overflow - 3)
            if keep < len(label):
                label = label[:keep] + "..."
            pairs = self._pairs(0, "", label)
            plain = "".join(p[0] for p in pairs)
            if len(plain) > budget:
                plain = plain[:budget]
                pairs = [(plain, None)]  # decoration would corrupt the slice
        shown = "".join(p[1] if p[1] is not None else p[0] for p in pairs)
        return plain, shown

    def _write_line(self, line, shown=None):
        """Overwrite the current console line in place (carriage return)."""
        pad = max(0, self._last_len - len(line))
        self._last_len = len(line)
        self._rendered = True
        if not self._tty:
            return
        text = shown if shown is not None else line
        try:
            if USE_COLOR:
                # \x1b[2K erases the whole row: a line that shrank between
                # renders cannot leave stale characters behind, and no pad
                # math is needed. The line itself is already width-clamped.
                self._stdout.write("\r\x1b[2K" + text)
            else:
                self._stdout.write("\r" + text + " " * pad)
            self._stdout.flush()
        except Exception:
            # Closed/odd console → stop rendering, keep counting bytes.
            self._tty = False


def summary(results):
    """Close a batch of component results: counts plus failing rows only.

    Components announce what they are doing while running (steps, per-item
    lines), so re-listing every row here duplicated the 45-row verification
    table under itself on every deploy. Failing rows stay visible so a
    broken check can never scroll past unnoticed; the complete listing
    remains with the component that produced the results.
    """
    ok_count = sum(1 for r in results if r.get("status") == "ok")
    skip_count = sum(1 for r in results if r.get("status") == "skipped")
    failures = [r for r in results if r.get("status") not in ("ok", "skipped")]
    fail_count = len(failures)

    if failures:
        if _RICH_AVAILABLE:
            table = Table(title="Summary", box=None)
            table.add_column("Name")
            table.add_column("Detail", style="dim")
            for r in failures:
                table.add_row(f"[red]✗[/red] {r['name']}", r.get("detail", ""))
            _console.print(table)
        else:
            _print(f"\n{_C.BOLD}Failed:{_C.RESET}")
            for r in failures:
                detail = r.get("detail", "")
                suffix = f" {_C.DIM}-- {detail}{_C.RESET}" if detail else ""
                _print(f"  {_C.RED}{S.CROSS}{_C.RESET} {r['name']}{suffix}")

    parts = []
    if ok_count:
        parts.append(("ok", f"{ok_count} succeeded"))
    if skip_count:
        parts.append(("skip", f"{skip_count} skipped"))
    if fail_count:
        parts.append(("fail", f"{fail_count} failed"))
    if not parts:
        active = "nothing to report"
        if _RICH_AVAILABLE:
            _console.print(f"[dim]{active}[/dim]")
        else:
            _print(f"  {_C.DIM}{active}{_C.RESET}")
        return

    if _RICH_AVAILABLE:
        styled = []
        for kind, text in parts:
            style = {"ok": "green", "skip": "yellow", "fail": "red"}[kind]
            styled.append(f"[{style}]{text}[/{style}]")
        _console.print("  ".join(styled))
    else:
        style_by_kind = {"ok": _C.GREEN, "skip": _C.YELLOW, "fail": _C.RED}
        _print("  " + "  ".join(f"{style_by_kind[k]}{t}{_C.RESET}" for k, t in parts))


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
