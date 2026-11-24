# Research: Player UI Styles and Themes (spec 006)

Findings were read from the uosc 5.13.0 source and from this repo on 2026-11-23,
then corrected after EGM Stage 9 on 2026-11-24. `Menu.lua` line numbers refer
to the unmodified fixture `tests/fixtures/uosc-5.13.0/elements/Menu.lua`. The
deployed copy carries the spec 005 patch, and its line numbers differ. The
`main.lua` line numbers refer to upstream 5.13.0 (`main.lua` has no repo patch).

## R1. Applying options while playing

- **Decision**: the theme script writes the whole `script-opts` property once
  per pick or load. It reads the map with `get_property_native('script-opts')`,
  replaces the owned `uosc-*` keys, and writes it back with
  `set_property_native('script-opts', map)`.
- **Rationale**: `main.lua:119` registers `handle_options` as the `read_options`
  update handler. mpv's `mp.options` observes `options/script-opts`, so one
  property write produces one handler call. That call re-runs `update_config()`
  and every element's `on_options` (`Controls.lua:473` rebuilds the control list).
  Keys from other sources survive, because the map is read, edited and written
  back; one example is `display_fps_guard-detected_fps` from `mpv.conf`. A native
  map also avoids escaping the commas inside `controls`, `color` and `opacity`.
- **Status**: read from source only. The reviewer checks it live after P1 (plan).
- **Alternatives rejected**:
  - One `change-list script-opts append` per key: about 10 handler calls and
    mixed looks per pick (spec M5).
  - Editing `uosc.conf`: uosc reads it once at startup, and the deployer keeps
    user files (spec B3).

## R2. Startup-only keys

- **Decision**: `border_radius=10` and `chapter_ranges` are set in
  `config/mpv.conf.template` with `script-opts-append`. The theme never writes them.
- **Rationale**:
  - `border_radius` becomes `state.radius` only in `update_display_dimensions()`
    (`main.lua:455`), which runs on display changes, not on option changes.
  - `chapter_ranges` is parsed into `config` once at load (`main.lua:202`).
  - The template already uses `script-opts-append`, and `-append` takes the value
    whole, commas included.
  - `mpv.conf` is regenerated on update unless `--keep-conf` is given.
- **Value**: `openings:7cc4fa64,endings:7cc4fa64,ads:c54e4e80`. Today's alpha
  `64` is kept, and `ads` is unchanged.
- **Limit**: some installs keep today's radius 8 and range colour until `mpv.conf`
  is regenerated:
  - `--keep-conf` installs;
  - a re-install over an existing `mpv.conf`;
  - a plain `script-opts=` in `mpv.conf.user`.

  The CHANGELOG says so.

## R3. Where the choice lives

- **Decision**: the choice is saved in `script-opts/ui_appearance.conf`, which is
  shipped in `config/script-opts/` with the defaults. The theme script is
  `scripts/ui_appearance.lua`, so `read_options(raw, 'ui_appearance')` reads the
  file.
- **Install**: `deploy()` copies a shipped `script-opts/*.conf` only when the
  target is missing (`deployer.py:1359-1368`).
- **Update**: `mpv-config update` (`cmd_update`) does not call `deploy()`. Its
  `tx.update_assets` replaces only `scripts`, `shaders`, `fonts` and the manifest
  (`transaction.py:26, 456-474`). Seeding therefore needs a migration:
  - `_migrate_ui_appearance_conf` is registered in `_migrate_deployed_configs`,
    which runs on install and update (`deployer.py:1555`).
  - It follows `_migrate_anime4k_conf` (`deployer.py:2829`): it copies the
    shipped file when the target is missing.
- **Uninstall**: a plain uninstall removes `script-opts/` (`deployer.py:3611-3621`),
  as it does for `anime4k.conf`.
- **Writing**: the file is written in place with `io.open(path, 'w')`, as
  `profile_picker.lua:374-390` does (`os.rename` over an existing file fails on
  Windows). The path is found as `profile_picker.lua` `mode_file_path` finds it.

## R4. The More button and menu

- **Decision**: the `controls` string has
  `command:menu:script-message-to ui_appearance open-more?More` in place of the
  `menu` shorthand.
  - `open-more` sends `script-message-to uosc open-menu <json>`.
  - After a pick, the script sends `update-menu`, which uosc ignores unless a
    menu of that `type` is open (`main.lua:1103-1104`).
- **Rationale**:
  - `#!` lines replace uosc's default menu and are cached.
  - Script menus support `active` and `keep_open`, and they are rebuilt on every
    open (`main.lua:1090-1105`).
  - `player-toolbar.lua:650-655` already uses `open-menu`.
  - `input.conf.template` binds no key to `uosc/menu`.
- **"Full uosc menu"** runs `script-binding uosc/menu-blurred`, today's menu
  button command (`Controls.lua:40`). With no `#!` lines, uosc shows its default
  menu.

## R5. State shown in the More menu, and the allowed commands

| Row | State source |
|---|---|
| Loop playlist / loop file | `loop-playlist`, `loop-file` |
| Speed values | `speed` |
| Shuffle | Not published by uosc (`set_state`, `main.lua:568-573`). The row sends `script-message-to ui_appearance toggle-shuffle`, which runs `script-binding uosc/shuffle` and flips the script's flag. The flag starts from the last `shuffle=` line of `~~/script-opts/uosc.conf` (`yes` means on). `read_options` is not used for this, because it would warn on every other uosc key. No other route toggles shuffle. |
| Anime4K mode | `user-data/anime4k/mode`: the saved mode `state.mode` (what `set-mode` changes and the anime profile uses). `profile_picker.lua` publishes it at load (`:560`), in `apply_mode` (`:401`) and in `on_shaders_changed` (`:538`). The menu lists all 8 `CHAINS` modes in the order `off fast A B C A+A B+B C+A`, labelled from `MODE_LABELS`. |
| Stable volume | `user-data/player_toolbar/stable-volume` (bool), set in `publish()` before its early return (`player-toolbar.lua:468-471`) |
| Video track | listed when `track-list` has more than one `video` track that is not `image` or `albumart`, as uosc's `has_many_video` counts them (`main.lua:671-693`) |
| Editions | listed when `edition-list` has more than one entry |
| Stream rows | listed when `demuxer-via-network` is true (`main.lua:739`) |

