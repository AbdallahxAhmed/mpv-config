# Implementation Plan: Player UI Styles and Themes

**Branch**: `006-player-ui-themes` (directory name only; the maintainer commits to `main`) | **Date**: 2026-11-23, revised 2026-11-24 after EGM Stage 9 round 1 (`.egm/006/`) | **Status**: Planned | **Spec**: [spec.md](spec.md)
**Input**: `specs/006-player-ui-themes/spec.md`, revised after EGM review round 1. Stage 9 fixes accepted ("auto accept"), with one change from the maintainer: no copy of uosc `main.lua` is committed (see "Pin-bump guard").

**Artifacts**: [research.md](research.md) · [data-model.md](data-model.md) · [quickstart.md](quickstart.md) · [contracts/ui-appearance.md](contracts/ui-appearance.md)

## Summary

The looks are owned by a new first-party mpv script, `scripts/ui_appearance.lua`
(the **theme script**). At load it reads `script-opts/ui_appearance.conf` (four
words). It turns the look into uosc option values with the pure module
`scripts/modules/looks.lua`, and writes them into the `script-opts` property in
one write. uosc 5.13.0 re-applies its options when `script-opts` changes
(research R1).

The theme script also builds the More menu and opens it through uosc's
`open-menu`. An Appearance pick saves the file first, then applies the look in
one write, then refreshes the open menu.

No uosc patch is needed. The deployer gets one small seeding migration so that
`mpv-config update` adds `ui_appearance.conf` where it is missing (R3). Two
startup-only uosc keys go into `mpv.conf.template` (R2). Two existing scripts
each publish one `user-data` value, so the More menu can mark the Anime4K mode
and stable volume (R5). The stream-quality button redraws when Size changes (R8).

A pin-bump guard checks a small committed facts file (uosc option names and
defaults, plus the SHA-256 of the pinned `main.lua`). The weekly release check
regenerates those facts from the downloaded release (R9).

## Technical Context

**Language/Version**: Lua 5.1 / LuaJIT as embedded in mpv 0.40+ (scripts); Python 3.11+ (deployer, tests, release check)
**Primary Dependencies**: uosc 5.13.0 (pinned; not patched by this feature); mpv `mp.options`, `mp.utils`
**Storage**: `script-opts/ui_appearance.conf` (two comment lines, four `key=value` lines)
**Testing**: `python -m unittest discover -s tests` (project venv, `PYTHONPATH=src`); `python tests/run_lua_tests.py` (runs every `tests/lua/test_*.lua` inside mpv)
**Target Platform**: Linux KDE Wayland and Windows (Tier 1); macOS best effort
**Project Type**: mpv configuration + deploy tool
**Performance Goals**: a pick shows within 1 s; no playback impact (spec 004 pass table)
**Constraints**: no uosc patch (C-001); no copy of uosc `main.lua` in the repo; the deployer must not edit `uosc.conf` or `input.conf`; Python uses pathlib and never `shell=True`; no secrets or personal paths
**Scale/Scope**: 1 new script (~250 lines), 1 new module (~350 lines), small edits to 3 existing scripts, 1 deployer migration, 1 template edit, 1 shipped conf, 1 facts fixture, release-check extension, tests, docs

## Constitution Check

| Principle | Status |
|---|---|
| I. Boundary separation | Pass. Lua and conf stay in `scripts/` and `config/`; Python stays in `deploy/`, `tools/` and `tests/`. The deployer copies the shipped conf; it embeds no config literal. |
| II. Cross-platform parity | Pass. The looks are the same everywhere. The only file write uses `io.open` in place, which works on Windows (R3). |
| III. Dependency classification | Pass. No new dependency. |
| IV. Shell compatibility | Not affected. |
| V. Aesthetic CLI UX | Pass. The seeding migration reports through the existing migration result rows. |
| VI. User customization sovereignty | Pass. `ui_appearance.conf` is seeded only when missing. `uosc.conf` and `input.conf` are not touched. Hand edits to the owned uosc keys no longer take effect at runtime; README and CHANGELOG say so (spec M3). |
| VII. Idempotent operations | Pass. Running update twice changes nothing. The same look always produces byte-identical `uosc-*` values, because sub-keys have a fixed order (data-model.md). |
| Branching rule | Deviation, as in spec 005: the maintainer commits to `main`. |

