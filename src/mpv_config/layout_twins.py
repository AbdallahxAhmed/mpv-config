"""Layout twins: make mpv bindings fire on the same PHYSICAL key under an
Arabic layout, without duplicating lines by hand.

mpv matches a binding against the CHARACTER a key produces, and "mpv uses
input translated by the current OS keyboard layout, rather than physical
scan codes" (mpv manual; upstream issue #351 has been open since 2013).
With an Arabic layout active every Latin letter binding is therefore dead.

The twins approach: for each printable binding in input.conf, emit an extra
binding on the character the SAME physical key produces on the Arabic 101
layout (the only non-Latin layout installed on the target machine). Pure
config - no hook process, nothing to spawn, nothing to clean up - and the
deployer regenerates the twin block on every install/update, so a binding
added by hand later is covered after the next `mpv-config update`.

Rules the generator follows:
  - only bare printable keys, Shift+<printable> and Ctrl+Shift+<printable>
    are twinned. Plain Ctrl+<letter> arrives as a layout-independent
    control code on every layout (measured: Ctrl+c/v and Ctrl+4 work under
    Arabic), so it needs no twin; named keys (F1, RIGHT, ...) are not
    characters at all;
  - a Ctrl+Shift+<key> combo does NOT become a control code under Arabic:
    mpv receives Ctrl+<the shift-layer Arabic character> (measured on the
    real stream: a user --input-test capture shows "Ctrl+أ" for
    Ctrl+Shift+H). Those modified twins are emitted - Ctrl+Shift+h ->
    Ctrl+أ, Ctrl+Shift+b -> Ctrl+آ (lam-alef pairs: only the LAST
    character arrives, same as bare keys) - and combining marks are
    allowed (mpv registers and dispatches them). ASCII halves are refused
    so US behaviour never changes;
  - a bare twin must be exactly one character, not reachable from the US
    layout (otherwise the binding would change US behaviour), and not a
    lam-alef glyph;
  - the lam-alef glyphs (ل ا أ إ آ) are never GENERATED as plain twins.
    Measured on the real key stream (user's --input-test capture,
    2026-10-25): a b keypress delivers ONLY "ا" to mpv - the ل of every
    lam-alef pair never arrives - so "b" and "h" send the IDENTICAL
    character; binding ا would make the b key open history. The template
    covers those five keys through the Ctrl+Shift+ combos (whose Arabic
    delivery form the generator twins) and through its own bare
    shift-layer lines (أ آ ’ ‘ ٍ - written in the template, skipped by
    the generator). NOTE for the future: simulating keys with the
    `keypress` command DOES deliver both characters - only the real
    Windows stream drops the ل; do not "fix" this from headless tests.

Table provenance: probed on the target machine from the loaded Arabic
layout (hkl 0x04010c01, layout id 00000401 = Arabic 101) with
ToUnicodeEx, an explicit layout handle and a zeroed key-state array - an
offline one-shot probe, NOT the guard's banned runtime VK->char path. The
result agrees with xkeyboard-config's ara(basic) symbol table on every
key.
"""
from __future__ import annotations

import argparse
import re
import sys

# US-layout character -> what the SAME physical key produces on Arabic 101 (Windows)
# and Linux XKB ara (Arabic Egypt / basic), unshifted layer. Keys identical in both
# layouts (digits, "-", "=") are omitted: the original binding already covers them.
ARABIC_PLAIN_WIN = {
    "q": "ض", "w": "ص", "e": "ث", "r": "ق", "t": "ف", "y": "غ", "u": "ع",
    "i": "ه", "o": "خ", "p": "ح",
    "a": "ش", "s": "س", "d": "ي", "f": "ب", "g": "ل", "h": "ا", "j": "ت",
    "k": "ن", "l": "م",
    "z": "ئ", "x": "ء", "c": "ؤ", "v": "ر", "b": "لا", "n": "ى", "m": "ة",
    "`": "ذ", "[": "ج", "]": "د", ";": "ك", "'": "ط",
    ",": "و", ".": "ز", "/": "ظ",
}

ARABIC_SHIFT_WIN = {
    "Q": "َ", "W": "ً", "E": "ُ", "R": "ٌ", "T": "لإ", "Y": "إ", "U": "‘",
    "I": "÷", "O": "×", "P": "؛",
    "A": "ِ", "S": "ٍ", "D": "]", "F": "[", "G": "لأ", "H": "أ", "J": "ـ",
    "K": "،", "L": "/",
    "Z": "~", "X": "ْ", "C": "}", "V": "{", "B": "لآ", "N": "آ", "M": "’",
    "~": "ّ", "<": ",", ">": ".", "?": "؟",
}

