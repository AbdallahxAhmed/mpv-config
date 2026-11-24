# Data Model: Player UI Styles and Themes (spec 006)

## Look (saved choice)

The look is saved in `script-opts/ui_appearance.conf`. The shipped file and
`looks.serialize(looks.DEFAULTS)` are byte-identical (LF line endings):

```
# Player look, chosen in More > Appearance. Values:
# style=calm|bar|focus background=dark|black|slate accent=amber|teal|violet|rose|white size=comfortable|compact
style=calm
background=dark
accent=amber
size=comfortable
```

| Field | Values, in menu order | Default |
|---|---|---|
| `style` | `calm` `bar` `focus` | `calm` |
| `background` | `dark` `black` `slate` | `dark` |
| `accent` | `amber` `teal` `violet` `rose` `white` | `amber` |
| `size` | `comfortable` `compact` | `comfortable` |

**Validation** (FR-013):
- The file is read with empty-string defaults.
- An empty or out-of-list value falls back to that field's default, for that
  field alone.
- All fallbacks of one start go into one warning.
- Unknown keys are not shipped. mp.options warns about them itself.
- The file is rewritten whole on every pick.

## Palette

| Name | Hex (lower-case in uosc strings) | uosc sub-key |
|---|---|---|
| Accent amber / teal / violet / rose / white | `f2b544` / `5eead4` / `a78bfa` / `fb7185` / `f2f2f3` | `color.foreground` |
| Text on accent | `000000` | `color.foreground_text` |
| Background dark / black / slate | `0e0f12` / `000000` / `1c2430` | `color.background` |
| Text | `f2f2f3` | `color.background_text` |
| Window border (uosc default) | `000000` | `color.window_border` |
| Curtain (shipped today) | `06080d` | `color.curtain` |
| Success | `34d399` | `color.success` |
| Error | `f87171` | `color.error` |
| Search match (shipped today) | `38bdf8` | `color.match` |
| Heatmap (uosc default, kept on purpose) | `00adee` | `color.heatmap` |
| Openings / endings ranges | `7cc4fa` alpha `64` | `chapter_ranges`, in mpv.conf (research R2) |

## Owned keys (FR-011), in the literal tables of `looks.lua`

- `OWNED_KEYS` (top-level `uosc-<key>` entries, written in this order):
  `controls`, `color`, `opacity`, `controls_size`, `controls_spacing`,
  `controls_margin`, `controls_persistency`, `timeline_size`, `progress`,
  `progress_size`, `menu_item_height`.
- `OWNED_COLOR_KEYS` (sub-key order inside `color`): `foreground`,
  `foreground_text`, `background`, `background_text`, `window_border`,
  `curtain`, `success`, `error`, `match`, `heatmap`.
- `OWNED_OPACITY_KEYS` (sub-key order inside `opacity`): `timeline`,
  `position`, `chapters`, `slider`, `slider_gauge`, `controls`, `speed`,
  `menu`, `submenu`, `border`, `title`, `tooltip`, `thumbnail`, `curtain`,
  `idle_indicator`, `audio_indicator`, `buffering_indicator`,
  `playlist_position`, `heatmap`.
- `MORE_UOSC_BINDINGS`: `shuffle`, `video`, `editions`, `open-file`, `menu-blurred`.
- Never written at runtime:
  - `border_radius` and `chapter_ranges` (set in mpv.conf);
  - `proximity_out`, `destination_time` and `top_bar_controls`.

## Values per style and size

Shorthands used in `controls`:
- `PLAY` = `cycle:pause_circle:pause:no=pause_circle/yes=play_circle?Play/pause`
- `SUBS` = `command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles`
- `COND` = `<has_many_video>video,<has_many_edition>editions,<stream>button:stream-quality,<stream>button:download-video`
- `MORE` = `command:menu:script-message-to ui_appearance open-more?More`

| Key | calm | bar | focus |
|---|---|---|---|
| `controls` | `prev,PLAY,next,space,<video,audio>speed,SUBS,button:audio-tracks,COND,items,MORE,fullscreen` | same as calm | `space,prev,PLAY,next,space,items,MORE,fullscreen` |
| `opacity.controls` | `0` | `0.93` | `0` |
| `controls_persistency` | `idle` | `idle,windowed` | `idle` |
| `progress` | `always` | `always` | `always` |
| `progress_size` | `3` | `3` | `3` |
| `menu_item_height` | `40` | `40` | `40` |

| Key | comfortable | compact |
|---|---|---|
| `controls_size` | `44` | `36` |
| `controls_spacing` | `4` | `2` |
| `controls_margin` | `8` | `6` |
| `timeline_size` | `40` | `32` |

**Opacity**: today's shipped values, plus `heatmap`, with `controls` from the style.