Re-checked after Phase 1 design: no change.

## Design

### Components

| File | Action | Phase |
|---|---|---|
| `scripts/modules/looks.lua` | new: pure tables and functions ([contract](contracts/ui-appearance.md)) | P1, grown in P3, P4 |
| `scripts/ui_appearance.lua` | new: load, apply, save, More menu, script messages | P1, grown in P3, P4 |
| `config/script-opts/ui_appearance.conf` | new: the defaults, byte-identical to `looks.serialize(looks.DEFAULTS)` | P1 |
| `deploy/deployer.py` | modify: `_migrate_ui_appearance_conf`, registered in `_migrate_deployed_configs` | P1 |
| `config/mpv.conf.template` | modify: two `script-opts-append` lines after `osd-fonts-dir` | P1 |
| `tests/lua/test_ui_appearance.lua` | new: module, load and apply, pick, More menu, contrast | P1, grown in P3, P4 |
| `tests/test_ui_appearance.py` | new: deployer seeding, template lines, guard against the facts fixture | P1, P2 |
| `tests/fixtures/uosc-5.13.0/uosc-options.json` | new: facts fixture (R9) | P2 |
| `tests/fixtures/uosc-5.13.0/README.md` | modify: row for the facts fixture | P2 |
| `tools/check_uosc_release.py` | modify: facts extraction, option checks, `--tag`, `--write-options` | P2 |
| `tests/test_uosc_release_check.py` | modify: `GOOD_ZIP` gets a synthetic `main.lua`; output assertions; new cases | P2 |
| `.github/workflows/uosc-release-check.yml` | modify: step name; the pinned-tag facts comparison | P2 |
| `specs/005-playlist-drag-reorder/contracts/uosc-release-check.md` | modify: new checks, messages, exit codes, flags | P2 |
| `scripts/player-toolbar.lua` | modify: stable-volume user-data; republish quality on a Size change | P3 (republish), P4 (user-data) |
| `tests/lua/test_player_toolbar.lua` | modify: tests for both | P3, P4 |
| `scripts/profile_picker.lua` | modify: publish `user-data/anime4k/mode` | P4 |
| `tests/lua/test_profile_picker.lua` | modify: tests for it | P4 |
| `scripts/help_overlay.lua` | modify: the menu row | P5 |
| `README.md`, `README.ar.md`, `docs/YOUTUBE_GUI.md`, `CHANGELOG.md`, `AGENTS.md` | modify | P5 |

### Load and apply (FR-011 to FR-013)

1. `local raw = {style = '', background = '', accent = '', size = ''}`, then
   `opt.read_options(raw, 'ui_appearance')`. The empty defaults let a missing
   file or a missing line show up as an empty value.
2. `local look, fallbacks = looks.normalize(raw)`. `normalize` replaces each
   empty or invalid field with `looks.DEFAULTS` and lists that field in
   `fallbacks`. If `fallbacks` is not empty, the script logs one `msg.warn`:
   `ui_appearance.conf: using defaults for <fields>`. A missing or unreadable
   file falls back on all four fields. Once the deployer has seeded the file
   (P1), a missing file is abnormal.
3. `mp.set_property_native('script-opts', looks.merge_script_opts(mp.get_property_native('script-opts') or {}, look))`.
   This is the **apply write** (one property write).
4. The shuffle flag starts from a plain-text read of `~~/script-opts/uosc.conf`:
   the last `shuffle=` line; `yes` means on, anything else or no file means off.

When uosc is absent, nothing reads the `uosc-*` keys and there is no More
button, so the script loads without errors and nothing visible changes. A P1
Lua test loads the script with no uosc and expects no error.

### A pick: `set <field> <value>` (FR-010, FR-014)

