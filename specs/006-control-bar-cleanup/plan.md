# Implementation Plan: Control bar cleanup

**Branch**: `006-control-bar-cleanup` (directory name only) | **Date**: 2026-11-25 | **Spec**: [spec.md](spec.md)

## Summary

Revert the theme work in one commit, then add a small More menu script, a
new `controls=` line, and three deployer migrations that bring existing
installs onto it. The earlier theme plan is dropped (see the spec).

## Technical context

- uosc 5.13.0 (pinned). Controls syntax: the comment block in
  `config/script-opts/uosc.conf`. Menus: `script-message-to uosc open-menu`,
  `update-menu`, `close-menu`; `user-data/uosc/menu/type` names the open menu.
- Lua scripts are tested headless by `tests/run_lua_tests.py` with a mocked `mp`.
- The deployer keeps `script-opts/` and `input.conf`; `update` regenerates
  `mpv.conf` unless `--keep-conf`. Both `install` and `update` snapshot the
  whole config before the repair migrations in `_migrate_deployed_configs`.
- Dry-run returns after `display_plan`, so plan entries are the dry-run output.

## Constitution check

- **VI, backup before change**: the migrations run after the run's snapshot;
  tests assert the snapshot holds the old file.
- **VI, `--dry-run`**: the planners add one entry per pending migration,
  computed read-only from the live config; tests assert dry-run writes nothing.
- **VII, idempotent**: a second run changes nothing.

## Design

- `scripts/more_menu.lua`: builds the menu from `track-list`/`edition-list`,
  `demuxer-via-network`, `loop-playlist`, `loop-file`,
  `user-data/player_toolbar/stable-volume` and a shuffle flag. The shuffle flag starts from
  `shuffle=` in `uosc.conf` and flips on each toggle. Observes those
  properties and sends `update-menu` while the menu is open. Message `open`
  toggles the menu.
- `scripts/player-toolbar.lua`: publishes `user-data/player_toolbar/stable-volume`
  (as reverted P4 did).
- `deploy/deployer.py`: `_migrate_uosc_conf` also replaces the `controls=`
  line; `_migrate_mpv_conf` also drops the two spec-006 lines (skipped when
  `mpv.conf` was just regenerated); a new `remove-ui-appearance-conf`
  migration. `deploy/planner.py`: read-only previews of the same three
  changes for the install and update plans.

## Commits

1. `revert(ui)`: drop spec 006 themes (P1 to P5). Done: `66e11bc`.
2. `docs(spec)`: this spec, plan and tasks.
3. `feat(ui)`: More menu script and new controls line.
4. `feat(deployer)`: controls line, mpv.conf lines and ui_appearance.conf on update, with backup and dry-run.
5. `docs`: READMEs, guide, help overlay, changelog.
