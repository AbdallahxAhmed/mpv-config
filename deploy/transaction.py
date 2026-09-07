"""Recoverable, same-filesystem configuration replacement (stdlib only).

The CLI holds operation_lock while calling these helpers. Stop mpv before
updating. This protects cooperative installer operations, not arbitrary local
writers, power loss, SIGKILL, or a failing storage device. Each pathname rename
is atomic; a multi-path update is NOT globally atomic. Old paths and a journal
are retained if automatic recovery fails.
"""

import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import uuid
import warnings
from datetime import datetime, timezone

ASSET_DIRS = ("scripts", "shaders", "fonts")
PROTECTED = frozenset((".git", ".mpv-config.lock"))
MANIFEST = ".deploy.lock.json"


class RecoveryError(RuntimeError):
    """A failed operation left recovery material that must not be removed."""


def canonical(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(os.path.expanduser(path))))


def is_junction(path):
    return getattr(os.path, "isjunction", lambda _: False)(path)


def config_path(path):
    expanded = os.path.abspath(os.path.expanduser(path))
    if os.path.islink(expanded) or is_junction(expanded):
        raise ValueError("Config directory must not be a symlink or junction")
    result = canonical(expanded)
    if os.path.dirname(result) == result:
        raise ValueError("A filesystem root is not an mpv config directory")
    if os.path.lexists(result) and not os.path.isdir(result):
        raise ValueError("Config path must be a directory")
    return result


def assert_disjoint(*paths):
    normalized = [canonical(p) for p in paths]
    for i, left in enumerate(normalized):
        for right in normalized[i + 1:]:
            try:
                shared = os.path.commonpath((left, right))
            except ValueError:  # different Windows volumes
                continue
            if shared in (left, right):
                raise ValueError(f"Overlapping paths are not allowed: {left} / {right}")


@contextlib.contextmanager
def operation_lock(config_dir):
    """Exclusive, owner-checked lock beside (never inside) the config directory.

    A crashed process may leave a lock. Do not automatically steal it: verify
    the recorded process has exited before manually removing the exact file.
    """
    config_dir = config_path(config_dir)
    parent, name = os.path.split(config_dir)
    os.makedirs(parent, exist_ok=True)
    lock = os.path.join(parent, f".{name}.mpv-config.lock")
    token = uuid.uuid4().hex
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(
            f"Another operation holds {lock}. If this is a stale lock, verify "
            "its recorded process has exited before removing it."
        ) from exc
    identity = os.fstat(fd)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"pid": os.getpid(), "token": token}, stream)
            stream.flush()
        yield
    finally:
        try:
            current = os.lstat(lock)
            if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                if stat.S_ISREG(current.st_mode):
                    with open(lock, encoding="utf-8") as stream:
                        contents = json.load(stream)
                    if contents.get("token") == token:
                        os.unlink(lock)
        except (OSError, ValueError, AttributeError):
            # Never remove an unrelated/replaced lock on cleanup.
            pass


def regular_tree(root):
    """Validate a tree before copying: only real directories and regular files."""
    if not os.path.isdir(root) or os.path.islink(root) or is_junction(root):
        raise ValueError(f"Expected a real directory: {root}")
    for current, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = os.path.join(current, name)
            mode = os.lstat(path).st_mode
            if is_junction(path) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError(f"Unsafe link or special file: {path}")


def copy_overlay(src, dst):
    """Merge regular files into an OFFLINE candidate, never through links."""
    regular_tree(src)
    if os.path.lexists(dst):
        regular_tree(dst)
    shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=False)


def live_asset_source(config_dir, name):
    """Accept legacy top-level links only to this install's deployed/<name>."""
    path = os.path.join(config_dir, name)
    if not os.path.lexists(path):
        return None
    if is_junction(path):
        raise ValueError(f"Junction is not a managed asset directory: {path}")
    if os.path.islink(path):
        deployed = os.path.join(config_dir, "deployed")
        target = os.path.join(deployed, name)
        if (os.path.islink(deployed) or is_junction(deployed)
                or os.path.islink(target) or is_junction(target)
                or canonical(path) != canonical(target)):
            raise ValueError(f"Refusing unmanaged asset symlink: {path}")
        path = target
    regular_tree(path)
    return path


