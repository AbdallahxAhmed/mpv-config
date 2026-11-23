# Contract: `ui_appearance` script interface (spec 006)

The theme script is `scripts/ui_appearance.lua` (mpv script name `ui_appearance`).
Its pure logic lives in `scripts/modules/looks.lua`, loaded the way
`player-toolbar.lua` loads `scripts/modules/stream_policy.lua`
(`mp.find_config_file`, then `dofile`).

## Script messages received

| Message | Arguments | Effect |
|---|---|---|
| `open-more` | none | Builds the More menu from current state and opens it (`script-message-to uosc open-menu <json>`). |
| `set` | `<field> <value>` | Validates; saves `ui_appearance.conf`; writes `script-opts` once; sends `update-menu` if the More menu is open. Unknown field or value: ignored with a log warning, nothing saved or applied. |

## Script messages sent

| To | Message | When |
|---|---|---|
| `uosc` | `open-menu <json>` | `open-more` |
| `uosc` | `update-menu <json>` | after a `set` while the More menu is open |

## Properties written

| Property | Owner | Content |
|---|---|---|
| `script-opts` | `ui_appearance` | the `uosc-<key>` entries for the owned keys (data-model.md); all other entries kept as read |
| `user-data/anime4k/mode` | `profile_picker` | the mode now applied: `off` `fast` `A` `A+A` `B` `B+B` `C` `C+A` |
| `user-data/player_toolbar/stable-volume` | `player_toolbar` | `true` while the stable-volume filter is active |

## Module API (`scripts/modules/looks.lua`)

| Function | Returns |
|---|---|
| `looks.DEFAULTS` | `{style='calm', background='dark', accent='amber', size='comfortable'}` |
| `looks.CHOICES` | allowed values per field, in menu order |
| `looks.OWNED_KEYS` | the owned uosc keys, in a literal table the Python check can parse |
| `looks.normalize(look)` | `(clean_look, fallbacks)`: invalid fields replaced by defaults, `fallbacks` lists them |
| `looks.uosc_options(look)` | map `uosc-<key> -> string` for every owned key |
| `looks.merge_script_opts(current, look)` | new `script-opts` map: `current` with owned keys replaced |
| `looks.more_menu(look, state)` | the More menu table (before JSON); `state` holds the properties of research.md R5 |
| `looks.serialize(look)` | the file text |

Every function is pure (no `mp` calls), so the Lua suite tests it directly.
