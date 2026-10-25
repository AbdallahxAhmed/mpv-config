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
  - only bare printable keys and Shift+<printable> are twinned. Ctrl+/Alt+
    combinations are layout independent on Windows (control codes) and
    named keys (F1, RIGHT, ...) are not characters at all;
  - a twin must be exactly one character and must not be reachable from
    the US layout, otherwise binding it would change US-layout behaviour.
    Arabic letters qualify; the few Arabic shift-layer results that are
    plain ASCII (e.g. Shift+. produces ".") do NOT and are skipped with a
    report - those actions need a hand-picked layout-independent backup
    in the template (Ctrl+Shift+<letter>);
  - the b key emits the two-character sequence "لا" and shifted G/B/T
    emit "لأ/لآ/لإ" - mpv dispatches each character as its own key
    event. Those keys are twinned as mpv KEY SEQUENCES ("ل-ا": keys
    joined with "-"), which consumes both events: pressing b fires the
    twin exactly once and never touches the single-key bindings.
    Sequences lose to single-key bindings on their FIRST element, so
    "ل" (g's character) must stay unbound - g is the one key that keeps
    only its Ctrl+Shift+ backup. There is no sequence timeout: an
    Arabic "h" pressed immediately after an Arabic "g" completes the
    b sequence instead of firing history (measured; accepted);
  - "ا" may be bound as a single (h's twin): it is only ever the SECOND
    character of a lam-alef sequence, and a completed sequence consumes
    it - a bare b press fires b's twin, not h's (measured). The other
    component glyphs ("أ إ آ") are never needed as singles and stay
    refused, as does "ل" (it would defeat every sequence).

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

# US-layout character -> what the SAME physical key produces on Arabic 101,
# unshifted layer. Keys identical in both layouts (digits, "-", "=") are
# omitted: the original binding already covers them.
ARABIC_PLAIN = {
    "q": "ض", "w": "ص", "e": "ث", "r": "ق", "t": "ف", "y": "غ", "u": "ع",
    "i": "ه", "o": "خ", "p": "ح",
    "a": "ش", "s": "س", "d": "ي", "f": "ب", "g": "ل", "h": "ا", "j": "ت",
    "k": "ن", "l": "م",
    "z": "ئ", "x": "ء", "c": "ؤ", "v": "ر", "b": "لا", "n": "ى", "m": "ة",
    "`": "ذ", "[": "ج", "]": "د", ";": "ك", "'": "ط",
    ",": "و", ".": "ز", "/": "ظ",
}

# Shift layer, keyed by the character the US layout produces with shift
# held (uppercase letters and shifted punctuation). ASCII results ("[",
# "]", "/", "~", "{", "}", ",", ".") are kept for honesty; the validator
# refuses to bind them.
ARABIC_SHIFT = {
    "Q": "َ", "W": "ً", "E": "ُ", "R": "ٌ", "T": "لإ", "Y": "إ", "U": "‘",
    "I": "÷", "O": "×", "P": "؛",
    "A": "ِ", "S": "ٍ", "D": "]", "F": "[", "G": "لأ", "H": "أ", "J": "ـ",
    "K": "،", "L": "/",
    "Z": "~", "X": "ْ", "C": "}", "V": "{", "B": "لآ", "N": "آ", "M": "’",
    "~": "ّ", "<": ",", ">": ".", "?": "؟",
}

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

# The b key emits the two-character sequence "لا" and shifted T/G/B emit
# "لإ/لأ/لآ"; mpv dispatches each character as its own key event. Those
# become mpv KEY SEQUENCES (keys joined with "-"). "ل" itself must stay
# unbound - a single-key binding on a sequence's first element defeats
# the sequence - which is why g keeps only its Ctrl+Shift+ backup.
LAM_ALEF_SEQUENCES = {
    "لا": "ل-ا", "لإ": "ل-إ", "لأ": "ل-أ", "لآ": "ل-آ",
}
# Component glyphs that must never be SINGLE bindings: "ل" defeats the
# sequences, and "أ إ آ" are never needed (nothing Latin maps to them
# alone). "ا" is allowed - it is h's twin and only ever the second
# character of a sequence, which a completed sequence consumes (measured).
LAM_ALEF_REFUSED_SINGLES = set("لأإآ")

BEGIN_MARK = "# >>> layout twins (generated by mpv-config - do not edit) >>>"
END_MARK = "# <<< layout twins <<<"


def _validate(twin):
    """(twin, reason): twin is the binding key (possibly a sequence like
    "ل-ا"), or None with a reason when it must not be bound."""
    if twin in LAM_ALEF_SEQUENCES:
        return LAM_ALEF_SEQUENCES[twin], ""
    if len(twin) != 1:
        return None, (
            "Arabic output is %d characters (%s) - needs a Ctrl+Shift+ backup"
            % (len(twin), " ".join("U+%04X" % ord(c) for c in twin))
        )
    if twin in LAM_ALEF_REFUSED_SINGLES:
        return None, (
            "twin %r must stay unbound as a single key - %s"
            % (twin, "binding ل would defeat every lam-alef sequence"
               if twin == "ل" else "it is only ever a sequence component")
        )
    if twin in US_REACHABLE:
        return None, (
            "twin %r is typeable on the US layout - would change US behaviour"
            % twin
        )
    return twin, ""


def _twin_for(key):
    """(twin, reason) for a binding key, or (None, reason) when untwinnable."""
    if key.startswith("Shift+"):
        body = key[len("Shift+"):]
        if len(body) != 1 or not body.isprintable():
            return None, "not a single printable key"
        shift_char = body.upper() if body.isalpha() else US_SHIFTED.get(body)
        if shift_char is None:
            return None, "no US shift character for this key"
        twin = ARABIC_SHIFT.get(shift_char)
    elif len(key) == 1 and key.isprintable():
        if key in ARABIC_PLAIN:
            twin = ARABIC_PLAIN[key]
        else:
            twin = ARABIC_SHIFT.get(key) if not key.islower() else None
    else:
        return None, "named or modified key"
    if twin is None:
        return None, "no Arabic twin for this key"
    return _validate(twin)


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
    """Bare printable keys and Shift+<printable> only."""
    if key.startswith(("Ctrl+", "Alt+", "Win+", "Meta+")):
        return False
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
        twin, reason = _twin_for(key)
        if twin is None:
            report.append((key, reason))
            continue
        if twin in bound_keys or twin in taken:
            report.append((key, "twin %r already bound - skipped" % twin))
            continue
        taken.add(twin)
        twins.append((key, twin, command))

    lines = ["", BEGIN_MARK,
             "# Same physical keys, Arabic 101 layout. Refreshed by every",
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
