"""Event protocol spoken to the mpv-config-ui renderer (ui/ in this repo).

When the CLI launches the deployer under the Go renderer it sets
MPV_CONFIG_UI_PROTOCOL=1. deploy/ui.py then emits structured events instead
of drawing: one line per event on stdout, the ASCII record separator (0x1E)
followed by JSON. Anything else on stdout is shown as plain text, so a stray
print can never corrupt the stream. Prompt answers come back on stdin as
{"id": n, "value": ...} lines. Schema: ui/PROTOCOL.md.

Stdlib only; the plain (Rich/ANSI) renderer is untouched when this is off.
"""

import itertools
import json
import os
import re
import signal
import sys
import threading

VERSION = 1
RECORD_SEPARATOR = "\x1e"

ACTIVE = os.environ.get("MPV_CONFIG_UI_PROTOCOL") == "1"

_lock = threading.Lock()
_ids = itertools.count(1)
_out = sys.stdout

# Rich markup tags start with a lowercase letter, '#', '/' or '@' — the same
# rule Rich uses, so "[DRY RUN]" stays literal exactly as it renders today.
_MARKUP_TAG = re.compile(r"(?<!\\)\[[a-z#/@][^\[\]]*\]")


def next_id():
    return next(_ids)


def plain(value):
    """Rich markup → plain text (the renderer applies its own styling)."""
    if value is None:
        return ""
    text = str(value)
    try:
        from rich.markup import render

        return render(text).plain
    except Exception:
        return _MARKUP_TAG.sub("", text).replace("\\[", "[")


def emit(event_type, /, **fields):
    event = {"t": event_type}
    event.update({key: value for key, value in fields.items() if value is not None})
    line = RECORD_SEPARATOR + json.dumps(event, ensure_ascii=False) + "\n"
    with _lock:
        try:
            _out.write(line)
            _out.flush()
        except (OSError, ValueError):
            pass  # renderer gone (it was killed): keep working silently


def interactive():
    return os.environ.get("MPV_CONFIG_UI_INTERACTIVE") == "1"


def _await_reply(event_id):
    """Block until the renderer answers ``event_id``; None on EOF/garbage."""
    while True:
        try:
            line = sys.stdin.readline()
        except (OSError, ValueError):
            return None, False
        if not line:
            return None, False
        try:
            reply = json.loads(line)
        except ValueError:
            continue
        if isinstance(reply, dict) and reply.get("id") == event_id:
            return reply.get("value"), True


def ask_confirm(text, default=True):
    event_id = next_id()
    emit("prompt", id=event_id, kind="confirm", text=plain(text), default=bool(default))
    value, ok = _await_reply(event_id)
    if not ok or not isinstance(value, bool):
        return False  # same contract as the plain prompt: EOF means "no"
    return value


def ask_menu(text, items, default_index):
    event_id = next_id()
    values = [value for value, _label in items]
    emit(
        "prompt",
        id=event_id,
        kind="menu",
        text=plain(text),
        items=[{"value": value, "label": plain(label)} for value, label in items],
        default=default_index,
    )
    value, ok = _await_reply(event_id)
    if ok and value in values:
        return value
    return values[default_index]


def request_sudo(reason):
    """Ask the renderer to run `sudo -v` on the real terminal; True if granted."""
    event_id = next_id()
    emit("sudo", id=event_id, reason=plain(reason))
    value, ok = _await_reply(event_id)
    return bool(ok and value is True)


def _raise_keyboard_interrupt(signum, frame):
    raise KeyboardInterrupt


def install_signal_bridge():
    """Windows: the renderer cancels with CTRL_BREAK (the only console event
    that reaches another process group). Map it to KeyboardInterrupt so the
    transaction code rolls back exactly like Ctrl+C on Linux."""
    if ACTIVE and sys.platform == "win32" and hasattr(signal, "SIGBREAK"):
        try:
            signal.signal(signal.SIGBREAK, _raise_keyboard_interrupt)
        except (ValueError, OSError):
            pass  # not the main thread: nothing to bridge


install_signal_bridge()
