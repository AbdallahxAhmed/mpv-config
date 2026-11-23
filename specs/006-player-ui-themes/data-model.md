# Data Model: Player UI Styles and Themes (spec 006)

## Look (saved choice)

File `script-opts/ui_appearance.conf`, read with `mp.options.read_options`:

```
style=calm
background=dark
accent=amber
size=comfortable
```

| Field | Values | Default |
|---|---|---|
| `style` | `calm` `bar` `focus` | `calm` |
| `background` | `dark` `black` `slate` | `dark` |
| `accent` | `amber` `teal` `violet` `rose` `white` | `amber` |
| `size` | `comfortable` `compact` | `comfortable` |

Validation: a value outside its list falls back to the default for that field
alone; all fallbacks of one start are logged in one warning (FR-013). Unknown
keys are ignored. The file is rewritten whole on every pick, comments included.

## Palette (fixed and chosen colours)

| Name | Hex | uosc key |
|---|---|---|
| Background dark / black / slate | `0E0F12` / `000000` / `1C2430` | `color.background` |
| Accent amber / teal / violet / rose / white | `F2B544` / `5EEAD4` / `A78BFA` / `FB7185` / `F2F2F3` | `color.foreground` |
| Text on accent | `000000` | `color.foreground_text` |
| Text | `F2F2F3` | `color.background_text` |
| Success | `34D399` | `color.success` |
| Error | `F87171` | `color.error` |
| Curtain (shipped today) | `06080D` | `color.curtain` |
| Search match (shipped today) | `38BDF8` | `color.match` |
| Window border (uosc default) | `000000` | `color.window_border` |
| Openings / endings ranges | `7CC4FA` alpha `64` | `chapter_ranges` (mpv.conf, R2) |

`color` is written as all nine sub-keys, every time.

## Opacity (written whole)

Today's shipped string, with `controls` set by the style:

```
timeline=0.95,position=1,chapters=0.8,slider=0.95,slider_gauge=1,controls=<0|0.92>,
speed=0.7,menu=0.95,submenu=0.5,border=1,title=1,tooltip=1,thumbnail=1,curtain=0.85,
idle_indicator=0.85,audio_indicator=0.6,buffering_indicator=0.4,playlist_position=0.8
```

## Style definition

`MORE` = `command:menu:script-message-to ui_appearance open-more?More`
`PLAY` = `cycle:pause_circle:pause:no=pause_circle/yes=play_circle?Play/pause`
`SUBS` = `command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles`
`COND` = `<has_many_video>video,<has_many_edition>editions,<stream>button:stream-quality,<stream>button:download-video`

| Key | calm | bar | focus |
|---|---|---|---|
| `controls` | `prev,PLAY,next,space,<video,audio>speed,SUBS,button:audio-tracks,COND,items,MORE,fullscreen` | same as calm | `space,prev,PLAY,next,space,items,MORE,fullscreen` |
| `opacity.controls` | `0` | `0.92` | `0` |
| `controls_persistency` | `idle` | `idle,windowed` | `idle` |
| `progress` | `always` | `always` | `always` |
| `progress_size` | `3` | `3` | `3` |
| `menu_item_height` | `40` | `40` | `40` |

## Size definition

| Key | comfortable | compact |
|---|---|---|
| `controls_size` | `44` | `36` |
| `controls_spacing` | `4` | `2` |
| `controls_margin` | `8` | `6` |
| `timeline_size` | `40` | `32` |

## Owned keys (FR-011)

`controls`, `color`, `opacity`, `controls_size`, `controls_spacing`,
`controls_margin`, `controls_persistency`, `timeline_size`, `progress`,
`progress_size`, `menu_item_height`. Each is written as `uosc-<key>` in
`script-opts`. Never written at runtime: `border_radius`, `chapter_ranges`
(mpv.conf), `proximity_out`, `destination_time`, `top_bar_controls`.

## More menu (built per open)

`type = 'ui_appearance_more'`. Rows and commands:

| Row | Command | Listed when | Marked when |
|---|---|---|---|
| Appearance > Style / Background / Accent / Size > value | `script-message-to ui_appearance set <field> <value>`, `keep_open` | always | value is current |
| Subtitles | `script-binding ytdl_sub_menu/open` | always | — |
| Audio | `script-message-to player_toolbar open-audio-menu` | always | — |
| Stream quality | `script-message-to player_toolbar open-quality-menu` | stream | — |
| Playback > Shuffle | `script-binding uosc/shuffle` (theme flips its tracked state) | always | tracked state on |
| Playback > Loop playlist | `cycle-values loop-playlist inf no` | always | `loop-playlist` ≠ `no` |
| Playback > Loop file | `cycle-values loop-file inf no` | always | `loop-file` ≠ `no` |
| Playback > Speed > 0.5 … 2 | `set speed <v>` | always | `speed` equals value |
| Picture & sound > Anime4K mode > mode | `script-message-to profile_picker set-mode <mode>` | always | `user-data/anime4k/mode` equals mode |
| Picture & sound > Stable volume | `script-message-to player_toolbar toggle-stable-volume` | always | `user-data/player_toolbar/stable-volume` |
| Picture & sound > Video track | `script-binding uosc/video` | more than one video track | — |
| Picture & sound > Editions | `script-binding uosc/editions` | more than one edition | — |
| Open > Paste link (hint `Ctrl+V`) | `script-binding smart_paste/paste-to-open` | always | — |
| Open > Open file | `script-binding uosc/open-file` | always | — |
| Open > Download video | `script-message-to player_toolbar download-video` | stream | — |
| Full uosc menu | `script-binding uosc/menu` | always | — |
| All shortcuts (hint `F9`) | `script-message-to help_overlay help` | always | — |

Speed values: 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2. Rows marked active carry no hint
(FR-023 exception).
