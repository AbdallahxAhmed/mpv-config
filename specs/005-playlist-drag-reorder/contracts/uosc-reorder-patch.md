# Contract: uosc playlist-reorder patcher

**Module**: `tools/patch_uosc_playlist_reorder.py` (stdlib, `pathlib` only, no `subprocess`)
**Payload**: `tools/uosc_patches/playlist_reorder.lua` (LF, tabs; inserted verbatim)
**Target**: `elements/Menu.lua` only. `lib/menus.lua` is not touched (research R4).
**Replaces**: `tools/patch_uosc_playlist_drag.py` (removed under C-006)

## Constants

```python
PATCH_NAME = "uosc-playlist-reorder"            # every message uses this name
PATCH_VERSION = 1                               # bump on any payload or hook change (pinned by test)
MARKER = b" -- mpv-config:playlist-reorder v1"  # trailing marker on each hook line (written)
MARKER_TOKEN = b"mpv-config:playlist-reorder"     # version-free "marker present" test (R12 step 1)
PAYLOAD_PATH = Path(__file__).parent / "uosc_patches" / "playlist_reorder.lua"
PAYLOAD = PAYLOAD_PATH.read_bytes()             # read at import; a missing file raises (packaging error, not `skipped`)
PAYLOAD_SHA256 = "<sha256 of PAYLOAD>"          # checked by test against the file, tied to PATCH_VERSION
TARGET = "elements/Menu.lua"
PIN = "5.13.0"
EXPECTED_UPSTREAM_SHA256 = {TARGET: "0cbc42afbe72f3f76f069995744de1e772d706445ed7987d1bffaafed50f2f49"}
HUNKS: tuple[Hunk, ...]                         # 8 hunks (payload + 7 hooks), exact lines in research.md R4

class PatchState(Enum): ABSENT, FOREIGN, UNEXPECTED_UPSTREAM, PATCHED, BROKEN_ANCHOR, UPSTREAM
@dataclass(frozen=True) class Hunk: id: str; anchor: bytes; insertion: bytes; where: str  # "before" | "after"
@dataclass(frozen=True) class AnchorFailure: hunk_id: str; found: int
@dataclass(frozen=True) class PatchResult: status: str; changed: bool; detail: str
```

## Pure functions (bytes in, bytes out; no I/O)

| Function | Output | Raises | Hash check |
|---|---|---|---|
| `check_anchors(data)` | `list[AnchorFailure]`, **all** failures | never | no |
| `detect_state(data, *, verify_hash=True)` | a `PatchState` other than `ABSENT`, by the procedure in research R12. Its round-trip step calls `patch_bytes(unpatched, verify_hash=False)` and treats a raise as `FOREIGN` | never | if `verify_hash` |
| `patch_bytes(data, *, verify_hash=True)` | patched bytes | `PatchError(state, detail)` unless the state is `UPSTREAM` | if `verify_hash` |
| `unpatch_bytes(data)` | original upstream bytes | `PatchError` if any insertion is not found exactly once | no |

Guarantees, each covered by a test against the 5.13.0 fixture:

1. `unpatch_bytes(patch_bytes(f)) == f`, byte for byte.
2. `detect_state(patch_bytes(f)) == PATCHED`, and `apply()` on a patched tree writes
   nothing (`st_mtime_ns` and `st_ino` unchanged).
3. All-or-nothing: if any hunk fails, no output is produced and the input is
   unchanged.
4. No regexes, no `strip`, no newline translation; every comparison is on bytes.
5. In the patched file, the `reorder_handle` hook line comes after the last
   `cursor:zone('primary_click'` of the action loop (research R5).
6. A patched copy of bytes that are not the pinned release gives
   `UNEXPECTED_UPSTREAM` and `skipped`, and nothing raises.

## I/O entry point

```python
def apply(uosc_dir: Path, *, unpatch: bool = False) -> PatchResult
```

1. If `uosc_dir / TARGET` is missing, return `absent` and write nothing.
2. Read the file with `read_bytes()`. Call `detect_state(data)` with
   `verify_hash=True`.
3. `UPSTREAM` with `unpatch=False`, or `PATCHED` with `unpatch=True`: compute the
   new bytes and write them:
   - write `Menu.lua.mpvcfg-tmp` in the same directory;
   - `tmp.chmod(st.st_mode)` (pathlib) to the original's mode;
   - `Path.replace()` it over the target.

   On `OSError` at any step, remove the temp file if it exists, leave the original
   untouched (`os.replace` is atomic), and return `skipped` with the I/O detail.
   Any other exception propagates.
