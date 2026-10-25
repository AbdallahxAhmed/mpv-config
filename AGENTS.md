<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at specs/004-playback-performance/plan.md
<!-- SPECKIT END -->

## Agent context — current status (refreshed 2026-10-25)

### Where things live
- **Dev repo (source of truth):** `C:\Users\Abdallah_Ahmed\Desktop\dev\mpv\mpv-config` — all edits, tests and commits happen here.
- **This checkout:** `C:\Users\Abdallah_Ahmed\Desktop\mpv-config-clean` — same origin (`github.com/AbdallahxAhmed/mpv-config.git`); sync with `git pull --ff-only` when it falls behind.
- **Deploy clone:** `~\.mpv-config-deploy` — the editable Python install points HERE, so its `__editable__` finder beats `sys.path`: `git pull` it before every test/import run or tests see stale code.
- **Deployed config:** `%APPDATA%\mpv` — what the user's mpv actually runs.
- **Deploy sequence:** commit → push → `git -C ~\.mpv-config-deploy pull --ff-only` → `python -m deploy.deployer --update` (interactive prompt: answer `y`).
- **Test suites:** `python -m unittest discover -s tests` and `python tests/run_lua_tests.py`.

### State of main
- `45aad00` on `main`, pushed, deploy clone and `%APPDATA%\mpv` at the same commit (deployed 2026-10-23).
- Tests green: 421 Python (43 skipped) + all Lua suites. A rare transient single-error run can hit the network-port tests (unreleased socket); **re-run before believing a failure**.

### How the keyboard-layout guard works now (scripts/keyboard_layout.lua + src/mpv_config/layout_guard.py)
- Purpose: mpv matches bindings by the CHARACTER a key produces, so an Arabic layout breaks every letter binding. Switching layouts is a dead end (`WM_INPUTLANGCHANGEREQUEST` only toggles to the foreground thread's last-active layout — measured US→Arabic→US), so a low-level Windows keyboard hook TRANSLATES instead: swallows the physical key and injects a `KEYEVENTF_UNICODE` event for the US character of the same physical key.
- Decision: the virtual key code is PHYSICAL, so `_us_char()` (VK table, shift-aware) gives the target character. Translation happens iff mpv's thread layout is not a US one (`GetKeyboardLayout(mpv_thread)` low word ≠ `0x0409`). An unreadable/unknown layout means DO NOT translate. Ctrl/Alt/Win combos are never translated (Windows already makes them layout-independent control codes). A swallowed key's key-up is swallowed too, so mpv never sees a release without a keydown.
- Why the layout HANDLE and not a character query: on this machine `MapVirtualKeyExW(MAPVK_VK_TO_CHAR)` and `ToUnicodeEx` misbehave (returned scan codes like 0x23 for H, i.e. '#', and identical values for every layout; best chalked to earlier synthetic key injections leaving key-state pollution). Do not reintroduce VK→char queries.
- The script spawns the guard once per mpv instance, after the first file-loaded (python startup ≈120 ms). Spawn line ends with `>nul 2>&1` — without the redirect `io.popen` blocks mpv's script thread on the guard's pipe for the guard's lifetime. Don't remove it.
- Diagnostics: `%APPDATA%\mpv\keyboard_layout.log`. `guard started` per launch; `translate vk=N -> 'c'` only when a key is actually translated. If `mp.get_config_dir` semantics matter anywhere: that function DOES NOT EXIST in this mpv (probe: nil) — always use `pcall(mp.get_property, "config-dir")`. Same for `profile_picker.lua` and `player-toolbar.lua` (fixed 2026-10-23).

### Open item 1 — user-side acceptance (blocked on the user)
The h-key fix cannot be auto-verified headlessly (synthetic key injection would type into whatever the user is running). The log shows 18 clean `guard started` entries but ZERO `translate` lines so far, so the guard is alive but the fix is still unproven. Acceptance recipe: restart mpv → switch to the Arabic layout while mpv is focused → press h → expect `translate vk=48 -> 'h'` in `%APPDATA%\mpv\keyboard_layout.log`. If nothing appears, check that a python process with `layout_guard` on its command line exists while mpv runs.

### Open item 2 — guard has no single-instance / self-cleanup
`start /B` guards outlive their mpv (3 orphan guards were alive on 2026-10-25 with NO mpv running). Harmless to correctness (injected keys carry `LLKHF_INJECTED` and are skipped, so stacked hooks never double-translate) but they accumulate as zombies. Candidate fix: pidfile/lockfile with takeover, plus self-kill when no window of class `mpv` exists for some grace period. Not done yet — needs the user's go-ahead since it touches live processes.

### Shipped earlier this cycle (all deployed)
- Fast quality switch (`96490e4`): wide→narrow is instant, playlist keeps canonical URLs.
- Anime detection + selectable Anime4K mode + install-time choice + cheat sheet.
- Thumbnail black-box after 1080p→720p switch: `is_same_video()` (same path OR duration±1.5s + title) keeps the overlay; uosc's timeline rect is its own drawing, so a black box means thumbfast's overlay died.
- Streaming slowness: the real cause was thumbfast's worker being a SECOND mpv downloading the same stream (~43% of the connection, playback fell ~2 s behind). Fixes: no pre-spawn for network streams, worker cache capped 16 MiB / 1 s readahead. Verified with a throttled HTTP server (`%TEMP%\opencode\http_stream.py`, harness `compare_stream.py`/`harness.py` — agent-owned mpv must be matched and killed by command line only).

### Agent operating rules (standing, from the user)
- ALL tests must run silent and headless (user watches videos while the agent works): `--no-audio --ao=null --vo=null --no-terminal --really-quiet`, hidden windows, no focus stealing, no audio.
- NEVER kill processes the user started — only agent-spawned ones, matched by command line (`thumbfast.out`, `127.0.0.1:8731`, `mpv_probe_pipe`).
- Replies to the user go in SHORT ARABIC; work/reasoning in English.
- mpv binary: `C:\Program Files\mpv\mpv.exe`. Test clip: `%TEMP%\opencode\clip_1080p24_10bit.mkv`; test URL: `http://127.0.0.1:8731/clip.mkv`.
