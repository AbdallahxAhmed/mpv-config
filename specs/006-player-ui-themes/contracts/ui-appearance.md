# Contract: `ui_appearance` script interface (spec 006)

The theme script is `scripts/ui_appearance.lua` (mpv script name `ui_appearance`).
Its pure logic lives in `scripts/modules/looks.lua`, loaded the way
`player-toolbar.lua` loads `scripts/modules/stream_policy.lua`: with
`mp.find_config_file`, then `dofile`.

## Script messages received

| Message | Arguments | Effect | Phase |
|---|---|---|---|
| `open-more` | none | Reads `state`, builds the More menu and sends `script-message-to uosc open-menu <json>`. | P1 |
| `set` | `<field> <value>` | Validates the value, saves `ui_appearance.conf`, writes `script-opts` once, then sends `update-menu`. An unknown field or value is ignored with a log warning; nothing is saved or applied. | P3 |
| `toggle-shuffle` | none | Runs `script-binding uosc/shuffle`, flips the shuffle flag, then sends `update-menu`. | P4 |

## Script messages sent

| To | Message | When |
|---|---|---|
| `uosc` | `open-menu <json>` | on `open-more` |
| `uosc` | `update-menu <json>` | after `set` and `toggle-shuffle`; uosc ignores it unless a `ui_appearance_more` menu is open |

## Properties

| Property | Writer | Content |
|---|---|---|
| `script-opts` | `ui_appearance` | The `uosc-<key>` entries for the owned keys (data-model.md). Every other entry is kept as read. |
| `user-data/anime4k/mode` | `profile_picker` | The saved Anime4K mode (`state.mode`): `off` `fast` `A` `B` `C` `A+A` `B+B` `C+A`. Published at load, in `apply_mode` and in `on_shaders_changed`. |
| `user-data/player_toolbar/stable-volume` | `player_toolbar` | `true` while the stable-volume filter is active. Set in `publish()` before its early return. |

## `state` table passed to `looks.more_menu`

| Field | Source |
|---|---|
| `loop_playlist` | `loop-playlist` (string) |
| `loop_file` | `loop-file` (string) |
| `speed` | `speed` (number) |
| `video_tracks` | count of `track-list` entries with `type == 'video'` and not `image` or `albumart` |
| `editions` | count of `edition-list` entries |
| `is_stream` | `demuxer-via-network` (bool) |
| `anime4k_mode` | `user-data/anime4k/mode` (string or nil) |
| `stable_volume` | `user-data/player_toolbar/stable-volume` (bool or nil) |
| `shuffle` | the script's shuffle flag (bool) |

`state` is read on `open-more`, and read again before every `update-menu`.

## Module API (`scripts/modules/looks.lua`)

| Name | Value or return |
|---|---|
| `DEFAULTS` | `{style='calm', background='dark', accent='amber', size='comfortable'}` |
| `CHOICES` | the allowed values per field, in menu order (data-model.md) |
| `OWNED_KEYS`, `OWNED_COLOR_KEYS`, `OWNED_OPACITY_KEYS`, `MORE_UOSC_BINDINGS` | literal tables of quoted strings, one table per `local NAME = { ... }` block, so the Python guard can parse them with a regex |
| `normalize(raw)` | `(look, fallbacks)`: an empty or invalid field becomes its default and is listed in `fallbacks` (field names in `DEFAULTS` order) |
| `uosc_options(look)` | a map from `uosc-<key>` to a string, for every owned key. Sub-keys follow the fixed order, so the same look always gives the same strings. |
| `merge_script_opts(current, look)` | a new map: `current` with the owned keys replaced |
| `serialize(look)` | the file text (data-model.md) |
| `more_menu(look, state)` | the More menu table, before JSON encoding; its rows grow by phase (plan) |
| `contrast(fg_hex, bg_hex)` and `blend(top_hex, alpha, under_hex)` | the helpers the contrast test uses (research R6) |

Every function is pure (no `mp` calls), so the Lua suite tests the module directly.
