# Implementation Plan: Player UI Styles and Themes

**Branch**: `006-player-ui-themes` (directory name only; the maintainer commits to `main`) | **Date**: 2026-11-23 | **Status**: Planned | **Spec**: [spec.md](spec.md)
**Input**: `specs/006-player-ui-themes/spec.md`, revised after EGM review round 1 (`.egm/006/`)

**Artifacts**: [research.md](research.md) · [data-model.md](data-model.md) · [quickstart.md](quickstart.md) · [contracts/ui-appearance.md](contracts/ui-appearance.md)

## Summary

A new first-party mpv script, `scripts/ui_appearance.lua`, owns the looks. At
load it reads `script-opts/ui_appearance.conf` (four words), turns the look into
uosc option values with the pure module `scripts/modules/looks.lua`, and writes
them into the `script-opts` property in one write. uosc 5.13.0 re-applies its
options when `script-opts` changes (research R1). The same script builds the
More menu and opens it through uosc's `open-menu`; an Appearance pick saves the
file first, then applies the look in one write and refreshes the open menu.

No uosc patch. The deployer is unchanged: the shipped
`config/script-opts/ui_appearance.conf` is copied only when missing, which gives
fresh installs the defaults, keeps a user's choice on update, and moves existing
installs to the default look (R3). Two startup-only uosc keys go into
`mpv.conf.template` (R2). Two existing scripts publish one `user-data` value each
so the More menu can mark Anime4K mode and stable volume (R5), and the toolbar
redraws the stream-quality label on a Size change (R8).

## Technical Context

**Language/Version**: Lua 5.1 / LuaJIT as embedded in mpv 0.40+ (scripts); Python 3.11+ (tests, release check)
**Primary Dependencies**: uosc 5.13.0 (pinned, unpatched by this feature); mpv `mp.options`, `mp.utils`
**Storage**: `script-opts/ui_appearance.conf` (four `key=value` lines)
**Testing**: `python -m unittest discover -s tests` (project venv, `PYTHONPATH=src`); `python tests/run_lua_tests.py` (runs every `tests/lua/test_*.lua` inside mpv)
**Target Platform**: Linux KDE Wayland and Windows (Tier 1); macOS best effort
**Project Type**: mpv configuration + deploy tool
**Performance Goals**: a pick shows within 1 s; no playback impact (spec 004 pass table)
**Constraints**: no uosc patch (C-001); no edits to `uosc.conf` or `input.conf` by the deployer; pathlib and no `shell=True` in Python; no personal paths
**Scale/Scope**: 1 new script (~250 lines), 1 new module (~300 lines), 2 small edits to existing scripts, 1 template edit, 1 shipped conf, 1 fixture, tests, docs

## Constitution Check

| Principle | Status |
|---|---|
| I. Boundary separation | Pass. Lua and conf stay in `scripts/` and `config/`; Python checks stay in `tests/` and `tools/`. |
| II. Cross-platform parity | Pass. Same looks everywhere; the only file write uses `io.open` in place (works on Windows, R3). |
| III. Dependency classification | Pass. No new dependency. |
| IV. Shell compatibility | Not affected. |
| V. Aesthetic CLI UX | Not affected (no new deployer output). |
| VI. User customization sovereignty | Pass. `ui_appearance.conf` is kept on update; `uosc.conf` and `input.conf` are not touched. Hand edits to the owned uosc keys stop having effect at runtime; documented in README and CHANGELOG (spec M3). |
| VII. Idempotent operations | Pass. Update twice changes nothing; applying the same look twice writes the same `script-opts`. |
| Branching rule | Deviation, as in spec 005: the maintainer commits to `main`. |

Re-checked after Phase 1 design: no change.

## Design

### Components

```text
scripts/ui_appearance.lua          new: load, apply, save, More menu, script messages
scripts/modules/looks.lua          new: pure tables and functions (contracts/ui-appearance.md)
config/script-opts/ui_appearance.conf   new: the four defaults
config/mpv.conf.template           edit: script-opts-append for border_radius, chapter_ranges
scripts/profile_picker.lua         edit: publish user-data/anime4k/mode in apply_mode
scripts/player-toolbar.lua         edit: publish user-data/player_toolbar/stable-volume; republish quality on uosc-controls_size change
scripts/help_overlay.lua           edit: the "menu button" row describes the new More menu
tests/fixtures/uosc-5.13.0/main.lua     new: upstream file, SHA-256 pinned
tools/check_uosc_release.py        edit: also check main.lua and the Menu.lua opacity constants (R9)
tests/lua/test_ui_appearance.lua   new
tests/test_ui_appearance.py        new: option-existence, contrast, deployer seeding
README.md, README.ar.md, docs/YOUTUBE_GUI.md, CHANGELOG.md   edit
```

### Load and apply (FR-010 to FR-013)

1. `read_options(opts, 'ui_appearance')` with string defaults from `looks.DEFAULTS`.
2. `looks.normalize(opts)`; if `fallbacks` is not empty, one `msg.warn` listing them.
3. `mp.set_property_native('script-opts', looks.merge_script_opts(mp.get_property_native('script-opts') or {}, look))`.
4. If uosc is absent, nobody reads the `uosc-*` keys and the More button does not exist, so the script loads without errors and does nothing visible (Edge Cases).