## Literal values for the default look (calm, dark, amber, comfortable)

```
uosc-controls=prev,cycle:pause_circle:pause:no=pause_circle/yes=play_circle?Play/pause,next,space,<video,audio>speed,command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles,button:audio-tracks,<has_many_video>video,<has_many_edition>editions,<stream>button:stream-quality,<stream>button:download-video,items,command:menu:script-message-to ui_appearance open-more?More,fullscreen
uosc-color=foreground=f2b544,foreground_text=000000,background=0e0f12,background_text=f2f2f3,window_border=000000,curtain=06080d,success=34d399,error=f87171,match=38bdf8,heatmap=00adee
uosc-opacity=timeline=0.95,position=1,chapters=0.8,slider=0.95,slider_gauge=1,controls=0,speed=0.7,menu=0.95,submenu=0.5,border=1,title=1,tooltip=1,thumbnail=1,curtain=0.85,idle_indicator=0.85,audio_indicator=0.6,buffering_indicator=0.4,playlist_position=0.8,heatmap=0.4
uosc-controls_size=44
uosc-controls_spacing=4
uosc-controls_margin=8
uosc-controls_persistency=idle
uosc-timeline_size=40
uosc-progress=always
uosc-progress_size=3
uosc-menu_item_height=40
```

## Facts fixture: `tests/fixtures/uosc-5.13.0/uosc-options.json`

```json
{
  "bindings": ["audio", "audio-device", "chapters", "..."],
  "color": {"background": "000000", "...": "..."},
  "main_lua_sha256": "<sha256 of upstream scripts/uosc/main.lua in uosc.zip 5.13.0>",
  "opacity": {"audio_indicator": "0.5", "...": "..."},
  "options": {"autohide": "false", "controls": "'menu,gap,...'", "...": "..."},
  "runtime_handler": true,
  "uosc_version": "5.13.0"
}
```

- **`options`**: each field of the `defaults = {` block, mapped to its default
  exactly as written in the source (trailing comma removed).
- **`color`**: each `config_defaults.color` sub-key, mapped to the hex inside
  `serialize_rgba('…')`.
- **`opacity`**: each `config_defaults.opacity` sub-key, mapped to its number as
  written.
- **`bindings`**: the sorted `bind_command('<name>'` names.
- **Serialization**: `json.dumps(…, indent=2, sort_keys=True)` plus a newline.

## More menu (`type = 'ui_appearance_more'`, title `More`)

| Row (label) | Command | Listed when | Marked when |
|---|---|---|---|
| Appearance > Style / Background / Accent / Size > value (label = the stored value) | `script-message-to ui_appearance set <field> <value>`, `keep_open` | always (P3+) | value is current |
| Subtitles | `script-binding ytdl_sub_menu/open` | always | — |
| Audio | `script-message-to player_toolbar open-audio-menu` | always | — |
| Stream quality | `script-message-to player_toolbar open-quality-menu` | stream | — |
| Playback > Shuffle | `script-message-to ui_appearance toggle-shuffle`, `keep_open` | always | flag on |
| Playback > Loop playlist | `cycle-values loop-playlist inf no`, `keep_open` | always | `loop-playlist` ≠ `no` |
| Playback > Loop file | `cycle-values loop-file inf no`, `keep_open` | always | `loop-file` ≠ `no` |
| Playback > Speed > `0.5×` `0.75×` `1×` `1.25×` `1.5×` `1.75×` `2×` | `set speed <v>` | always | `speed` equals the value |
| Picture & sound > Anime4K mode > `off` `fast` `A` `B` `C` `A+A` `B+B` `C+A` (hint `MODE_LABELS` text when not active) | `script-message-to profile_picker set-mode <mode>` | always | `user-data/anime4k/mode` equals the mode |
| Picture & sound > Stable volume | `script-message-to player_toolbar toggle-stable-volume`, `keep_open` | always | `user-data/player_toolbar/stable-volume` |
| Picture & sound > Video track | `script-binding uosc/video` | more than one real video track | — |
| Picture & sound > Editions | `script-binding uosc/editions` | more than one edition | — |
| Open > Paste link (hint `Ctrl+V`) | `script-binding smart_paste/paste-to-open` | always | — |
| Open > Open file | `script-binding uosc/open-file` | always | — |
| Open > Download video | `script-message-to player_toolbar download-video` | stream | — |
| Full uosc menu | `script-binding uosc/menu-blurred` | always | — |
| All shortcuts (hint `F9`) | `script-message-to help_overlay help` | always | — |

The P1 menu has four top-level rows: Paste link (hint `Ctrl+V`), Stable volume,
Full uosc menu and All shortcuts. P3 adds Appearance at the top. P4 builds the
full table. A row that is marked active carries no hint.