1. Check `value` against `looks.CHOICES[field]`. If it is not allowed:
   `msg.warn`, then return. Nothing is saved or applied.
2. Write `looks.serialize(new_look)` in place (`io.open(path, 'w')`). The path
   comes from `mp.find_config_file('script-opts/ui_appearance.conf')`, or, when
   the file is missing, from `mp.command_native({'expand-path', '~~/script-opts/ui_appearance.conf'})`,
   as `profile_picker.lua` `mode_file_path` does. If `io.open` returns nil and an
   error: `mp.osd_message('Appearance not saved: ' .. err, 3)`, then continue.
3. Apply with the apply write ("Load and apply", step 3).
4. Re-read the menu state and send `script-message-to uosc update-menu <json>`
   with `looks.more_menu(look, state)`. uosc ignores the message unless a menu
   of type `ui_appearance_more` is open (`main.lua:1103-1104`). No open-tracking
   and no `on_close` handler are needed.

### More menu (FR-017 to FR-020)

`open-more` reads `state` (fields in the contract) and sends
`script-message-to uosc open-menu <json>` with `looks.more_menu(look, state)`.
The root title is `More` and the type is `ui_appearance_more`. The rows and
their commands are in data-model.md. Rows marked active carry no hint (FR-023
exception). The menu grows by phase:

| After | Top-level rows |
|---|---|
| P1 | Paste link, Stable volume, Full uosc menu, All shortcuts |
| P3 | Appearance, then the P1 rows |
| P4 | the full menu of data-model.md (Paste link moves into Open, and Stable volume into Picture & sound) |

So no commit leaves a control unreachable: from P1 on, the More button opens
this menu, and Full uosc menu reaches every uosc default entry.

### Startup-only keys (R2)

`config/mpv.conf.template` gets these two lines directly after the
`osd-fonts-dir` line in the "UI / uosc compatibility" block:

```
script-opts-append        = uosc-border_radius=10
script-opts-append        = uosc-chapter_ranges=openings:7cc4fa64,endings:7cc4fa64,ads:c54e4e80
```

### Seeding migration (FR-015, R3)

`_migrate_ui_appearance_conf(conf_path, repo_config_dir, audit_log=None)` in
`deploy/deployer.py`, modelled on `_migrate_anime4k_conf`:

- If `conf_path` is missing, it copies `config/script-opts/ui_appearance.conf`
  to it with `shutil.copyfile`, records `create` in the audit log, and returns True.
- Otherwise it returns False and leaves the file untouched.
- It is registered in `_migrate_deployed_configs` under the name
  `seed-ui-appearance-conf`, so it runs on install and on update.
- On install, `deploy()` copies the file first, so the migration finds it
  present and does nothing.
- Paths use `pathlib.Path`.

### Pin-bump guard (FR-016, R9)

No copy of uosc `main.lua` is committed. Instead:

- **Facts fixture**: `tests/fixtures/uosc-5.13.0/uosc-options.json`, shape in
  data-model.md. It holds the `defaults` option names and their default source
  text, the `config_defaults.color` and `config_defaults.opacity` sub-keys with
  their defaults, whether the runtime handler is registered, the `bind_command`
  names, the uosc version, and the SHA-256 of upstream 5.13.0 `main.lua`. It is
  written with `json.dumps(facts, indent=2, sort_keys=True) + "\n"`.
