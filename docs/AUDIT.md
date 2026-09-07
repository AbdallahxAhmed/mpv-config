# Audit and remediation report

Baseline reviewed: `835e46df0cc5ff11b33e3d01bc3982820852e58f`.
All work described here lives on a review branch. `main` was not modified.

## Status of this branch

Everything described below is **on this branch**. Every pushed file was verified
byte-for-byte after the push by comparing its blob hash against the locally
tested file, so nothing here is "written but not landed".

| File | Purpose |
| --- | --- |
| `deploy/transaction.py` | recoverable same-filesystem transaction engine |
| `deploy/path_safety.py` | validation of untrusted relative paths |
| `deploy/audit_log.py` | non-mutating reads, fail-closed package ownership |
| `deploy/fetcher.py` | archive-member validation, atomic component commit |
| `deploy/deployer.py` | deployment routed through the transaction engine |
| `deploy/verifier.py` | config checks with third-party Lua disabled |
| `setup.py` | CLI rewrite: read-only dry run, ordered install, wired verification |
| `scripts/smart-paste.lua` | local paths are no longer rewritten into URLs |
| `tests/test_transaction.py` | 14 tests, 64 failure-injection subcases |
| `tests/test_portable_fetcher.py` | 11 download and extraction safety tests |
| `tests/test_audit_log_integrity.py` | 4 audit-log integrity tests |
| `tests/test_fetcher_safety.py` | repaired fixtures, pinned-tag coverage |
| `tests/test_audit_patches.py` | repaired collection errors; dry-run guarantees added |
| `tests/test_rollback.py` | repaired to assert behaviour instead of deleted internals |
| `.github/workflows/ci.yml` | continuous integration, which this repository had none of |

## What CI reports

CI now exists and has run on this branch. These are its results, not local
results:

| Check | Result |
| --- | --- |
| Byte-compile (`setup.py`, `deploy/`, `tests/`) | pass |
| Lua syntax, every script in `scripts/` | pass |
| Bootstrap parsing (`install.sh`, `install.ps1`) | pass |
| 8 of the 9 test modules, run individually | pass |
| `tests/test_audit_patches.py` | **1 test fails**, 34 pass |
| Full suite on Ubuntu, Windows and macOS | fails, because it includes that one test |

So **exactly one test in the repository fails**, and it fails for a real reason
described below. Nothing else is red.

Getting to that answer took work worth recording: Action logs cannot be read
without signing in, so the workflow was made to report one check run per test
module, then one per test, then one per individual guarantee. Each failure names
itself in the job title. That is why `ci.yml` runs a per-module matrix.

Two risks that this audit had carried as unverified are now closed by CI:
`tests/test_audit_log_ownership.py` passes against the stricter `audit_log.py`,
and `tests/test_config.py` passes against the rewritten `deployer.py`, so the
configuration templates and the playback tuning they assert are intact.

### The one remaining failure is a real bug

`tests/test_audit_patches.py::test_sync_dependencies_dry_run_is_read_only`
fails. CI probed its three guarantees separately:

| Guarantee | Result |
| --- | --- |
| every result reports `skipped` | holds |
| `_add_to_path` is never called | holds |
| `os.makedirs` is never called | **violated** |

`deploy/installer.py::sync_dependencies(dry_run=True)` reports every package as
`skipped`, and correctly leaves `PATH` alone, but still creates the target tools
directory on disk. A dry run must not write anything, so `--sync-deps
--dry-run` can leave an empty directory behind that did not exist before.

The fix is small and belongs in `deploy/installer.py`: the directory creation in
the `sync_dependencies` path must be guarded so it only runs when `dry_run` is
false. If that `os.makedirs` sits inside `_get_target_tools_dir`, that helper
should resolve the path without creating it, and creation should move to the
call site that actually installs.

That change is **not** made here, and the failing test is deliberately left
failing rather than weakened, so the bug stays visible until the code is fixed.
Weakening the test would have turned CI green while leaving the defect in place.

## What was reviewed

Deployment code (`setup.py`, `deploy/`), configuration templates, vendored mpv
scripts, the bootstrap installers, the existing tests, and the documentation.

## Method, and what "verified" means here

- Bugs were reproduced against the exact baseline sources with mocked HTTP and
  filesystem fixtures, then re-run after the fix.
