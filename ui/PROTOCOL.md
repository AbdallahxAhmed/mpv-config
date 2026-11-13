# mpv-config-ui protocol (v1)

`mpv-config-ui` is a Go ([Bubble Tea](https://github.com/charmbracelet/bubbletea))
renderer for the Python deployer. It starts the deployer as its child with
`MPV_CONFIG_UI_PROTOCOL=1`; `deploy/ui.py` then emits events instead of drawing.
The deployer stays the only source of truth: the renderer draws what it is told
and answers prompts.

## Transport

- **Events** (child → renderer): one per line on the child's stdout, the ASCII
  record separator `0x1E` followed by a JSON object. Lines without the
  separator are stray output and are shown as plain text.
- **Replies** (renderer → child): one JSON object per line on the child's stdin,
  `{"id": <prompt id>, "value": <answer>}`. Subprocesses of the deployer get
  `stdin=DEVNULL` in protocol mode so they can never read a reply.
- **stderr** is captured; its tail is shown if the command fails.
- `MPV_CONFIG_UI_INTERACTIVE=1` tells the child that prompts can be answered.

## Events

| `t` | Fields | Meaning |
|---|---|---|
| `hello` | `v`, `command` | optional greeting |
| `outline` | `steps: [{key, title}]` | stages shown up front as a checklist |
| `phase` | `key`, `title` | a stage starts (`ui.header`); the previous one completes |
| `log` | `level` (`step` `info` `item` `ok` `warn` `error`), `text`, `detail`, `transient` | `ok`/`warn`/`error` stay in the scrollback; the rest is live narration |
| `table` | `title`, `columns`, `rows` | 2 columns → key/value list; a `Status` column → "N/M checks passed" plus failing rows |
| `plan` | `title`, `groups: [{label, entries: [{action, target, detail}]}]` | compact install plan |
| `summary` | `succeeded`, `skipped`, `failed: [{name, detail}]` | stage result counts |
| `progress` | `id`, `label`, `state` (`connect` `run` `done` `fail`), `done`, `total` | download bar |
| `command` | `id`, `state` (`start` `output` `end`), `text`, `ok`, `secs`, `tail` | external command with a live timer; the tail of a failed command is kept |
| `spinner` | `state` (`start` `stop`), `text` | indeterminate activity |
| `panel` | `title`, `text`, `style` | final message; first line is the headline, `Key: value` lines are aligned |
| `prompt` | `id`, `kind` (`confirm` `menu`), `text`, `items: [{value, label}]`, `default` | blocks the child until a reply |
| `sudo` | `id`, `reason` | the renderer suspends itself and runs `sudo -v` on the real terminal; reply `true`/`false` |

## Cancellation

Ctrl+C is forwarded once as a graceful interrupt (SIGINT on POSIX,
`CTRL_BREAK_EVENT` on Windows, which `deploy/ui_protocol.py` maps to
`KeyboardInterrupt`), so the transaction code can roll back. A second Ctrl+C
kills the child.

## Release

`python ui/build_release.py --check` rebuilds all targets reproducibly and
compares them with the SHA-256 pins in `ui/release.json`; the CLI only runs a
downloaded renderer whose hash matches. Set `MPV_CONFIG_UI=plain` to opt out,
`MPV_CONFIG_UI_BIN=<path>` to use a local build.
