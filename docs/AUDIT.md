# Audit and remediation report

Baseline reviewed: `835e46df0cc5ff11b33e3d01bc3982820852e58f`.
All work described here lives on a review branch. `main` was not modified.

## Status of this branch

This report separates what is **on this branch** from what is only implemented
and tested locally. Read that distinction before relying on any claim below.

Landed here, each verified byte-for-byte against the locally tested file:

| File | Purpose |
| --- | --- |
| `deploy/transaction.py` | recoverable same-filesystem transaction engine |
| `deploy/path_safety.py` | validation of untrusted relative paths |
| `deploy/audit_log.py` | non-mutating reads, fail-closed package ownership |
| `deploy/fetcher.py` | archive-member validation, atomic component commit |
| `deploy/deployer.py` | deployment routed through the transaction engine |
| `deploy/verifier.py` | config checks with third-party Lua disabled |
| `scripts/smart-paste.lua` | local paths are no longer rewritten into URLs |
| `tests/test_transaction.py` | 14 tests, 64 failure-injection subcases |
| `tests/test_portable_fetcher.py` | 11 download and extraction safety tests |
| `tests/test_audit_log_integrity.py` | 4 audit-log integrity tests |
| `tests/test_fetcher_safety.py` | repaired fixtures, pinned-tag coverage |

**Not on this branch:** the `setup.py` CLI rewrite and a CI workflow. The CLI
changes are written and pass locally but were not pushed, so every CLI-level
item below is marked *pending* rather than fixed.

**The suite on this branch is currently red**, for a reason that predates these
commits: `tests/test_audit_patches.py` contains two `IndentationError`s and
cannot be collected. That file is not repaired here.

**No CI has ever run on this branch.** Every result quoted in this document
comes from a local Linux sandbox: 32 Python tests under `unittest` and 15 Lua
cases under a real Lua 5.4 interpreter.

## What was reviewed

Deployment code (`setup.py`, `deploy/`), configuration templates, vendored mpv
scripts, the bootstrap installers, the existing tests, and the documentation.

## Method, and what "verified" means here

- Bugs were reproduced against the exact baseline sources with mocked HTTP and
  filesystem fixtures, then re-run after the fix.
- Python behavior was exercised with `unittest`, including failure injection.
- Lua behavior was exercised with a real Lua 5.4 interpreter and mocked mpv
  APIs. No media, network request, or subprocess was executed.
- **Not validated here:** real playback, GPU output, HDR, Windows/macOS
  end-to-end installs, and package-manager behavior. Those require the target
  machines. See the manual checklist below.

## Highest-value missing feature: recoverable updates

The original `--update` and `--install` paths copied files directly onto the
live configuration directory. A failure midway, a `Ctrl-C`, or a partial
download could leave the configuration half-updated with no way back.

This branch adds `deploy/transaction.py`, which:

1. builds the complete new configuration **offline** in a sibling directory,
2. verifies the download is complete before anything live is touched,
3. takes a uniquely named backup of the existing configuration,
4. swaps each top-level path into place with atomic renames,
5. reverses every completed step if anything fails, including `KeyboardInterrupt`,
6. keeps the previous files plus a `journal.json` if automatic recovery itself
   fails, and raises `RecoveryError` naming the exact directory to keep.

Personal files are preserved: `mpv.conf`, `input.conf`, `mpv.conf.user`, custom
scripts, and unknown files in `scripts/`, `shaders/`, `fonts/` and `script-opts/`
survive an update. Profile flags now seed only newly created config files;
rewriting an existing config is an explicit, reviewable action.

### Honest limits

Each rename is atomic; a multi-path update is **not** globally atomic. This
protects against errors, interruptions and failed verification. It does not
promise recovery from power loss, `SIGKILL`, a failing disk, or another program
writing into the same directory at the same time. Stop mpv before updating.

## Engine and module fixes on this branch

- Updates no longer copy onto live paths or follow symlinks out of the config
  directory; legacy `deployed/` symlink layouts are migrated to real directories
  without touching the old target.
- Deployment prepares the whole configuration in a sibling directory and commits
  it with renames, so an existing `mpv.conf`, `input.conf`, `mpv.conf.user` or
  `script-opts/` file is preserved rather than overwritten. Only newly supplied
  files are recorded as managed.
- The transaction engine accepts a verification callback and restores the
  previous configuration when that callback fails.
- The operation lock lives **beside** the configuration directory, is created
  exclusively, and is only removed by the owning process. A stale lock is never
  silently stolen.
- Backups are uniquely named, so two operations in the same second cannot
  overwrite each other, and `.git` is preserved during rollback.
- Rollback keeps a safety snapshot of the pre-rollback state.
- `deploy/verifier.py` checks the configuration directory it is given rather
  than a hardcoded path, treats `uv`, `ffsubsync` and `alass` as optional,
  ignores commented lines when scanning for unresolved template placeholders,
  and runs the mpv startup probe with `--load-scripts=no` so verification
  cannot execute freshly downloaded third-party Lua.

### Download hardening (`deploy/fetcher.py`, `deploy/path_safety.py`)

- Archive members are validated before extraction: path traversal, absolute and
  drive-relative paths, Windows-reserved names, symlinks, FIFOs, sockets and
  device entries are rejected.
- Symlink detection now inspects the full Unix mode instead of masking away the
  file type, which previously made the check always false.
- Set-user-ID / set-group-ID bits from archive metadata are dropped; only the
  executable bit is preserved.
