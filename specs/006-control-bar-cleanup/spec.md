# Feature Specification: Control bar cleanup

**Feature Branch**: `006-control-bar-cleanup` (directory name only; the maintainer commits to `main`)
**Created**: 2026-11-25
**Status**: Ready for implementation
**Input**: Maintainer, 2026-11-25: "Drop themes completely. Go back to today's uosc look exactly. Only clean up the control bar." This replaces the earlier spec 006, *Player UI styles and themes*.

## Dropped: player UI styles and themes

The theme work (styles calm/bar/focus, More > Appearance, accents,
backgrounds, sizes, `script-opts/ui_appearance.conf`, the `mpv.conf.template`
`script-opts-append` lines, `scripts/modules/looks.lua`, the uosc options
fixture) is **dropped**. It was specified in `5a35c4d`..`6c56baf`,
implemented in `a581786`..`a60b5a8` and reverted in `66e11bc`. Git history
keeps the old spec, plan, research, data model, contract and quickstart.

## What changes

The look stays what `script-opts/uosc.conf` already says: colors, opacity,
timeline, sizes, radius and chapter-range colors are unchanged. Only the
`controls=` line and a new More menu change. No keyboard shortcut changes.

### The control bar

| Group | Controls |
|---|---|
| Left | prev, play-pause, next |
| Center | speed (between two `space` elements, as today) |
| Right | subtitles (the existing CC command), audio-tracks button, `<has_many_video>` video, `<stream>` stream-quality button, items, More, fullscreen |

```
controls=prev,play-pause,next,space,<video,audio>speed,space,command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles and captions,button:audio-tracks,<has_many_video>video,<stream>button:stream-quality,items,command:menu:script-message-to more_menu open?More,fullscreen
```

Speed sits midway between the two groups, so with three buttons on the left
and seven on the right it is a little left of the window's center.

### The More menu

The menu button opens a menu built by `scripts/more_menu.lua`. It holds the
controls that leave the bar, plus two entries kept from before:

| Entry | Shown | Runs | Marked when |
|---|---|---|---|
| Paste link (hint `Ctrl+V`) | always | `script-binding smart_paste/paste-to-open` | — |
| Download video | streams only | `script-message-to player_toolbar download-video` | — |
| Stable volume | always | `script-message-to player_toolbar toggle-stable-volume` | stable volume is on |
| Shuffle | always | `script-binding uosc/shuffle` | shuffle is on |
| Loop playlist | always | `cycle-values loop-playlist inf no` | `loop-playlist` is not `no` |
| Loop file | always | `cycle-values loop-file inf no` | `loop-file` is not `no` |
| Editions | more than one edition | `script-binding uosc/editions` | — |
| Full uosc menu | always | `script-binding uosc/menu-blurred` | — |
| All shortcuts (hint `F9`) | always | `script-message-to help_overlay help` | — |

The toggles keep the menu open, and their marks update while it is open.
Pressing the More button while the menu is open closes it.

Right-click does not open uosc's menu: `config/input.conf.template` binds
`MBTN_RIGHT` to `cycle pause` (checked 2026-11-25). "Full uosc menu" is the
way to reach it from the mouse.

The bar's download button showed download progress as a badge; from the
More menu, a download reports through its existing OSD messages only.

## Requirements

- **FR-001**: `config/script-opts/uosc.conf` ships the `controls=` line above;
  no other key in it changes.
- **FR-002**: `scripts/more_menu.lua` builds the More menu above. Script
  messages go to `more_menu`; the menu type is `more_menu`.
- **FR-003**: On `install` over an existing config and on `update`, the
  deployer replaces the `controls=` line in `script-opts/uosc.conf` with the
  shipped one. Every other line stays byte-identical. A file already on the
  new line is not rewritten. A hand-edited `controls=` line is replaced too.
- **FR-004**: When `mpv.conf` is kept (`--keep-conf`, or install over an
  existing config), the deployer removes exactly these two lines if present
  and nothing else:
  `script-opts-append        = uosc-border_radius=10` and
  `script-opts-append        = uosc-chapter_ranges=openings:7cc4fa64,endings:7cc4fa64,ads:c54e4e80`.
- **FR-005**: The deployer deletes a leftover `script-opts/ui_appearance.conf`.
- **FR-006** (constitution VI): FR-003 to FR-005 change a user file only after
  the config backup for that run exists, and the backup holds the old file.
- **FR-007** (constitution VI): `--dry-run` for `install` and `update` lists
  each FR-003 to FR-005 change that would be made to this config, and writes
  nothing.
- **FR-008**: No keyboard shortcut changes.

## Success criteria

- **SC-001**: Both test suites pass: `PYTHONPATH=src python -m unittest discover -s tests`
  (project venv) and `python tests/run_lua_tests.py`.
- **SC-002**: Playback is not affected. Two runs on KDE Wayland from
  `--start=5:00` (after the SmartSkip seek): run A with no UI use, run B
  using the bar and the More menu. Both end with `delayed=0` and `drop=0`.