### A pick (`set <field> <value>`)

1. Validate against `looks.CHOICES`; on failure log and return.
2. Write `looks.serialize(new_look)` in place. On failure: `mp.osd_message('Appearance not saved: <reason>', 3)` and continue.
3. Apply with one `script-opts` write (step 3 above).
4. If the More menu is open (the script tracks `open-more` and the menu's `on_close` callback), send `update-menu` with `looks.more_menu(...)`.

### More menu

`looks.more_menu(look, state)` builds the tree in data-model.md. `state` is read
when the menu opens: `loop-playlist`, `loop-file`, `speed`, `track-list`,
`edition-list`, `demuxer-via-network`, `user-data/anime4k/mode`,
`user-data/player_toolbar/stable-volume`, and the tracked shuffle flag (R5).
The menu has `type = 'ui_appearance_more'` and an `on_close` message back to
the script. Active rows get no hint.

### Startup-only keys (R2)

`config/mpv.conf.template` gains, under "UI / uosc compatibility":

```
script-opts-append        = uosc-border_radius=10
script-opts-append        = uosc-chapter_ranges=openings:7cc4fa64,endings:7cc4fa64,ads:c54e4e80
```

### Pin-bump guard (FR-016, R9)

`tests/test_ui_appearance.py` parses `OWNED_KEYS` from `looks.lua`, then checks
the fixture `main.lua`: every key is a field of `defaults`, and
`opt.read_options(options, 'uosc', handle_options)` is present. It also checks
the fixture `Menu.lua` still contains the opacity expressions the contrast test
assumes. `tools/check_uosc_release.py --latest` runs the same functions on the
release zip's `scripts/uosc/main.lua` and `elements/Menu.lua`, so the weekly job
fails on a release that breaks them.

## Implementation phases (one commit each)

| Phase | Content | Tests added | Stories |
|---|---|---|---|
| 1. Guard | `main.lua` fixture with pinned hash; the option-existence and handler check; release-check extension | Python: fixture hash, owned keys exist (against a stub key list until phase 2), handler present, release check on a fixture with a key removed fails and names it | FR-016 |
| 2. Looks | `looks.lua` (tables, `normalize`, `uosc_options`, `merge_script_opts`, `serialize`); `ui_appearance.lua` load-and-apply; shipped conf; `mpv.conf.template` lines | Lua: every look's options match data-model.md, only owned keys, complete `color`/`opacity`, other `script-opts` kept, one write at load, fallback warning (SC-007). Python: contrast over all 15 pairs with real opacities (SC-004); deployer seeds/keeps/adds the conf (SC-008); template has the two lines | US1 |
| 3. Switching | `set` message, save-then-apply, failed-save message, Appearance submenu, `update-menu`; `player-toolbar.lua` quality republish on Size change | Lua: a pick writes the file before `script-opts`, one write per pick, last pick wins, read-only file shows the message and still applies, Appearance marks current values; toolbar republishes on `uosc-controls_size` change only | US2 |
| 4. More menu | full `more_menu`; `profile_picker.lua` and `player-toolbar.lua` user-data; shuffle tracking | Lua: every row's command is in the allowed set built from `input.conf.template`, the uosc binding list and the toolbar messages (SC-005); conditional rows on local vs stream, one vs two video tracks and editions (FR-019); active rows carry no hint; the two user-data values are published | US3 |
| 5. Docs | help overlay row, READMEs, YOUTUBE_GUI, CHANGELOG (existing installs move to calm; `--keep-conf` keeps radius 8 until `mpv.conf` is regenerated; hand edits to owned keys have no effect), AGENTS.md status | existing doc tests (`test_readme_toc.py`, hygiene) stay green | — |

Manual checks after phase 5: [quickstart.md](quickstart.md), on KDE Wayland and Windows.

## Risks

| Risk | Mitigation |
|---|---|
| Visible flash of today's toolbar when mpv starts idle (R10) | Quickstart step 3 checks it. If visible, ship `config/script-opts/uosc.conf` with the calm/dark/amber/comfortable values so fresh installs start in the default look (existing installs keep their `uosc.conf`); a follow-up, not in these phases. |
| A uosc option silently stops applying at runtime after a pin bump | FR-016 guard in tests and in the weekly release check; the pin is bumped by hand only after it passes (spec 005, C-009). |
| A user's own `script-opts=uosc-…` entries in `mpv.conf.user` for owned keys | They are overwritten at runtime for owned keys only; others are kept by the read-merge-write. Documented. |
| Shuffle mark drifts from uosc's state | Only the More row toggles shuffle in every style (R5); the theme resets its flag from uosc's `shuffle` option at load. |
| Torn write of `ui_appearance.conf` | Four short lines written in one `write`; a torn file fails validation and falls back per field (FR-013). |

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
└── tasks.md              (next step)
```

### Source Code

See "Components" above; no new directories.

## Complexity Tracking

No constitution violation needs justification beyond the documented `main` branching deviation.