- Download and expansion size limits, plus a member count limit, are enforced.
- Destination collisions, including case-only collisions that matter on Windows
  and macOS, are rejected before any write.
- Every destination is validated before the first request, and a mid-download
  failure removes the partial output instead of leaving a half-written script.
- Asset mapping is anchored to the archive root instead of matching any
  substring, and each mapped prefix must actually produce files.
- An incomplete or empty release is an error rather than a "successful" install.

### Audit log integrity (`deploy/audit_log.py`)

- Reading the log never renames, rewrites or repairs it.
- Ownership of a system package requires an explicit, successful, new install.
  Malformed, ambiguous or failed records are treated conservatively, so the
  uninstaller cannot remove tools it did not install.
- A corrupt log is preserved under a unique `.corrupt.<id>` name only when a
  write is actually needed, and saves are atomic.

### Playback script fix (`scripts/smart-paste.lua`)

A local file whose path contained `shorts/`, `youtube.com` or `watch?v=` was
rewritten into a YouTube URL, so opening `~/videos/shorts/holiday.mp4` tried to
stream from the internet. Local paths are now never rewritten, host-relative
links are anchored to a real host, and clipboard/drag-and-drop URL handling is
unchanged. Fifteen cases were re-run against a real Lua interpreter.

## CLI-level fixes that are pending (not on this branch)

These are implemented in a local `setup.py` and pass locally, but that file was
not pushed. Until it is, the CLI on this branch still has the original behavior:

- `--dry-run` writing audit entries, staging directories, `.pyc` files and
  `PATH` changes.
- Dependencies being installed before all downloads are known to have
  succeeded, so a dependency failure can still follow a replaced config.
- Verification not being wired into the transaction as a restore trigger.
- `--migrate-from-old` rewriting the live configuration instead of producing a
  uniquely named review candidate (`mpv.conf.original`, `mpv.conf.new`,
  `REVIEW.txt`).
- `--rollback`, `--verify` and `--uninstall` not returning a failing exit
  status, and `--uninstall` not holding the lock through all of its work or
  writing its log outside a purged directory.

## Tests added or repaired

- `tests/test_transaction.py` — 14 tests, including 64 failure-injection
  subcases (`OSError` and `KeyboardInterrupt` before and after every rename),
  custom-file preservation, legacy symlink migration, lock ownership, unique
  backups, and rollback edge cases.
- `tests/test_portable_fetcher.py` — 11 tests covering traversal, archive member
  types, size and duplicate limits, and cleanup after a failed write.
- `tests/test_audit_log_integrity.py` — 4 tests covering non-mutating reads,
  malformed histories, and package-ownership transitions.
- `tests/test_fetcher_safety.py` — repaired. Both cases previously passed a bare
  release object while the entry carried no `pin`, so the fetcher resolved the
  latest release and indexed `releases[0]` on a dict; both errored before
  asserting anything. The unpinned cases now use a list payload, the pinned path
  has its own case, and the traversal case asserts nothing was written.

## Known issues that are NOT fixed

1. **`scripts/SmartSkip.lua` builds a PowerShell command by string
   interpolation** for its chapter-hash and `mkdir` helpers. Backslash escaping
   does not make a PowerShell double-quoted string safe, so a media filename
   containing `$(...)` can execute code on Windows. This needs a constant
   program with the path passed as data, the pattern now used by
   `ensure_windows_shortcuts`.
2. **`scripts/thumbfast.lua`** calls `setup_storyboards()` before the local
   function is declared, and its fetch-failure branch dereferences a result it
   has just accepted as `nil`. A callback error can also leak the active queue
   counter.
3. **Selective uninstall.** Removal still deletes whole managed directories,
   including custom files inside them. A backup is kept, but per-file removal
   driven by the new manifest hashes is the correct fix.
4. **`tests/test_audit_patches.py`** has two `IndentationError`s and cannot be
   collected, so the suite on this branch does not run to completion.
5. **Bootstrap scripts** (`install.sh`, `install.ps1`) remove an existing
   checkout before validating the new one, use fixed temporary paths, escalate
   privileges around global `pip`, and interpolate paths into PowerShell.
6. **Destructive third-party defaults are unchanged on purpose:**
   `uosc use_trash=no` deletes media permanently, and
   `autosubsync overwrite_old_sub=yes` overwrites your original subtitles.
7. **No `LICENSE` file** at the repository root, while vendored scripts carry
   MPL-2.0 and BSD-2-Clause terms.
8. `test.sh` is a spinner demo, not a test runner.
9. `README.md` still presents hardware-specific numbers as general results.

## Manual validation checklist

Run on each target machine before trusting an install:

1. `python setup.py --dry-run --install` and confirm nothing is written.
2. Install into a throwaway config dir, then confirm playback: a local file, a
   YouTube link, subtitles, thumbnails, and the F8 volume toggle.
3. Edit `mpv.conf.user`, add a custom script, run `--update`, and confirm both
   survive and that a backup directory was created.
4. Interrupt an update with `Ctrl-C` and confirm the configuration still works.
5. `--rollback`, then confirm the pre-rollback state was also snapshotted.
6. `--uninstall --dry-run`, review the plan, and only then uninstall.

## Recovery by hand

Backups are siblings of the configuration directory, named
`<config>.backup.<timestamp>.<id>`. To restore one manually, stop mpv and move it
back into place. If an operation reports a retained recovery directory
(`.<config>.recovery-*`), read its `journal.json` first: `old/` holds your
previous files and must not be deleted until you have restored them.
