<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at specs/004-playback-performance/plan.md
<!-- SPECKIT END -->

## Agent context — current status (refreshed 2026-10-25, layout twins shipped)

### Where things live
- **This repo (source of truth):** `~\Desktop\mpv-config-clean` — all edits, tests and commits happen here; origin `github.com/AbdallahxAhmed/mpv-config.git`.
- **Deploy clone:** `~\.mpv-config-deploy` — the editable Python install points HERE, so its `__editable__` finder beats `sys.path`: `git pull` it before every test/import run or tests see stale code. Until it is pulled, load new modules by file location (see `_layout_twins_module` for the pattern).
- **Deployed config:** `%APPDATA%\mpv` — what the user's mpv actually runs.
- **Deploy sequence:** commit → push → `git -C ~\.mpv-config-deploy pull --ff-only` → `python -m deploy.deployer --update` (interactive prompt: answer `y`).
- **Test suites:** `python -m unittest discover -s tests` and `python tests/run_lua_tests.py`.

### State of main
- `12f848a` (twins + sequences) on `main`, pushed; deployed to `%APPDATA%\mpv` on 2026-10-25. Tests green: 439 Python (43 skipped) + all Lua suites. A rare transient single-error run can hit the network-port tests (unreleased socket); **re-run before believing a failure**.

### How the keyboard layout works now (layout twins; hook guard retired to opt-in)
- mpv matches bindings by the CHARACTER a key produces ("mpv uses input translated by the current OS keyboard layout, rather than physical scan codes"; upstream issue #351 open since 2013 — no native fix). `src/mpv_config/layout_twins.py` generates a twin block appended to the DEPLOYED input.conf on every install/update: for each printable Latin binding, a binding on the Arabic-101 output of the SAME physical key (`c→ؤ a→ش h→ا n→ى ?→؟` singles; `b/G/B` as `ل-ا/ل-أ/ل-آ` key sequences). Users write Latin only; twins regenerate — nothing maintained by hand, no processes.
- Table provenance: one-shot offline probe of the loaded Arabic layout (hkl `0x04010c01`, KLID `00000401` = Arabic 101) via `ToUnicodeEx` with an explicit hkl + zeroed state + dead-key double-call, agreeing with xkb `ara(basic)` and with the old session's probe. This is NOT the guard's banned RUNTIME VK→char path (that trap was about live queries under polluted key state). User's layouts (registry): US + `00000c01` substituted to `00000401`.
- Untwinnable key: ONLY `g`. The lam-alef keys are twinned as mpv KEY SEQUENCES (`b`→`ل-ا`, `G`→`ل-أ`, `B`→`ل-آ`; keys joined with `-` — mpv's sequence matcher consumes both events, measured) and `h`→`ا` is safe as a single because a completed sequence swallows the second event. `g`→`ل` must stay unbound: a single-key binding on a sequence's FIRST element defeats every sequence; g carries the `Ctrl+Shift+m` backup (control code = same combo in every layout; h/b/G/B keep `Ctrl+Shift+h/s/b/u` backups too). Quirk (measured, accepted): sequences have NO timeout — an Arabic `h` immediately after an Arabic `g` completes the `b` sequence. ASCII shift-layer twins (`>`→`.` etc.) are refused: binding them changes US behavior (measured: `Shift+.` and `.` collide in mpv's binder).
- The hook guard (`scripts/keyboard_layout.lua` + `src/mpv_config/layout_guard.py`) still ships but is `enabled=no` by default (template) and migrated off on existing installs (`_migrate_keyboard_layout_conf`). Re-enable in `script-opts/keyboard_layout.conf` for layouts beyond Arabic 101. Its traps (spawn `>nul 2>&1`, `mp.get_config_dir` absent) live in CONTEXT.md §9.
- Deployer seams: `_patch_input_conf` (fresh installs) and `_migrate_input_conf` rule 8 (updates; also removes the legacy "Arabic Bilingual Twin Bindings" mnemonic block — actions on OTHER physical keys like `ح`=P — and ensures the backups). Tests: `tests/test_layout_twins.py` (unit + migration) and `tests/test_layout_twins_integration.py` (agent-owned `--no-config` mpv over a unique IPC pipe: `keypress` an Arabic char, assert via `user-data` that the twin fired — red without the block, green with it).

### Open item — user-side acceptance (blocked on the user)
The physical keystroke half cannot be verified headlessly (synthetic injection would type into the user's apps). Recipe after deploy: restart mpv → switch to Arabic while mpv is focused → press physical `C`, `A`, `N`, `H` → subtitles/audio/sync/history must open; press physical `B` → subtitle backdrop toggles (lam-alef sequence twin); `?` opens the cheat sheet; `Ctrl+Shift+M` marks a SponsorBlock segment (g's backup, must work in BOTH layouts). If c/a/n/h/b fail, run `mpv --input-test` under Arabic to see exactly which characters arrive and re-probe the table.

### Shipped earlier this cycle (all deployed)
- Fast quality switch (`96490e4`): wide→narrow is instant, playlist keeps canonical URLs.
- Anime detection + selectable Anime4K mode + install-time choice + cheat sheet.
- Thumbnail black-box after 1080p→720p switch: `is_same_video()` (same path OR duration±1.5s + title) keeps the overlay; uosc's timeline rect is its own drawing, so a black box means thumbfast's overlay died.
- Streaming slowness: the real cause was thumbfast's worker being a SECOND mpv downloading the same stream (~43% of the connection, playback fell ~2 s behind). Fixes: no pre-spawn for network streams, worker cache capped 16 MiB / 1 s readahead. Verified with a throttled HTTP server (`%TEMP%\opencode\http_stream.py`, harness `compare_stream.py`/`harness.py` — agent-owned mpv must be matched and killed by command line only).

### Agent operating rules (standing, from the user)
- ALL tests must run silent and headless (user watches videos while the agent works): `--no-audio --ao=null --vo=null --no-terminal --really-quiet`, hidden windows, no focus stealing, no audio.
- NEVER kill processes the user started — only agent-spawned ones, matched by command line (`thumbfast.out`, `127.0.0.1:8731`, `mpv_probe_pipe`, `mpv_twins_test`).
- Replies to the user go in ENGLISH (user's request 2026-10-25: Arabic text renders reversed for him; supersedes the earlier short-Arabic rule). Work/reasoning in English.
- mpv binary: `C:\Program Files\mpv\mpv.exe`. Test clip: `%TEMP%\opencode\clip_1080p24_10bit.mkv`; test URL: `http://127.0.0.1:8731/clip.mkv`.