4. `PATCHED` (patch) returns `already-patched`. `UPSTREAM` (unpatch) returns
   `already-unpatched`. Neither writes anything.
5. `FOREIGN`, `UNEXPECTED_UPSTREAM` and `BROKEN_ANCHOR` return `skipped`, write
   nothing, and use the detail strings from
   [data-model.md](../data-model.md#patch-result-apply--deployer-result-row).

## CLI

```text
python -m tools.patch_uosc_playlist_reorder [--uosc-dir DIR] [--unpatch] [--check]
```

| Flag | Effect | Exit |
|---|---|---|
| none | `apply(dir)` | 0 `patched`/`already-patched` · 1 `skipped` · 2 `absent` |
| `--unpatch` | `apply(dir, unpatch=True)` | 0 `unpatched`/`already-unpatched` · 1 `skipped` · 2 `absent` |
| `--check` | `check_anchors` on the file, no writes | 0 all match · 1 any failure (all listed) |

Output: one line per run, `{PATCH_NAME}: {status} -- {detail}` (no ` -- ` part when
`detail` is empty). `--check` prints `anchor {hunk_id} matched {found}x` for each
failure, or `{PATCH_NAME}: all 8 anchors match`.

The `--uosc-dir` default reuses `get_default_uosc_dir()` from
`tools/patch_uosc_timeline_thumb.py:26-35`. It is imported, not copied.

## Deployer integration

```python
# deploy/deployer.py
def _patch_prepared_uosc(prepared: Path, staging: Path, config_dir: Path,
                         lockfile: dict | None) -> dict:
    """One result row: {"name": "uosc-playlist-reorder-patch", "status": ..., "detail": ...}."""

# deploy/transaction.py
def update_assets(config_dir, staging_dir, repo_dir, metadata, prepare_hook=None):
    ...
    prepare_assets(config_dir, staging_dir, repo_dir, prepared)
    if prepare_hook is not None:
        prepare_hook(prepared)          # return value ignored; prepared is a str
    manifest = asset_manifest(metadata, staging_dir, repo_dir, prepared)
    ...
```

`_patch_prepared_uosc` does the following:

- It imports the patcher inside the function
  (`from tools.patch_uosc_playlist_reorder import apply`), like the existing lazy
  `tools` imports (`deployer.py:1027`, 1457-1458, 1484).

- It sets `source = "staged"` if `staging / "scripts/uosc/elements/Menu.lua"`
  exists, and `"live"` otherwise.
- It sets `version` from `lockfile["scripts"]["uosc"]["version"]` (staged). If that
  is not available, it reads `config_dir / tx.MANIFEST`
  (`scripts.uosc.version`, via `json.loads(path.read_text(encoding="utf-8"))`,
  matching `tx._write_json`). If that raises `OSError`, `ValueError`, `KeyError` or
  `TypeError`, the version is `"unknown"`.
- It calls `apply(prepared / "scripts" / "uosc")` and maps the result with the
  table in data-model.md: `ok`, `warn`, or `skipped` for `absent`.

**Install** (`deploy()`), right after `tx.prepare_assets(...)` at `deployer.py:1313`:

```python
results.append(_patch_prepared_uosc(Path(prepared), Path(staging_dir), Path(config_dir), lockfile))
```

**Required in the same change**: delete the function-local `from pathlib import Path`
at `deployer.py:1455`, inside the post-commit `try`. That line makes `Path` local to
all of `deploy()`, so the call above would raise `UnboundLocalError` (ruff F823).
The module already imports `Path` at line 17. A test runs the real `deploy()` with a
staged uosc to keep this fixed.

`cmd_install` shows the rows through `ui.summary`. A `warn` row is listed under
**Warnings**, not under Failed (plan, "Summary warnings"), and install exits 0.

**Update** (`cmd_update()`, `deployer.py:3350`):

```python
patch_rows = []
backup = tx.update_assets(
    config_dir, staging, str(REPO_ROOT), lockfile,
    prepare_hook=lambda p: patch_rows.append(
        _patch_prepared_uosc(Path(p), Path(staging), Path(config_dir), lockfile)),
)
for row in patch_rows:     # right after update_assets returns, before the audit log
    if row["status"] != "warn":
        ui.info(f"{row['name']}: {row['detail']}")
ui.summary(patch_rows)     # the Warnings block is the ONLY place a skipped patch is shown
```

A skipped patch is shown exactly once, as the Warnings block of that summary. There
is no `ui.warn` call for it (SC-008), and the update exits 0. No call is added to
`_migrate_deployed_configs()`.