- **Functions in `tools/check_uosc_release.py`**:
  - `extract_uosc_facts(main_lua: bytes, version: str) -> dict` builds the facts
    from `main.lua` text with line-anchored regexes. It parses the `defaults = {`
    block up to the first line `}`, the `color = {` and `opacity = {` blocks
    inside `local config_defaults = {`, the literal
    `opt.read_options(options, 'uosc', handle_options)`, and every
    `bind_command('<name>'`. If a block is not found it raises `CheckError`
    (exit 2, "main.lua: <block> not found").
  - `read_looks_keys(looks_lua: Path) -> tuple[list[str], list[str], list[str]]`
    parses `OWNED_KEYS`, `OWNED_COLOR_KEYS` and `OWNED_OPACITY_KEYS` from
    `scripts/modules/looks.lua`, and `MORE_UOSC_BINDINGS`, the uosc binding
    names the More menu uses.
  - `check_options(facts, owned, color_keys, opacity_keys, bindings) -> list[str]`
    returns one problem line per gap, in this order:
    - `uosc <ver>: option <key> missing`
    - `uosc <ver>: color <key> missing`
    - `uosc <ver>: opacity <key> missing`
    - `uosc <ver>: runtime option handler missing`
    - `uosc <ver>: binding <name> missing`
  - `check_menu_constants(menu_lua: bytes) -> list[str]` checks the substrings in
    research R9. The problem line is `uosc <ver>: menu constant "<text>" missing`.
- **Release-check flow**: `run()` reads `elements/Menu.lua` and `main.lua` from
  the zip with `_members_from_zip(data) -> dict[str, bytes]`. A missing
  `main.lua` exits 2 with `release zip has no scripts/uosc/main.lua`. The run
  then does the anchor check, `check_menu_constants`, `extract_uosc_facts` and
  `check_options`.
  - Any problem prints its line with the `::error` prefix and exits 1.
  - On success it prints the anchor line, then
    `uosc <ver>: <n> owned options, runtime handler and <m> bindings present`.
  - `--uosc-dir DIR` reads `DIR/main.lua` the same way.
- **New flags**:
  - `--tag TAG` checks that release instead of the latest (API
    `.../releases/tags/TAG`).
  - `--write-options PATH` writes the extracted facts to PATH. It is used to
    create the fixture and to regenerate it on a pin bump.
  - `--compare-options PATH` exits 1 when the extracted facts differ from PATH,
    and prints the first differing key.
- **Weekly job**: two steps.
  - `--latest`: the existing check plus the option checks, on facts
    regenerated from that release.
  - `--tag 5.13.0 --compare-options tests/fixtures/uosc-5.13.0/uosc-options.json`:
    regenerates the pinned facts and fails if they differ from the committed
    file. This catches a re-published tag or extractor drift.
- **Offline tests** (`tests/test_ui_appearance.py`):
  - `check_options` runs against the committed fixture, with the keys read from
    `looks.lua`.
  - `check_menu_constants` runs against the committed `Menu.lua` fixture.
  - `extract_uosc_facts` runs on a synthetic `main.lua` snippet written in the
    test, with no upstream text.
  - A fixture with one key removed (built in the test) gives exactly one problem
    line that names the key.

## Implementation phases (one commit each)