- Python behaviour was exercised with `unittest`, including failure injection.
- Lua behaviour was exercised with a real Lua 5.4 interpreter and mocked mpv
  APIs. No media, network request, or subprocess was executed.
- **Not validated anywhere:** real playback, GPU output, HDR, Windows and macOS
  end-to-end installs, and package-manager behaviour. Those require the target
  machines. See the manual checklist below.
- **`setup.py` has never been executed**, on any machine. It byte-compiles in
  CI and the tests that import it pass, but no install, update, rollback or
  uninstall has actually been run from it. Treat the first real run as a test:
  use `--dry-run` first, on a throwaway config directory.

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

## CLI-level fixes on this branch (`setup.py`)

These were the original CLI defects, and the rewrite on this branch addresses
each one. None has been exercised by a real run; see the note in *Method*.

- `--dry-run` wrote audit entries, staging directories, `.pyc` files and `PATH`
  changes. The CLI is now read-only in dry run. The one remaining leak is in
  `deploy/installer.py`, described above, and is still open.
- Dependencies were installed before all downloads were known to have
  succeeded, so a dependency failure could follow a replaced config. The fetch
  must now be complete before anything live is touched.
- Verification is wired into the transaction as a restore trigger, so a failed
  verification restores the previous configuration.
- `--migrate-from-old` rewrote the live configuration; it now produces a
  uniquely named review candidate (`mpv.conf.original`, `mpv.conf.new`,
  `REVIEW.txt`).
- `--rollback`, `--verify` and `--uninstall` now return a failing exit status,
  `--uninstall` holds the lock through all of its work, and its log is not
  written inside a directory it is about to purge.

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
- `tests/test_audit_patches.py` — the collection errors are repaired, so all 35
  of its tests now run. A dry-run read-only guarantee and a check that the mpv
  startup probe cannot execute config Lua were added. The shortcut test now
  asserts the path travels as data rather than inside the PowerShell program.
- `tests/test_rollback.py` — repaired. Two of its tests asserted internals that
  no longer exist (a `.rollback.tmp.` name and a `shutil.move` call). One of
  them patched a symbol that is never called, which meant it had silently
  stopped checking that `.git` survives a failed rollback. It now injects the
  failure at the call that is really used and asserts both that `.git` survives
  and that the original file content is intact.

## Known issues that are NOT fixed

1. **`deploy/installer.py` breaks the dry-run contract** by creating the tools
   directory during `--sync-deps --dry-run`. This is the one failing test in
   CI. Details and the fix are in *The one remaining failure* above.
2. **`scripts/SmartSkip.lua` builds a PowerShell command by string
   interpolation** for its chapter-hash and `mkdir` helpers. Backslash escaping
   does not make a PowerShell double-quoted string safe, so a media filename
   containing `$(...)` can execute code on Windows. This needs a constant
   program with the path passed as data, the pattern now used by
   `ensure_windows_shortcuts`.
3. **`scripts/thumbfast.lua`** calls `setup_storyboards()` before the local
   function is declared, and its fetch-failure branch dereferences a result it
   has just accepted as `nil`. A callback error can also leak the active queue
   counter.
4. **Selective uninstall.** Removal still deletes whole managed directories,
   including custom files inside them. A backup is kept, but per-file removal
   driven by the new manifest hashes is the correct fix.
5. **No CLI integration tests.** Every `setup.py` command path is untested and
   unexecuted; the tests cover the modules it calls, not the commands.
6. **Bootstrap scripts** (`install.sh`, `install.ps1`) remove an existing
   checkout before validating the new one, use fixed temporary paths, escalate
   privileges around global `pip`, and interpolate paths into PowerShell. CI
   only checks that they parse.
7. **Destructive third-party defaults are unchanged on purpose:**
   `uosc use_trash=no` deletes media permanently, and
   `autosubsync overwrite_old_sub=yes` overwrites your original subtitles.
8. **No `LICENSE` file** at the repository root, while vendored scripts carry
   MPL-2.0 and BSD-2-Clause terms.
9. `test.sh` is a spinner demo, not a test runner.
10. `README.md` still presents hardware-specific numbers as general results.
11. `setup.py` imports `uuid` without using it.

## Manual validation checklist

Run on each target machine before trusting an install:

1. `python setup.py --dry-run --install` and confirm nothing is written. Note
   that `--sync-deps --dry-run` currently does create the tools directory; see
   the known issue above.
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
