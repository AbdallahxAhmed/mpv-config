---

description: "Task list for spec 006: player UI styles and themes"
---

# Tasks: Player UI Styles and Themes

**Input**: Design documents from `specs/006-player-ui-themes/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md, contracts/ui-appearance.md
**Generated**: 2026-11-24, after EGM Stage 9 round 1 (`.egm/006/`, fixes auto-accepted; facts fixture instead of a `main.lua` copy)

**Tests**: requested (spec SC-004, SC-005, SC-007, SC-008, FR-016). Within each phase,
the test tasks come first and must fail before their implementation task lands.

**Phases = commits.** Each phase below is one commit on `main`. That commit is
made by the reviewer only after both suites pass and the diff matches the plan.
Do not push.

**Write allowlist**: plan "Components" table. Nothing else changes.

**Standing rules**: `pathlib` for new and changed Python; never `shell=True`; no
secrets or personal paths; no copy of uosc `main.lua`; no uosc patch; Python
tests with the project venv and `PYTHONPATH=src`; Lua suites with
`python tests/run_lua_tests.py`; every test headless.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, and no dependency on an unfinished task)
- **[US1]** styles · **[US2]** switching · **[US3]** More menu

---

## Phase 1 (commit P1): Looks: the three styles, applied at load (US1, MVP)

**Goal**: The default look (calm, dark, amber, comfortable) applies at load on
every install, and the More button opens a minimal menu.

**Independent test**: `tests/lua/test_ui_appearance.lua` and `tests/test_ui_appearance.py`
pass. Then the reviewer's live check in a nested KWin session.

### Tests first

- [ ] T001 [P] [US1] Write `tests/lua/test_ui_appearance.lua` with a harness modelled on `tests/lua/test_profile_picker.lua` (it stubs `mp`, `mp.options`, `mp.msg`, `mp.utils`). Cover:
  - `looks.uosc_options` for all 30 looks: only `OWNED_KEYS` are produced, each `color` value has the 10 sub-keys in `OWNED_COLOR_KEYS` order, and each `opacity` value has the 19 sub-keys in `OWNED_OPACITY_KEYS` order;
  - for the default look, the output is byte-equal to the literal block in data-model.md "Literal values for the default look";
  - the focus `controls` string is `space,prev,PLAY,next,space,items,MORE,fullscreen`, and bar differs from calm only in `opacity.controls=0.92` and `controls_persistency=idle,windowed`;
  - `merge_script_opts` keeps a foreign entry (`display_fps_guard-detected_fps=144`) and replaces every owned key;
  - `normalize`: empty fields, invalid values and all-empty input give the defaults, with `fallbacks` in `DEFAULTS` order;
  - `serialize(DEFAULTS)` is byte-equal to `config/script-opts/ui_appearance.conf`.
- [ ] T002 [US1] In the same file, add script-level tests that load `scripts/ui_appearance.lua`:
  - load makes exactly one `set_property_native('script-opts', …)` call;
  - load with a missing file logs exactly one warning, naming `style, background, accent, size`;
  - load with `style=huge` logs one warning naming `style`;
  - load with no uosc present raises no error;
  - `open-more` sends one `script-message-to uosc open-menu` whose JSON has `type = ui_appearance_more`, title `More`, and exactly the P1 rows from data-model.md (Paste link with hint `Ctrl+V`, Stable volume, Full uosc menu, All shortcuts with hint `F9`).
- [ ] T003 [P] [US1] In the same file, add the contrast test from research R6. Use `looks.blend` and `looks.contrast`, cover all 15 Background × Accent pairs and every pair in the R6 table with its threshold, and treat a hint on the active row as exempt. On failure, print the pair, the ratio and the threshold.
- [ ] T004 [P] [US1] Write `tests/test_ui_appearance.py`:
  - deploy with `DeployerTestCase` (`tests/test_deploy_uosc_reorder_patch.py`): a fresh install has `script-opts/ui_appearance.conf` equal to the shipped file;
  - `_migrate_deployed_configs` on a config dir without the file seeds it, and on a dir with a changed file leaves it byte-identical (SC-008);
  - `config/mpv.conf.template` has both `script-opts-append` lines from plan "Startup-only keys", directly after the `osd-fonts-dir` line.

### Implementation

- [ ] T005 [US1] Create `scripts/modules/looks.lua` per contracts/ui-appearance.md and data-model.md: `DEFAULTS`, `CHOICES`, the four literal key tables, the palette, the style and size tables, `normalize`, `uosc_options`, `merge_script_opts`, `serialize`, `blend`, `contrast`, and `more_menu` returning the P1 rows. Pure functions only, no `mp` calls.
- [ ] T006 [US1] Create `config/script-opts/ui_appearance.conf` with the exact text in data-model.md "Look". LF line endings.
- [ ] T007 [US1] Create `scripts/ui_appearance.lua`:
  - load `looks.lua` the way `player-toolbar.lua` loads `stream_policy.lua`;
  - load and apply per plan "Load and apply" steps 1 to 3;
  - register `open-more` per plan "More menu";
  - the shuffle flag read (step 4) is added in T026.
- [ ] T008 [P] [US1] Edit `config/mpv.conf.template`: add the two `script-opts-append` lines directly after `osd-fonts-dir`.
- [ ] T009 [P] [US1] Edit `deploy/deployer.py`: add `_migrate_ui_appearance_conf(conf_path, repo_config_dir, audit_log=None)` per plan "Seeding migration", using `pathlib`, `shutil.copyfile` and an audit `create` record. Register it in `_migrate_deployed_configs` as `seed-ui-appearance-conf`.
- [ ] T010 [US1] Run both suites. Fix only the files touched in this phase.

**Checkpoint (reviewer)**:
- Review the diff against the plan and the allowlist, then commit P1.
- Live check in a nested KWin session: mpv with uosc and the theme script shows calm. Then set `script-opts` to the focus look's `uosc-*` entries through mpv's IPC socket: the controls re-lay out while playing.
- Stop before Phase 2 if the live check fails.

---

## Phase 2 (commit P2): Pin-bump guard (FR-016)

**Goal**: A uosc release that drops an owned option, a colour or opacity sub-key,
the runtime handler, a More binding or a menu constant fails the check offline
and weekly. No copy of `main.lua` is committed.

**Independent test**: `tests/test_ui_appearance.py` guard cases and
`tests/test_uosc_release_check.py` pass.

### Tests first

- [ ] T011 [P] Add guard tests to `tests/test_ui_appearance.py`:
  - `read_looks_keys` returns the four tables from `scripts/modules/looks.lua`;
  - `check_options` on the committed fixture returns no problems;
  - a fixture copy with `progress_size` removed, built in the test, returns exactly `uosc 5.13.0: option progress_size missing`;
  - the same for a removed `color.heatmap`, a removed binding `menu-blurred`, and `runtime_handler: false`;
  - `check_menu_constants` on `tests/fixtures/uosc-5.13.0/elements/Menu.lua` returns no problems, and with one constant removed it names that constant;
  - `extract_uosc_facts` on a synthetic `main.lua` snippet written in the test returns the expected dict;
  - a snippet without `defaults = {` raises `CheckError`.
- [ ] T012 [P] Update `tests/test_uosc_release_check.py`:
  - `GOOD_ZIP` carries a synthetic `scripts/uosc/main.lua` with a `defaults` block holding every owned key, both `config_defaults` blocks, the handler line, and `bind_command` lines for `MORE_UOSC_BINDINGS`;
  - add the new success line to every exact-output assertion;
  - new cases: a zip whose `main.lua` lacks one owned key (exit 1, line names it), lacks the handler (exit 1), and a zip with no `main.lua` (exit 2, `release zip has no scripts/uosc/main.lua`);
  - `--write-options` writes sorted JSON, and `--compare-options` exits 1 on one changed default and names the key.

### Implementation

- [ ] T013 Extend `tools/check_uosc_release.py` per plan "Pin-bump guard":
  - `_members_from_zip`, `extract_uosc_facts`, `read_looks_keys`, `check_options`, `check_menu_constants`;
  - the `run()` and `check_dir()` flow and messages;
  - the `--tag`, `--write-options` and `--compare-options` flags;
  - update the module docstring.
- [ ] T014 Generate `tests/fixtures/uosc-5.13.0/uosc-options.json` with `python -m tools.check_uosc_release --tag 5.13.0 --write-options tests/fixtures/uosc-5.13.0/uosc-options.json`. Check that `main_lua_sha256` matches the hash of `scripts/uosc/main.lua` in the 5.13.0 `uosc.zip`.
- [ ] T015 [P] Edit `tests/fixtures/uosc-5.13.0/README.md`: add a row for `uosc-options.json` (source, generator command, the SHA-256 of upstream `main.lua`), and a line saying no copy of `main.lua` is kept and why.
- [ ] T016 [P] Edit `.github/workflows/uosc-release-check.yml`:
  - rename the step to "Check latest uosc release (reorder anchors, theme options)";
  - add a step that runs `python -m tools.check_uosc_release --tag 5.13.0 --compare-options tests/fixtures/uosc-5.13.0/uosc-options.json --download-timeout 120`.
- [ ] T017 [P] Edit `specs/005-playlist-drag-reorder/contracts/uosc-release-check.md`: add the new checks, problem lines, exit codes and flags.
- [ ] T018 Run both suites.

**Checkpoint (reviewer)**: run T014's command again and confirm the output is byte-identical. Then commit P2.

---

## Phase 3 (commit P3): Change the look from inside mpv (US2)

**Goal**: More > Appearance switches style, background, accent and size while
playing, saves the choice, and the stream-quality label follows Size.

**Independent test**: the US2 cases in `tests/lua/test_ui_appearance.lua` and
the republish case in `tests/lua/test_player_toolbar.lua` pass.

### Tests first

- [ ] T019 [P] [US2] Add pick tests to `tests/lua/test_ui_appearance.lua`:
  - `set style bar` writes the file (exact `serialize` text) before its one `script-opts` write;
  - three quick picks give three writes, and the last one wins;
  - with `io.open` stubbed to return `nil, 'Permission denied'`, `mp.osd_message('Appearance not saved: Permission denied', 3)` shows and the look still applies;
  - `set style huge` and `set colour amber` write and apply nothing;
  - after each pick, one `update-menu` with type `ui_appearance_more` is sent;
  - `open-more` now starts with Appearance (Style, Background, Accent, Size, each submenu marking the current value, value rows `keep_open`), followed by the P1 rows.
- [ ] T020 [P] [US2] Add to `tests/lua/test_player_toolbar.lua`: a change of the `uosc-controls_size` entry in `options/script-opts` calls the quality republish once; a change of any other entry does not.

### Implementation

- [ ] T021 [US2] In `scripts/modules/looks.lua`, add the Appearance submenu to `more_menu`. In `scripts/ui_appearance.lua`, register `set` per plan "A pick" steps 1 to 4, with the path lookup modelled on `profile_picker.lua` `mode_file_path`.
- [ ] T022 [P] [US2] In `scripts/player-toolbar.lua`, observe `options/script-opts`, remember the last `uosc-controls_size` value, and call `publish_quality(true)` only when it changes (research R8).
- [ ] T023 [US2] Run both suites.

**Checkpoint (reviewer)**: diff review, then commit P3.

---

## Phase 4 (commit P4): The grouped More menu (US3)

**Goal**: The full More menu from data-model.md, with the current state marked
and the conditional rows.

**Independent test**: the US3 cases in `tests/lua/test_ui_appearance.lua`,
`test_profile_picker.lua` and `test_player_toolbar.lua` pass.

### Tests first

- [ ] T024 [P] [US3] Add More-menu tests to `tests/lua/test_ui_appearance.lua`:
  - **Allowed commands (SC-005)**: every row command is in the allowed set of research R5. Build the set inside the test from `config/input.conf.template` (with `no-osd ` stripped), the fixture `uosc-options.json` `bindings`, the `register_script_message` names in the four scripts, and the R5 extras.
  - **Conditional rows (FR-019)**:
    - a local file has no Stream quality and no Download video, and a stream has both;
    - `track-list` with one video track plus one album-art track has no Video track row, and two real video tracks have one;
    - one edition has no Editions row, and two editions have one.
  - **Marks**: active rows have no `hint`; Loop, Speed, Anime4K and Stable volume rows are marked from `state`.
  - **Shuffle**:
    - `toggle-shuffle` runs `script-binding uosc/shuffle`, flips the mark and sends `update-menu`;
    - the flag starts as true when `uosc.conf` ends with `shuffle=yes`, and false when there is no file.
- [ ] T025 [P] [US3] Add tests:
  - in `tests/lua/test_profile_picker.lua`: `user-data/anime4k/mode` equals the saved mode after load, after `set-mode B`, and after a `glsl-shaders` change that `on_shaders_changed` maps to a mode;
  - in `tests/lua/test_player_toolbar.lua`: `user-data/player_toolbar/stable-volume` is true or false after `publish()` with and without the filter.

### Implementation

- [ ] T026 [US3] Complete `more_menu` in `scripts/modules/looks.lua` per the data-model.md table:
  - labels, the 8 Anime4K modes in order `off fast A B C A+A B+B C+A` with `MODE_LABELS` hints, speeds `0.5×` to `2×`, and `keep_open` where listed;
  - Full uosc menu runs `script-binding uosc/menu-blurred`.

  In `scripts/ui_appearance.lua`:
  - read `state` per the contract;
  - register `toggle-shuffle`;
  - read the initial shuffle flag (plan "Load and apply" step 4).
- [ ] T027 [P] [US3] In `scripts/profile_picker.lua`, set `user-data/anime4k/mode` to `state.mode` at load (after `read_mode`), in `apply_mode` and in `on_shaders_changed`.
- [ ] T028 [P] [US3] In `scripts/player-toolbar.lua`, set `user-data/player_toolbar/stable-volume` in `publish()`, before its early return.
- [ ] T029 [US3] Run both suites.

**Checkpoint (reviewer)**: diff review, then commit P4.

---

## Phase 5 (commit P5): Documentation

- [ ] T030 [P] In `scripts/help_overlay.lua`, change the MOUSE row `{ "menu button", … }` to `{ "More button", "appearance, playback, open, all menus" }`. Update `tests/lua/test_help_overlay.lua` if it asserts the old text.
- [ ] T031 [P] Update `README.md` and `README.ar.md`: the toolbar line becomes the three styles and More > Appearance. Hand edits to owned uosc keys have no effect; list the keys. Keep `tests/test_readme_toc.py` green.
- [ ] T032 [P] Update `docs/YOUTUBE_GUI.md`: the toolbar groups for calm, bar and focus, the new More menu, and the sizes 44 and 36.
- [ ] T033 [P] Add a `CHANGELOG.md` entry covering:
  - the new looks;
  - existing installs move to calm, dark, amber, comfortable;
  - `--keep-conf`, a re-install over an existing `mpv.conf`, or a plain `script-opts=` in `mpv.conf.user` keeps radius 8 and the old range colour until `mpv.conf` is regenerated;
  - hand edits to owned keys no longer apply.
- [ ] T034 [P] Update the `AGENTS.md` status section for spec 006.
- [ ] T035 Run both suites, including `tests/test_repo_hygiene.py`.

**Checkpoint (reviewer)**: diff review, then commit P5. Stop: hand the maintainer
the quickstart steps for KDE Wayland and Windows.

---

## Dependencies

- P1 blocks everything: `looks.lua` and the theme script exist only after P1.
- P2 needs P1 (`read_looks_keys` parses `looks.lua`).
- P3 needs P1. P4 needs P3, because the Appearance rows go into the full menu.
- P5 needs P4.
- Within a phase, the test tasks come before the implementation tasks. `[P]` tasks
  touch different files.

## Parallel examples

- P1: T001, T003 and T004 together; then T008 and T009 alongside T005 to T007.
- P2: T011 and T012 together; T015, T016 and T017 after T013 and T014.
- P4: T024 and T025 together; T027 and T028 alongside T026.

## Implementation strategy

- The MVP is P1: every install shows calm, nothing becomes unreachable, and the
  More menu keeps Paste link, Stable volume, the full uosc menu and the shortcuts.
- P2 makes the pin safe before more code depends on uosc internals.
- P3 and P4 add the stories in priority order.
- Each phase is delegated to agy on its own. The reviewer runs both suites,
  checks the diff against the plan and the repo rules, and commits only what
  passes.