| Phase | Content | Tests added | Stories |
|---|---|---|---|
| **P1. Looks** | `looks.lua` (`DEFAULTS`, `CHOICES`, the owned key tables, `MORE_UOSC_BINDINGS`, `normalize`, `uosc_options`, `merge_script_opts`, `serialize`, `more_menu` with the P1 rows); `ui_appearance.lua` with load and apply, and `open-more`; shipped conf; seeding migration; the two `mpv.conf.template` lines | Lua: every look's options equal data-model.md, byte for byte; only owned keys; other `script-opts` entries kept; one apply write at load; fallback warning for a missing file, a missing line and an invalid value (FR-013); loads with no uosc; the P1 More rows; contrast (SC-004, model in research R6); `serialize(DEFAULTS)` equals the shipped conf byte for byte. Python: install seeds the conf, update seeds a missing one and keeps a changed one byte for byte (SC-008, using `DeployerTestCase` from `tests/test_deploy_uosc_reorder_patch.py` and `_migrate_deployed_configs`); the template has the two lines | US1, US2-3, US2-5 |
| **Live check (reviewer)** | After the P1 commit: in a nested KWin session, start mpv with uosc and the theme script, then confirm that the calm look appears and that a hand-sent `set style focus` re-lays out the controls. If it fails, stop before P2. | — | R1 |
| **P2. Guard** | `uosc-options.json` (generated with `--tag 5.13.0 --write-options`), README row, `check_uosc_release.py` extension, workflow, spec 005 contract amendment | Python: the offline tests listed under "Pin-bump guard"; `tests/test_uosc_release_check.py` gets a synthetic `main.lua` in `GOOD_ZIP` (a `defaults` block with the owned keys, the two `config_defaults` blocks, the handler line, the bindings) and the new success line in its exact-output assertions; new cases for a missing key, a missing handler and a zip without `main.lua` (exit 2) | FR-016 |
| **P3. Switching** | `set` message, save then apply, the failed-save message, `update-menu`, the Appearance submenu at the top of More; in `player-toolbar.lua`, observe `options/script-opts` and call `publish_quality(true)` when `uosc-controls_size` changes | Lua: the file is written before the apply write; one apply write per pick; the last pick wins; with `io.open` stubbed to return nil, the error OSD shows and the look still applies; Appearance marks the current values; an invalid value is ignored. `test_player_toolbar.lua`: republish only on a `uosc-controls_size` change | US2 |
| **P4. Full More** | the full `more_menu` (data-model.md); `toggle-shuffle`; `profile_picker.lua` publishes `user-data/anime4k/mode` (the saved mode `state.mode`) at load, in `apply_mode` and in `on_shaders_changed`; `player-toolbar.lua` sets `user-data/player_toolbar/stable-volume` in `publish()` before its early return | Lua: every row's command is in the allowed set (SC-005, research R5); conditional rows for a local file vs a stream, one vs two real video tracks (image and album-art tracks not counted), and one vs two editions (FR-019); active rows carry no hint; shuffle flips on `toggle-shuffle` and starts from `uosc.conf`. `test_profile_picker.lua`: the user-data value at load, after `set-mode` and after a shader change. `test_player_toolbar.lua`: the stable-volume value | US3 |
| **P5. Docs** | help overlay row `{ "More button", "appearance, playback, open, all menus" }`; README, README.ar, YOUTUBE_GUI (new More menu and styles); CHANGELOG: existing installs move to the default look (calm, dark, amber, comfortable); `--keep-conf`, a re-install over an existing `mpv.conf`, or a plain `script-opts=` in `mpv.conf.user` keeps radius 8 and the old range colour; hand edits to owned uosc keys have no effect; AGENTS.md status | the existing `tests/test_readme_toc.py` and `tests/test_repo_hygiene.py` stay green | — |

Manual checks after P5: [quickstart.md](quickstart.md), on KDE Wayland and Windows.

## Risks

| Risk | Mitigation |
|---|---|
| uosc does not re-apply an owned key at runtime as R1 reads it from source | The reviewer's live check after P1 decides whether P2 and later go ahead. |
| A uosc release changes or removes an option, a colour or opacity sub-key, the handler, a binding or a menu constant | The guard catches each of these, offline and weekly. It does not catch an element that stops re-reading an option in `on_options`, so quickstart step 2 is re-run before any pin bump (spec 005, C-009). |
| The pinned tag is re-published, or the extractor drifts | The weekly `--compare-options` step against the committed facts. |
| The pre-feature uosc controls (from `uosc.conf`) flash when mpv starts idle (R10) | Quickstart step 3 checks it. If the flash is visible, a follow-up changes the shipped `config/script-opts/uosc.conf` to the default look's values, which affects fresh installs only. That is outside these phases. |
| A user's own `script-opts=uosc-…` entries for owned keys | Owned keys are overwritten at runtime; the read-merge-write keeps every other entry. Documented in README and CHANGELOG (P5). |
| Shuffle is toggled by a route the theme script does not see | No key binds `uosc/shuffle`, no style keeps the shuffle button, and uosc's default menu has no shuffle row, so `toggle-shuffle` is the only route. |
| A torn write of `ui_appearance.conf` | A cut-off value or a missing line falls back and is logged (FR-013). |

## Project Structure

### Documentation (this feature)

```text
specs/006-player-ui-themes/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/ui-appearance.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code

See "Components"; no new directories.

## Complexity Tracking

No constitution violation needs justification, beyond the documented deviation of committing to `main`.
