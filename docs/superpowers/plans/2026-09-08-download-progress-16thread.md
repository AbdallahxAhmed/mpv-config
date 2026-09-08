# 16-Thread Supercharged Download & Progress System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 16-thread multi-connection download acceleration with live in-player visual progress tracking (Design A), eliminating cache truncation, HTTP 429 rate-limiting, and Windows file-locking collisions.

**Architecture:** A lightweight headless Python worker (`tools/download_worker.py`) executes `yt-dlp` using `aria2c` for 16-split connections on progressive MP4s and 6 concurrent fragments on HLS/DASH. The worker streams stdout and atomically writes updates via `os.replace()` to a temp JSON file. `player-toolbar.lua` polls this state file every 250ms with `pcall` and updates `uosc` button badges, tooltips, and micro-bar progress. Strict `bof`/`eof` checks prevent truncated `dump-cache` exports.

**Tech Stack:** Python 3.11+, Lua 5.1 / LuaJIT (MPV), `aria2c`, `yt-dlp`, UOSC, Windows NTFS / `os.replace`.

---

## File Structure & Responsibilities

- **`deploy/registry.py`**: Add `aria2` package definition for Windows `winget`, Arch `pacman`, Ubuntu `apt`, Fedora `dnf`, macOS `brew`.
- **`scripts/modules/stream_policy.lua`**: Update `analyze_cache_coverage` to enforce `bof == true` and `eof == true` before allowing cache export. Add worker argument builder.
- **`tools/download_worker.py`**: Headless background downloader process; orchestrates `yt-dlp` + `aria2c` (16 threads), forwards headers/cookies, parses progress, and atomically writes state.
- **`scripts/player-toolbar.lua`**: Dispatches download worker, polls status file every 250ms, updates `uosc` button badge (`15%`, `45%`, `80%`, `OK`, `SAVED`) and tooltip, handles completion/failure.
- **`tools/patch_uosc_button.py`**: Idempotent patch utility to optionally add micro-bar rendering to vendored/installed `uosc/elements/Button.lua`.
- **`tests/test_download_worker.py`**: Python unit tests for worker CLI, regex parsing, header forwarding, and atomic state file replacement.
- **`tests/lua/test_stream_policy.lua`**: Lua unit tests for `bof`/`eof` cache coverage enforcement.
- **`tests/lua/test_player_toolbar.lua`**: Lua unit tests for download progress polling and badge publishing.

---

### Task 1: Register `aria2` Dependency in `deploy/registry.py` and Install via WinGet

**Files:**
- Modify: `deploy/registry.py:280-300`
- Test: `tests/test_config.py`

- [ ] **Step 1: Add `aria2` definition to `deploy/registry.py`**
  Add:
  ```python
  "aria2": {
      "windows": {"method": "winget", "id": "aria2.aria2"},
      "arch":    {"method": "pacman", "pkg": "aria2"},
      "ubuntu":  {"method": "apt",    "pkg": "aria2"},
      "fedora":  {"method": "dnf",    "pkg": "aria2"},
      "macos":   {"method": "brew",   "pkg": "aria2"},
      "verify":  ["aria2c", "--version"],
  },
  ```

- [ ] **Step 2: Verify registry loads cleanly with Python tests**
  Run: `python -m unittest tests/test_config.py -v`
  Expected: PASS

- [ ] **Step 3: Install `aria2.aria2` via WinGet**
  Run: `winget install --id aria2.aria2 -e --accept-package-agreements --accept-source-agreements`
  Verify: `aria2c --version` outputs 1.37.x.

- [ ] **Step 4: Commit**
  ```bash
  git add deploy/registry.py
  git commit -m "feat(deploy): register aria2 dependency for multi-connection downloads"
  ```

---

### Task 2: Strict Cache Truncation Protection in `scripts/modules/stream_policy.lua`

**Files:**
- Modify: `scripts/modules/stream_policy.lua:260-310`
- Modify: `tests/lua/test_stream_policy.lua`

- [ ] **Step 1: Write failing test in `tests/lua/test_stream_policy.lua`**
  Add test asserting that `analyze_cache_coverage` returns `is_complete = false` if `cache_state.bof ~= true` or `cache_state.eof ~= true`, even if percentage or time range is high.

- [ ] **Step 2: Run Lua tests to verify failure**
  Run: `python tests/run_lua_tests.py`
  Expected: FAIL on missing BOF/EOF check.

- [ ] **Step 3: Implement strict BOF/EOF validation in `stream_policy.lua`**
  Update `analyze_cache_coverage`:
  ```lua
  local bof = cache_state.bof == true
  local eof = cache_state.eof == true
  if not bof or not eof then
      return { is_complete = false, percent = 0, coverage_ratio = 0 }
  end
  ```

- [ ] **Step 4: Run Lua tests to verify pass**
  Run: `python tests/run_lua_tests.py`
  Expected: PASS (all 25 policy tests).

- [ ] **Step 5: Commit**
  ```bash
  git add scripts/modules/stream_policy.lua tests/lua/test_stream_policy.lua
  git commit -m "fix(policy): enforce strict bof and eof checks before allowing cache dump"
  ```

---

### Task 3: Headless Multi-Thread Download Worker (`tools/download_worker.py`)

**Files:**
- Create: `tools/download_worker.py`
- Create: `tests/test_download_worker.py`