def validate_staging(staging_dir):
    regular_tree(staging_dir)
    for name in ASSET_DIRS:
        path = os.path.join(staging_dir, name)
        regular_tree(path)
        if not any(files for _, _, files in os.walk(path)):
            raise ValueError(f"Staging has no {name} files")


def prepare_assets(config_dir, staging_dir, repo_dir, prepared):
    """Old unknown files survive; upstream updates apply; vendored patches win."""
    config_dir = config_path(config_dir)
    assert_disjoint(config_dir, staging_dir, repo_dir, prepared)
    validate_staging(staging_dir)
    sources = {name: live_asset_source(config_dir, name) for name in ASSET_DIRS}
    vendor = os.path.join(repo_dir, "scripts")
    if os.path.exists(vendor):
        regular_tree(vendor)
    for name in ASSET_DIRS:
        dest = os.path.join(prepared, name)
        if sources[name]:
            copy_overlay(sources[name], dest)
        copy_overlay(os.path.join(staging_dir, name), dest)
    if os.path.isdir(vendor):
        copy_overlay(vendor, os.path.join(prepared, "scripts"))


def _ignore_root_metadata(root):
    root = canonical(root)
    return lambda current, names: list(PROTECTED.intersection(names)) if canonical(current) == root else []


def snapshot_config(config_dir):
    """Keep a complete, uniquely named backup; never dereference unknown links."""
    config_dir = config_path(config_dir)
    if not os.path.isdir(config_dir):
        return None
    sources = {name: live_asset_source(config_dir, name) for name in ASSET_DIRS}
    # copytree preserves symlinks, but Windows junctions must be rejected.
    for current, dirs, _ in os.walk(config_dir, followlinks=False):
        if canonical(current) == config_dir:
            dirs[:] = [d for d in dirs if d not in PROTECTED]
        for name in dirs:
            if is_junction(os.path.join(current, name)):
                raise ValueError("Cannot safely snapshot a Windows junction")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    backup = f"{config_dir}.backup.{stamp}.{uuid.uuid4().hex[:8]}"
    try:
        shutil.copytree(config_dir, backup, symlinks=True,
                        ignore=_ignore_root_metadata(config_dir))
        for name, source in sources.items():
            dest = os.path.join(backup, name)
            if source and os.path.islink(dest):
                os.unlink(dest)
                shutil.copytree(source, dest)
    except BaseException:
        # Nothing live has changed. Incomplete backups must not appear usable.
        _cleanup(backup)
        raise
    return backup


def _cleanup(path):
    if os.path.isdir(path) and not os.path.islink(path):
        try:
            shutil.rmtree(path)
        except OSError as exc:
            warnings.warn(f"Could not remove temporary directory {path}: {exc}")