# Linux XKB ara layout (Arabic Egypt / basic)
ARABIC_PLAIN_XKB = {
    "q": "ض", "w": "ص", "e": "ث", "r": "ق", "t": "ف", "y": "غ", "u": "ع",
    "i": "ه", "o": "خ", "p": "ح",
    "a": "ش", "s": "س", "d": "ي", "f": "ب", "g": "ل", "h": "ا", "j": "ت",
    "k": "ن", "l": "م",
    "z": "ئ", "x": "ء", "c": "ؤ", "v": "ر", "b": "\ufefb", "n": "ى", "m": "ة",  # ﻻ
    "`": "ذ", "[": "ج", "]": "د", ";": "ك", "'": "ط",
    ",": "و", ".": "ز", "/": "ظ",
}

ARABIC_SHIFT_XKB = {
    "Q": "َ", "W": "ً", "E": "ُ", "R": "ٌ", "T": "\ufef9", "Y": "إ", "U": "`",  # ﻹ
    "I": "÷", "O": "×", "P": "؛",
    "A": "ِ", "S": "ٍ", "D": "]", "F": "[", "G": "\ufef7", "H": "أ", "J": "ـ",  # ﻷ
    "K": "،", "L": "/",
    "Z": "~", "X": "ْ", "C": "}", "V": "{", "B": "\ufef5", "N": "آ", "M": "'",  # ﻵ
    "~": "ّ", "<": ",", ">": ".", "?": "؟",
    "{": "<", "}": ">", ":": ":", '"': '"',
}

# Alias for backward compatibility with probes expecting ARABIC_PLAIN/SHIFT
ARABIC_PLAIN = ARABIC_PLAIN_WIN
ARABIC_SHIFT = ARABIC_SHIFT_WIN

# What the US layout produces for Shift+<key>, to resolve "Shift+x" style
# binding names through ARABIC_SHIFT.
US_SHIFTED = {
    "`": "~", "1": "!", "2": "@", "3": "#", "4": "$", "5": "%", "6": "^",
    "7": "&", "8": "*", "9": "(", "0": ")",
    "-": "_", "=": "+", "[": "{", "]": "}", "\\": "|", ";": ":", "'": '"',
    ",": "<", ".": ">", "/": "?",
}

# Characters a US layout can type: binding any of these as a twin could
# fire on US keystrokes too, so they are refused.
US_REACHABLE = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    "`-=[]\\;',./~!@#$%^&*()_+{}|:\"<>?"
)

BEGIN_MARK = "# >>> layout twins (generated by mpv-config - do not edit) >>>"
END_MARK = "# <<< layout twins <<<"


def _validate(twin):
    """(twin, reason): twin is None with a reason when it must not be bound."""
    if not twin or len(twin) != 1:
        return None, (
            "Arabic output is %d characters (%s) - requires a single character"
            % (len(twin) if twin else 0, " ".join("U+%04X" % ord(c) for c in (twin or "")))
        )
    if twin in US_REACHABLE:
        return None, (
            "twin %r is typeable on the US layout - would change US behaviour"
            % twin
        )
    return twin, ""


def _validate_modified(char):
    """Validation for the Arabic half of a Ctrl+<char> modified twin.

    ASCII stays refused (binding it could fire on US keystrokes).
    """
    if not char or len(char) != 1:
        return None, "modified twin must be a single character"
    if char in US_REACHABLE:
        return None, (
            "twin Ctrl+%r is typeable on the US layout - would change US "
            "behaviour" % char)
    return char, ""