- [ ] **Step 1: Write failing tests in `tests/test_download_worker.py`**
  Write tests covering:
  - `build_ytdl_args()` with progressive MP4 using `aria2c` (`-s 16 -x 16 -k 1M --retry-wait=2 --max-tries=3`).
  - `build_ytdl_args()` with HLS/DASH or fallback using `--concurrent-fragments 6`.
  - Header forwarding (`--user-agent`, `--referer`, `--add-header Cookie:...`).
  - Regex progress parser: extracts percent, speed, ETA.
  - Atomic state file write (`.tmp` + `os.replace`).

- [ ] **Step 2: Run test to verify failure**
  Run: `python -m unittest tests/test_download_worker.py`
  Expected: FAIL (module not found).

- [ ] **Step 3: Implement `tools/download_worker.py`**
  Implement the CLI worker:
  - Parses `--state-file`, `--url`, `--output`, `--format`, `--audio-only`, `--user-agent`, `--referer`, `--cookies`.
  - Detects `aria2c` in PATH / standard directories.
  - Spawns `yt-dlp` with `--newline --progress`.
  - Parses stdout lines in a loop.
  - Atomically writes JSON state to `f"{state_file}.tmp"` and replaces with `os.replace`.
  - Handles exit codes and records clean error message if failed.

- [ ] **Step 4: Run tests to verify pass**
  Run: `python -m unittest tests/test_download_worker.py -v`
  Expected: PASS.

- [ ] **Step 5: Commit**
  ```bash
  git add tools/download_worker.py tests/test_download_worker.py
  git commit -m "feat(tools): add headless multi-thread download worker with atomic progress updates"
  ```

---

### Task 4: Toolbar Integration & Live Progress Polling in `scripts/player-toolbar.lua`

**Files:**
- Modify: `scripts/player-toolbar.lua:340-580`
- Modify: `tests/lua/test_player_toolbar.lua`

- [ ] **Step 1: Write failing test in `tests/lua/test_player_toolbar.lua`**
  Test that `start_download` initiates polling timer, safely parses status JSON with `pcall`, updates `download_badge` and `tooltip`, and stops timer on completion.

- [ ] **Step 2: Run Lua tests to verify failure**
  Run: `python tests/run_lua_tests.py`
  Expected: FAIL on missing worker invocation and polling.

- [ ] **Step 3: Implement download worker spawning and timer polling in `player-toolbar.lua`**
  - Extract `user-agent`, `referrer`, and `cookies`.
  - Generate session ID and state file `%TEMP%/mpv_dl_state_<id>.json`.
  - Launch `tools/download_worker.py` via `mp.command_native_async({name = 'subprocess', playback_only = false, ...})`.
  - Start 250ms periodic timer with `pcall` wrapped `utils.read_file(state_file)`:
    - Update `download_badge = state.percent_int .. '%'`
    - Update `tooltip = string.format("Downloading: %s%% (%s • ETA %s • 16 threads)", state.percent_int, state.speed, state.eta)`
    - Update `progress = state.percent / 100`
    - Call `publish_download(true)`.
  - On exit: show `OK` badge for 4s, clean up state file and timer.

- [ ] **Step 4: Run Lua tests to verify pass**
  Run: `python tests/run_lua_tests.py`
  Expected: PASS.

- [ ] **Step 5: Commit**
  ```bash
  git add scripts/player-toolbar.lua tests/lua/test_player_toolbar.lua
  git commit -m "feat(toolbar): integrate live progress polling and dynamic badge updates"
  ```

---

### Task 5: Optional Idempotent Micro-Bar Patcher (`tools/patch_uosc_button.py`)

**Files:**
- Create: `tools/patch_uosc_button.py`

- [ ] **Step 1: Write idempotent patch script**
  Checks `%APPDATA%\mpv\scripts\uosc\elements\Button.lua` (and repo if present):
  - If `self.progress` rendering is not present in `Button:render()`, injects the 2.5px micro bottom bar drawing block with ASS rectangle.
  - If already present, exits cleanly with no-op.
  - Creates `.bak` backup before patching.

- [ ] **Step 2: Run patch script on active APPDATA UOSC**
  Run: `python tools/patch_uosc_button.py`
  Expected: Success, patched cleanly.

- [ ] **Step 3: Commit**
  ```bash
  git add tools/patch_uosc_button.py
  git commit -m "feat(tools): add idempotent uosc button micro-bar progress patcher"
  ```

---

### Task 6: Live Deployment & End-to-End Verification

**Files:**
- Deploy to `%APPDATA%\mpv\scripts\` and `%APPDATA%\mpv\tools\`

- [ ] **Step 1: Deploy all updated scripts and tools to `%APPDATA%\mpv\`**
  Copy `stream_policy.lua`, `player-toolbar.lua`, and `tools/download_worker.py`.

- [ ] **Step 2: Run all test suites**
  Run: `python tests/run_lua_tests.py`
  Run: `python -m unittest discover -s tests -v`
  Expected: All tests PASS.

- [ ] **Step 3: End-to-end download test**
  Verify live stream download with 16-connection speed, live percentage badge (`12%` → `45%` → `85%` → `OK`), and absence of sharing violations.

- [ ] **Step 4: Push to GitHub main**
  Run: `git push origin main`
  Expected: Working tree clean, synced to remote.