def _write_json(path, value):
    with open(path, "x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def replace_items(config_dir, prepared, names, verify_callback=None):
    """Replace selected top-level paths, recovering on BaseException.

    A missing prepared path means deletion (used only by explicit rollback).
    Recovery uses renames, not deletion/copying through a possibly live symlink.
    """
    config_dir = config_path(config_dir)
    assert_disjoint(config_dir, prepared)
    names = list(names)
    if len(set(names)) != len(names):
        raise ValueError("Duplicate transaction path")
    for name in names:
        if (not name or name in PROTECTED or name in (".", "..")
                or os.path.basename(name) != name or "/" in name or "\\" in name):
            raise ValueError(f"Unsafe transaction path: {name}")
    parent = os.path.dirname(config_dir)
    if os.stat(prepared).st_dev != os.stat(parent).st_dev:
        raise ValueError("Prepared replacements must be on the config filesystem")
    created_config = not os.path.exists(config_dir)
    recovery = tempfile.mkdtemp(prefix=f".{os.path.basename(config_dir)}.recovery-", dir=parent)
    old = os.path.join(recovery, "old")
    discarded = os.path.join(recovery, "discarded")
    os.mkdir(old)
    os.mkdir(discarded)
    originals = {name: os.path.lexists(os.path.join(config_dir, name)) for name in names}
    retained = False
    touched = []
    try:
        _write_json(os.path.join(recovery, "journal.json"), {
            "config_dir": config_dir, "originally_present": originals,
            "note": "old/ holds previous paths; discarded/ holds replaced new paths",
        })
        os.makedirs(config_dir, exist_ok=True)
        try:
            for name in names:
                touched.append(name)  # record BEFORE a possibly interrupted rename
                dst = os.path.join(config_dir, name)
                src = os.path.join(prepared, name)
                if originals[name]:
                    os.replace(dst, os.path.join(old, name))
                if os.path.lexists(src):
                    os.replace(src, dst)
            if verify_callback:
                verify_callback()
        except BaseException as original_error:
            failures = []
            for name in reversed(touched):
                dst = os.path.join(config_dir, name)
                previous = os.path.join(old, name)
                try:
                    if os.path.lexists(previous):
                        if os.path.lexists(dst):
                            os.replace(dst, os.path.join(discarded, name))
                        os.replace(previous, dst)
                    elif not originals[name] and os.path.lexists(dst):
                        os.replace(dst, os.path.join(discarded, name))
                except BaseException as recovery_error:
                    failures.append(f"{name}: {recovery_error}")
            if failures:
                retained = True
                raise RecoveryError(
                    f"Automatic recovery was incomplete. Do not delete {recovery}; "
                    f"see its journal.json and old/ directory. {'; '.join(failures)}"
                ) from original_error
            if created_config and not os.listdir(config_dir):
                os.rmdir(config_dir)
            raise
    finally:
        if not retained:
            _cleanup(recovery)


def asset_manifest(metadata, staging_dir, repo_dir, prepared):
    """Record hashes of managed output, including vendored overrides.

    Hashes describe installed bytes; they are NOT upstream authenticity proof.
    Unknown files copied from the old installation are intentionally not owned.
    """
    result = dict(metadata)
    managed = {}
    for name in ASSET_DIRS:
        for current, _, files in os.walk(os.path.join(staging_dir, name)):
            for filename in files:
                relative = os.path.relpath(os.path.join(current, filename), staging_dir)
                managed[relative.replace(os.sep, "/")] = None
    vendor = os.path.join(repo_dir, "scripts")
    vendored = {}
    for current, _, files in os.walk(vendor):
        for filename in files:
            relative = os.path.relpath(os.path.join(current, filename), repo_dir).replace(os.sep, "/")
            managed[relative] = None
            vendored[relative] = None
    for relative in managed:
        data = Path(prepared, *relative.split("/")).read_bytes()
        managed[relative] = hashlib.sha256(data).hexdigest()
        if relative in vendored:
            vendored[relative] = managed[relative]
    result["managed_files"] = managed
    result["vendored_files"] = vendored
    result["manifest_version"] = 2
    return result


def update_assets(config_dir, staging_dir, repo_dir, metadata):
    """Apply a backed-up scripts/shaders/fonts update; config text is untouched."""
    config_dir = config_path(config_dir)
    assert_disjoint(config_dir, staging_dir, repo_dir)
    parent = os.path.dirname(config_dir)
    with tempfile.TemporaryDirectory(prefix=".mpv-prepared-", dir=parent) as prepared:
        prepare_assets(config_dir, staging_dir, repo_dir, prepared)
        manifest = asset_manifest(metadata, staging_dir, repo_dir, prepared)
        _write_json(os.path.join(prepared, MANIFEST), manifest)
        backup = snapshot_config(config_dir)
        replace_items(config_dir, prepared, [*ASSET_DIRS, MANIFEST])
    return backup


def restore_snapshot(config_dir, backup_path, dry_run=False):
    """Restore a snapshot, preserving .git and retaining the pre-rollback state."""
    config_dir = config_path(config_dir)
    backup_path = config_path(backup_path)
    assert_disjoint(config_dir, backup_path)
    if not os.path.isdir(backup_path):
        raise FileNotFoundError(f"Backup not found: {backup_path}")
    if dry_run:
        return None
    parent = os.path.dirname(config_dir)
    os.makedirs(parent, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".mpv-rollback-", dir=parent) as workspace:
        prepared = os.path.join(workspace, "prepared")
        # Symlinks in a backup are restored AS links, never dereferenced.
        shutil.copytree(backup_path, prepared, symlinks=True,
                        ignore=_ignore_root_metadata(backup_path))
        current_names = os.listdir(config_dir) if os.path.isdir(config_dir) else []
        names = sorted((set(current_names) | set(os.listdir(prepared))) - PROTECTED)
        safety_backup = snapshot_config(config_dir)
        replace_items(config_dir, prepared, names)
    return safety_backup