def _twins_for(key):
    """(list_of_twins, reason) for a binding key across Windows 101 and Linux XKB layouts."""
    twins: list[str] = []
    reason = ""
    if key.startswith("Ctrl+Shift+"):
        # Under an Arabic layout the combo does NOT become a control code:
        # mpv receives Ctrl+<the shift-layer Arabic character>.
        # On Windows, lam-alef delivers the second character (e.g. Ctrl+آ for Ctrl+Shift+b).
        # On Linux XKB, the ligature arrives as a single codepoint (Ctrl+ﻵ).
        # Both are emitted so the user's combo works across operating systems.
        body = key[len("Ctrl+Shift+"):]
        if len(body) != 1 or not body.isprintable():
            return [], "not a single printable key"
        shift_char = body.upper() if body.isalpha() else US_SHIFTED.get(body)
        if shift_char is None:
            return [], "no US shift character for this key"
        win_ar = ARABIC_SHIFT_WIN.get(shift_char)
        if win_ar:
            c, r = _validate_modified(win_ar[-1])
            if c and ("Ctrl+" + c) not in twins:
                twins.append("Ctrl+" + c)
            elif not c and not reason:
                reason = r
        xkb_ar = ARABIC_SHIFT_XKB.get(shift_char)
        if xkb_ar:
            c, r = _validate_modified(xkb_ar[-1])
            if c and ("Ctrl+" + c) not in twins:
                twins.append("Ctrl+" + c)
            elif not c and not reason:
                reason = r
        if not twins:
            return [], reason or "no Arabic twin for this combo"
        return twins, ""
    if key.startswith(("Ctrl+", "Alt+", "Win+", "Meta+")):
        # plain Ctrl+<letter> arrives as a layout-independent control code
        # on every layout (measured: Ctrl+c/v and Ctrl+4 work under Arabic);
        # Alt+<letter> delivery is unverified - neither gets a twin.
        return [], "control-code or unverified combo"
    if len(key) == 1 and key.isprintable():
        # Check Linux XKB first, then Windows Arabic 101
        for table_plain, table_shift in [
            (ARABIC_PLAIN_XKB, ARABIC_SHIFT_XKB),
            (ARABIC_PLAIN_WIN, ARABIC_SHIFT_WIN),
        ]:
            raw = table_plain.get(key) if key in table_plain else (table_shift.get(key) if not key.islower() else None)
            if raw:
                c, r = _validate(raw)
                if c and c not in twins:
                    twins.append(c)
                elif not c and not reason:
                    reason = r
        if not twins:
            return [], reason or "no Arabic twin for this key"
        return twins, ""
    return [], "named or modified key"


def _twin_for(key):
    """(twin, reason) for a binding key, returning primary twin or (None, reason)."""
    twins, reason = _twins_for(key)
    if twins:
        return twins[0], ""
    return None, reason


def _parse_binding(line):
    """(key, command) of a binding line, or None for anything else."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    parts = stripped.split(None, 1)
    if len(parts) < 2:
        return None
    return parts[0], parts[1].rstrip()


def _is_twinable(key):
    """Bare printable keys, Shift+<printable> and Ctrl+Shift+<printable>.

    Keys that are already Arabic-script characters (the template's own
    Arabic-shift lines like "أ") are skipped: they ARE the twins, there is
    nothing to generate for them.
    """
    if any(ord(c) > 0x590 for c in key):
        return False
    if key.startswith(("Ctrl+", "Alt+", "Win+", "Meta+")):
        if not key.startswith("Ctrl+Shift+"):
            return False
        body = key[len("Ctrl+Shift+"):]
    else:
        body = key[len("Shift+"):] if key.startswith("Shift+") else key
    return len(body) == 1 and body.isprintable()


def generate(input_conf):
    """Refresh the generated twin block in an input.conf text.

    Returns (new_text, report): report lists (key, reason) for bindings
    that could not be twinned, for the deployer to surface.
    """
    pattern = re.compile(
        re.escape(BEGIN_MARK) + r".*?" + re.escape(END_MARK) + r"\n?",
        re.DOTALL,
    )
    base = pattern.sub("", input_conf).rstrip("\n") + "\n"

    bindings = []
    for line in base.splitlines():
        parsed = _parse_binding(line)
        if parsed:
            bindings.append(parsed)

    bound_keys = {key for key, _ in bindings}
    twins, report, taken = [], [], set()
    for key, command in bindings:
        if not _is_twinable(key):
            continue
        cands, reason = _twins_for(key)
        if not cands:
            report.append((key, reason))
            continue
        for twin in cands:
            if twin in bound_keys or twin in taken:
                report.append((key, "twin %r already bound - skipped" % twin))
                continue
            taken.add(twin)
            twins.append((key, twin, command))

    lines = ["", BEGIN_MARK,
             "# Same physical keys, Arabic 101 & Linux XKB layouts. Refreshed by every",
             "# mpv-config install/update - edit your Latin bindings above",
             "# and these twin lines are regenerated."]
    for source, twin, command in twins:
        lines.append("# twin of %s" % source)
        lines.append("%s %s" % (twin, command))
    if report:
        lines.append("#")
        lines.append("# Could not be twinned (see the manual section on the")
        lines.append("# keyboard layout for the hand-picked backups):")
        for source, reason in report:
            lines.append("#   %s: %s" % (source, reason))
    lines.append(END_MARK)
    return base + "\n".join(lines) + "\n", report


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m mpv_config.layout_twins",
        description="Refresh the generated Arabic layout twins in input.conf.",
    )
    parser.add_argument("input", help="path to input.conf")
    parser.add_argument("--write", action="store_true",
                        help="rewrite the file instead of printing")
    args = parser.parse_args(argv)

    with open(args.input, "r", encoding="utf-8") as handle:
        text = handle.read()
    new_text, report = generate(text)
    if args.write:
        with open(args.input, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(new_text)
    else:
        sys.stdout.write(new_text)
    for source, reason in report:
        print("layout twins: %s: %s" % (source, reason), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