**Allowed commands (SC-005).** A row's command must be in the union of:

1. a command from a line of `config/input.conf.template`, with a leading `no-osd ` removed;
2. `script-binding uosc/<name>`, for a `<name>` in the facts fixture's `bindings`;
3. `script-message-to <script> <message> [args]`, for a `<message>` registered
   with `register_script_message` in `scripts/player-toolbar.lua`
   (`player_toolbar`), `scripts/profile_picker.lua` (`profile_picker`),
   `scripts/help_overlay.lua` (`help_overlay`) or `scripts/ui_appearance.lua`
   (`ui_appearance`);
4. these extras, which match today's buttons rather than a key:
   `cycle-values loop-playlist inf no`, `cycle-values loop-file inf no`,
   `set speed <number>`, `script-binding ytdl_sub_menu/open`,
   `script-binding smart_paste/paste-to-open`.

## R6. Colours, accent and the contrast model

- **Accent**: uosc has one icon colour, `foreground` (`Button.lua:18-19`), so the
  accent is `foreground`.
- **Active button**: it fills its box with `foreground` and draws its icon in
  `background` (`Button.lua:43-46`).
- **Highlighted menu rows**: their text uses `foreground_text`
  (`Menu.lua:1478`), which is `000000` (spec FR-004).
- **Contrast model (SC-004)**, computed in `tests/lua/test_ui_appearance.lua`
  from the palette in `looks.lua`:
  - Blending: straight alpha over sRGB-encoded 8-bit channels, as libass blends:
    `out = a*top + (1-a)*under`.
  - Luminance: WCAG 2.x relative luminance and ratio.
  - Menu surface: Background at 0.95 over `#000000`, and again over `#FFFFFF`.
    Both surfaces are checked.
  - Pairs, for all 15 Background × Accent combinations:

    | Pair | Threshold |
    |---|---|
    | Title (`F2F2F3`) on the surface | 4.5 |
    | Hint or muted (title at 0.5 over the surface) | 3.0 |
    | Title on the hover row (accent at 0.15 over the surface) | 4.5 |
    | Hint on the hover row | 3.0 |
    | `000000` on the active row (accent at 0.8 over the surface) | 4.5 |
    | Accent icon on the surface | 4.5 |
    | Accent icon on a bar box (Background at 0.92 over black, and over white) | 4.5 |
    | Background-coloured icon on the accent | 4.5 |

  - Exempt: a hint on the active row.
  - The expected worst values are in `checklists/requirements.md`, Notes 4.
- **Opacity constants**: the menu draws the active row at 0.8, the hover row at
  0.15 (`Menu.lua:1499`), hints at 0.5 (`:1633`) and muted text at 0.5 (`:1655`).

## R7. Sizes and layout

- A button's click area is its box, `controls_size`, and the icon is drawn at
  about 0.7 of it:
  - comfortable: 44 (icon about 31);
  - compact: 36 (icon about 25).
- Exactly two `space` items centre the middle group (`Controls.lua:381`).
- uosc hides controls from the middle outwards (`Controls.lua:349-373`), so every
  style keeps More and fullscreen at the right end.

## R8. Stream-quality button after a Size change

- `player-toolbar.lua:437` sizes its label from `mp.get_opt('uosc-controls_size')`.
  It republishes only on `uosc-version`, `file-loaded` and video size changes.
- **Decision**: also observe `options/script-opts`, and call `publish_quality(true)`
  when the `uosc-controls_size` value changes.

## R9. Pin-bump guard without a copy of `main.lua`

- **Maintainer decision (2026-11-24)**: commit no copy of uosc `main.lua`, not
  even a redacted one. Upstream line 177 holds `open_subtitles_api_key`.
- **Facts fixture**: `tests/fixtures/uosc-5.13.0/uosc-options.json`, extracted
  from the 5.13.0 release zip by `tools/check_uosc_release.py --tag 5.13.0 --write-options`.
  It holds the option names and defaults, the colour and opacity sub-keys, the
  handler flag, the bindings, and the SHA-256 of upstream `main.lua`. The shape
  is in data-model.md.
- **Weekly**:
  - `--latest` regenerates the facts from the latest release and checks them.
  - `--tag 5.13.0 --compare-options` regenerates the pinned facts and compares
    them with the committed file.
- **Menu constants**, checked in the committed `Menu.lua` fixture and in each
  release. Each must occur exactly once unless a count is given:
  - `(item.active and 0.8 or 0) + (is_selected and 0.15 or 0)`
  - `opacity = 0.5 * menu_opacity,`
  - `opacity = menu_opacity * (item.muted and 0.5 or 1),`
  - `item.active and fgt or bgt` (at least once; 3 times in 5.13.0)

## R10. Startup order

- mpv starts scripts in parallel:
  - If the theme writes `script-opts` before uosc calls `read_options`, uosc
    reads the theme values directly.
  - If it writes after, the handler re-lays out the controls.
- Controls are hidden until the pointer moves, except when idle
  (`controls_persistency=idle`).
- The timeline draws nothing until `state.duration > 0`.
- A re-layout before first display is accepted (US2-3). Quickstart step 3 checks
  for a visible flash when mpv starts idle.
