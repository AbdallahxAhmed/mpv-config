# Research: Player UI Styles and Themes (spec 006)

All findings were read from the uosc 5.13.0 source (the deployed copy and the
release zip) and from this repo on 2026-11-23. Line numbers refer to uosc 5.13.0.

## R1. Applying options while playing

- **Decision**: the theme script writes the whole `script-opts` property once
  per pick: `get_property_native('script-opts')`, replace the `uosc-*` keys the
  theme owns, then `set_property_native('script-opts', map)`.
- **Rationale**: `main.lua:119` registers `handle_options` as the `read_options`
  update handler. mpv's `mp.options` observes `options/script-opts`, so one
  property write produces one handler call, which re-runs `update_config()` and
  every element's `on_options` (`Controls.lua:473` rebuilds the list). Keys
  written by other sources (for example `display_fps_guard-detected_fps` from
  `mpv.conf`) survive because the map is read, edited and written back. A native
  map also avoids escaping the commas inside `controls`, `color` and `opacity`.
- **Alternatives**: one `change-list script-opts append` per key (about 10
  handler calls per pick and mixed looks in between; rejected, spec M5);
  editing `uosc.conf` (read once at startup, and the deployer keeps user files;
  rejected, spec B3).

## R2. Startup-only keys

- **Decision**: `border_radius=10` and `chapter_ranges` are set in
  `config/mpv.conf.template` with `script-opts-append`, so they are in
  `script-opts` before any script starts. The theme never writes them.
- **Rationale**: `border_radius` becomes `state.radius` only in
  `update_display_dimensions()` (`main.lua:455`), which runs on display changes,
  not on option changes. `chapter_ranges` is parsed into `config` once at load
  (`main.lua:202`). The template already uses `script-opts-append`
  (`display_fps_guard-detected_fps`), and `mpv.conf` is regenerated on update
  unless `--keep-conf` is passed. `-append` takes the value whole, commas included.
