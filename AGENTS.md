<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at specs/004-playback-performance/plan.md
<!-- SPECKIT END -->

## Agent context — current status (refreshed 2026-10-26, Arabic keyboard: AHK scan-code helper & clean layout twins shipped)

### Where things live
- **This repo (source of truth):** `~\Desktop\mpv-config-clean` — all edits, tests and commits happen here; origin `github.com/AbdallahxAhmed/mpv-config.git`.
- **Deploy clone:** `~\.mpv-config-deploy` — the editable Python install points HERE, so its `__editable__` finder beats `sys.path`: `git pull` it before every test/import run or tests see stale code. Until it is pulled, load new modules by file location (see `_layout_twins_module` for the pattern).
- **Deployed config:** `%APPDATA%\mpv` — what the user's mpv actually runs.
- **Deploy sequence:** commit → push → `git -C ~\.mpv-config-deploy pull --ff-only` → `python -m deploy.deployer --update` (interactive prompt: answer `y`).
- **Test suites:** `python -m unittest discover -s tests` and `python tests/run_lua_tests.py`.

### State of main
- Up to date on `main`, deployed to `%APPDATA%\mpv`. Tests green: all Python suites + all Lua suites.

### Arabic keyboard — what works NOW (deployed, verified in live headless mpv)
| User presses (Arabic layout) | Delivers to mpv | Fires |
| --- | --- | --- |
| Physical `H`, `B`, `G`, etc. bare | `h`, `b`, `g` | history / backdrop toggle / mark segment — **1:1 physical scan-code parity via AutoHotkey helper (`tools/mpv_arabic_layout.ahk`)** |
| `C` `A` `N` bare | `ؤ` `ش` `ى` | subtitles / audio / sync menus (built-in layout twins fallback) |
| Physical `?` (`Shift + /`) or `F9` | `?` / `؟` | Help Overlay cheat sheet (ASS formatted, SmartSkip conflict resolved) |
| Physical `/` bare | `/` | `ignore` (prevents accidental volume drops) |
| `Shift+H` `Shift+M` `Shift+S` `Shift+B` `Shift+U` | `أ` `’` `ٍ` `آ` `‘` | history / mark / submit / backdrop / upvote (cross-platform bare-shift route) |
| `Ctrl+Shift+H/M/S/B/U` | `Ctrl+أ/’/ٍ/آ/‘` | same five actions |
| English layout | Latin | everything as always |

### How the keyboard layout works (AHK hardware parity + native layout twins; retired ctypes hook removed)
- **Windows physical key parity:** `tools/mpv_arabic_layout.ahk` maps physical scan codes (`SC023` for H, `SC030` for B, `SC022` for G, etc.) directly when mpv is focused and Arabic is active. Uses `*` wildcards with `{Blind}` mode to transparently preserve Shift, Ctrl, and Alt modifiers. Launched silently on mpv startup by `scripts/keyboard_layout.lua` via `mp.find_config_file()`, and auto-terminates 2 seconds after mpv closes.
- **Native layout twins:** `src/mpv_config/layout_twins.py` generates twin bindings appended to `input.conf` for printable Latin keys (`c→ؤ a→ش n→ى ?→؟`) and modified combos. Pure config, zero runtime processes, cross-platform.
- **Cleaned up technical debt:** The legacy ctypes keyboard hook (`src/mpv_config/layout_guard.py`) was completely pruned.

### Shipped earlier this cycle (all deployed)
- Fast quality switch (`96490e4`): wide→narrow is instant, playlist keeps canonical URLs.
- Anime detection + selectable Anime4K mode + install-time choice + cheat sheet.
- Thumbnail black-box after 1080p→720p switch: `is_same_video()` (same path OR duration±1.5s + title) keeps the overlay.
- Streaming slowness: worker cache capped 16 MiB / 1 s readahead, no pre-spawn for network streams.
- Help Overlay: native `mp.create_osd_overlay` rendering crisp ASS vector typography with shadow.

### Agent operating rules (standing, from the user)
- ALL tests must run silent and headless (user watches videos while the agent works): `--no-audio --ao=null --vo=null --no-terminal --really-quiet`, hidden windows, no focus stealing, no audio.
- NEVER kill processes the user started — only agent-spawned ones, matched by command line (`thumbfast.out`, `127.0.0.1:8731`, `mpv_probe_pipe`, `mpv_twins_test`).
- Replies to the user go in ENGLISH (user's request 2026-10-25: Arabic text renders reversed for him). Work/reasoning in English.
- mpv binary: `C:\Program Files\mpv\mpv.exe`. Test clip: `%TEMP%\opencode\clip_1080p24_10bit.mkv`; test URL: `http://127.0.0.1:8731/clip.mkv`.
