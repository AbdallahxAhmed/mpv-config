"""Portable path validation for untrusted archive/raw output names."""
import ntpath
import os
import stat

_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    prefix + digit for prefix in ("COM", "LPT") for digit in "123456789¹²³"
}


def relative_parts(value, directory=False):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"Invalid portable relative path: {value!r}")
    if value.startswith("/") or ntpath.splitdrive(value)[0]:
        raise ValueError(f"Absolute/drive/UNC path is forbidden: {value!r}")
    if directory:
        value = value.rstrip("/")
    parts = value.split("/")
    for part in parts:
        if (not part or part in (".", "..") or part[-1:] in (" ", ".")
                or any(ord(c) < 32 or c in '<>:"|?*' for c in part)
                or part.split(".")[0].upper() in _RESERVED):
            raise ValueError(f"Unsafe path component in {value!r}")
    return parts


def safe_destination(root, relative):
    parts = relative_parts(relative)
    root = os.path.abspath(root)
    if os.path.islink(root) or getattr(os.path, "isjunction", lambda _: False)(root):
        raise ValueError("Staging root must not be a link")
    real_root = os.path.realpath(root)
    current = root
    for part in parts:
        current = os.path.join(current, part)
        if os.path.lexists(current):
            mode = os.lstat(current).st_mode
            if (stat.S_ISLNK(mode) or getattr(os.path, "isjunction", lambda _: False)(current)
                    or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode))):
                raise ValueError(f"Unsafe existing output path: {current}")
    dest_real = os.path.realpath(current)
    if os.path.commonpath((real_root, dest_real)) != real_root or dest_real == real_root:
        raise ValueError(f"Destination escapes staging: {relative}")
    return current