- **Value**: `chapter_ranges=openings:7cc4fa64,endings:7cc4fa64,ads:c54e4e80`
  (today's alpha `64` kept; `ads` unchanged).
- **Limit**: `--keep-conf` installs keep today's radius 8 and range colour until
  they regenerate `mpv.conf`. Documented in the CHANGELOG.

## R3. Where the choice lives

- **Decision**: `script-opts/ui_appearance.conf`, shipped in
  `config/script-opts/` with the defaults. The theme script is
  `scripts/ui_appearance.lua`, so `mp.options.read_options(opts, 'ui_appearance')`
  reads the file by itself.
- **Rationale**: `deploy()` copies a shipped `script-opts/*.conf` only when the
  target is missing (`deployer.py:1360-1370`). That one rule gives: fresh install
  gets the defaults, update keeps a changed file, an existing install without the
  file gets the defaults on its first update (FR-015). No deployer code changes.
  A plain uninstall removes `script-opts/` (`deployer.py:3611-3621`), as for
  `anime4k.conf`.
- **Writing**: in place with `io.open(path, 'w')`, as `profile_picker.lua:374-387`
  writes `anime4k.conf` (`os.rename` over an existing file fails on Windows). A torn
  write is read back as invalid and falls back per FR-013. The path comes from
  `mp.find_config_file('script-opts/ui_appearance.conf')`, or
  `mp.command_native({'expand-path', '~~/script-opts/ui_appearance.conf'})` when
  the file is missing.

## R4. The More button and menu

- **Decision**: the `controls` string the theme writes contains
  `command:menu:script-message-to ui_appearance open-more?More` in place of the
  `menu` shorthand. `open-more` builds the menu JSON and sends
  `script-message-to uosc open-menu <json>`. After an Appearance pick it sends
  `update-menu` with the rebuilt JSON, so the open menu marks the new value.
- **Rationale**: `#!` lines replace uosc's default menu and are cached
  (`lib/menus.lua`, `get_menu_items`); script menus support `active`,
  `keep_open`, and are rebuilt on every open (`main.lua:1090-1105`).
  `player-toolbar.lua:650-655` already uses `open-menu`. `input.conf.template`
  binds no key to `uosc/menu`, so the button is the only entry point.
- **"Full uosc menu"** runs `script-binding uosc/menu`; with no `#!` lines,
  uosc shows its default menu (`create_default_menu_items`).

## R5. State shown in the More menu

| Row | Current state read from |
|---|---|
| Loop playlist / loop file | `loop-playlist`, `loop-file` properties |
| Speed values | `speed` property |
| Shuffle | not published by uosc (`state.shuffle`, toggled by `uosc/shuffle`). The theme tracks its own toggles, starting from uosc's `shuffle` option (`no` in `uosc.conf`). No other route toggles it: no key binds `uosc/shuffle`, no style keeps the shuffle button, and uosc's default menu has no shuffle row. |
| Anime4K mode | new `user-data/anime4k/mode`, published by `profile_picker.lua` whenever it applies a mode |
| Stable volume | new `user-data/player_toolbar/stable-volume` (bool), published by `player-toolbar.lua` in `publish()` |
| Video track, editions | listed only when `track-list` has more than one video track, or `edition-list` has more than one entry |
| Stream rows | listed only when `demuxer-via-network` is true (uosc's own `is_stream`, `main.lua:739`) |

## R6. Colours and accent

- uosc has one icon colour, `foreground` (`Button.lua:18-19`); the accent is
  `foreground`. An active button fills with `foreground` and draws its icon in
  `background` (`Button.lua:43-46`); highlighted menu rows use `foreground_text`
  for text (`Menu.lua:1028`), which is `000000` (spec FR-004).
- Contrast is computed with the real opacities: menu surface `opacity.menu`
  0.95 over black and white video, hover row 0.15, active row 0.8, hints and
  muted text 0.5 (`Menu.lua:1656, 1791, 1813`). Worst pairs are recorded in
  `checklists/requirements.md`, Notes 4. All pass FR-023 except the exempt
  hints on highlighted rows.

## R7. Sizes and layout

- A button's click area is its box, `controls_size`; the icon is drawn at about
  0.7 of it. Comfortable 44 (icon about 31), compact 36 (icon about 25).
- Exactly two `space` items centre the middle group (`Controls.lua:381`); focus
  uses `space,prev,play,next,space,…`.
- uosc hides controls from the middle outwards when the row does not fit
  (`Controls.lua:349-357`); each style keeps More and fullscreen at the right end.

## R8. Stream-quality button after a Size change

- `player-toolbar.lua:437` sizes its label from `mp.get_opt('uosc-controls_size')`
  and republishes only on `uosc-version`, `file-loaded` and video size changes.
- **Decision**: `player-toolbar.lua` also observes `options/script-opts` and calls
  `publish_quality(true)` when `uosc-controls_size` changes (FR-008).

## R9. Checking a uosc pin bump (FR-016)

- **Decision**: add `tests/fixtures/uosc-5.13.0/main.lua` from the 5.13.0 release
  zip, pinned by SHA-256 like the `Menu.lua` fixture. A Python check confirms:
  (a) every uosc key the looks write appears in the `defaults` table of
  `main.lua`; (b) `opt.read_options(options, 'uosc', handle_options)` is present;
  (c) the menu opacity constants used by the contrast test (0.8, 0.15, 0.5) are
  still in `Menu.lua`. `tools/check_uosc_release.py --latest` runs the same check
  on the latest release zip (it already reads `Menu.lua` from it).
- The theme's owned key list is exported by the Lua module and also written as
  a plain list in `contracts/ui-appearance.md`; the Python check reads the key
  list from `scripts/modules/looks.lua` with a regex over its `OWNED_KEYS` table.

## R10. Startup order

- mpv starts scripts in parallel. If the theme writes `script-opts` before uosc
  calls `read_options`, uosc reads the theme values directly; if after, the
  handler re-lays out. Controls are hidden until the pointer moves, except when
  idle (`controls_persistency=idle`), and the timeline draws nothing until
  `state.duration > 0`. A re-layout before first display is accepted (US2-3).
  Quickstart step 3 checks for a visible flash when mpv starts idle.
