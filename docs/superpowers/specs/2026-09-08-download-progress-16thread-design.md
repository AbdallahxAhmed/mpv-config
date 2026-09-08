# Specification: 16-Thread Supercharged Download & Progress System

**Date:** 2026-09-08  
**Topic:** Download Acceleration, Live Visual Progress, and Edge Case Resilience  
**Target:** `scripts/player-toolbar.lua`, `tools/download_worker.py`, `scripts/modules/stream_policy.lua`, `deploy/registry.py`

---

## 1. Overview & Goals

This specification defines the architecture for high-speed multi-connection video downloading and in-player live progress tracking within MPV, resolving UI limitations, network throttling risks, and Windows IPC constraints.

### Key Goals
1. **16-Thread Multi-Connection Download Speed**: Saturate available bandwidth using `aria2c` 16-connection parallel chunk downloading for progressive single-file media (`txxx.com`, Twitter/X, Vimeo, direct MP4s) and 6 concurrent fragments for segmented streams (YouTube, Twitch, DASH/HLS).
2. **In-Player Live Progress UI (Design A - Micro Bottom Bar & Live Badge)**: Real-time percentage badge (`15%` → `45%` → `85%` → `OK` / `SAVED`), dynamic bottom track progress bar on the toolbar button, and detailed speed/ETA tooltips without console window popups.
3. **Robust Edge Case & Risk Mitigation**:
   - Strict `bof` & `eof` verification before allowing `dump-cache` to eliminate truncated video exports.
   - Concurrency moderation (`--concurrent-fragments 6`, `--retry-wait 2`, `-m 3`) to prevent HTTP 429 rate limits.
   - Atomic `.tmp` + `os.replace()` state swapping to eliminate Windows file-locking sharing violations (`EBUSY`).
   - Non-destructive UOSC integration supporting both stock UOSC and patched micro-bar rendering.
   - Complete header and cookie propagation (`user-agent`, `referer`, `cookie`) to `yt-dlp` and `aria2c`.
   - Standard dependency management via `deploy/registry.py` and Windows `winget`.

---

## 2. Technical Risk Mitigations & Architecture

### 2.1. Mitigating `dump-cache` Truncation Risk
* **Problem**: If video size exceeds `demuxer-max-bytes` or `demuxer-max-back-bytes` (800MiB), MPV only holds a sliding window. Triggering `dump-cache` would output an unplayable or truncated video missing the beginning or end.
* **Specification**:
  - In `stream_policy.lua` (`analyze_cache_coverage`):
    - Must inspect `cache_state.bof` (Beginning Of File) and `cache_state.eof` (End Of File).
    - If `bof ~= true` or `eof ~= true`, or if `seekable-ranges` has gaps or fails $\ge 99.5\%$ duration coverage, mark `is_complete = false`.
    - In `player-toolbar.lua`: Only invoke `dump-cache` when `is_complete == true`. Otherwise, immediately fall back to the background download worker to ensure the user receives a 100% complete video.

### 2.2. Concurrency Moderation & HTTP 429 Prevention
* **Problem**: 16 concurrent fragment requests on YouTube or Vimeo CDNs trigger HTTP 429 (Too Many Requests), connection throttling, and TCP resets.
* **Specification**:
  - For segmented DASH/HLS streams: Set `--concurrent-fragments 6` (safe sweet spot maximizing bandwidth without triggering CDN rate-limiting).
  - For direct/progressive MP4 streams via `aria2c`:
    - Keep 16 connections: `-x 16 -s 16 -k 1M -j 16`.
    - Add resilience flags: `--retry-wait=2 --max-tries=3 --max-file-not-found=3 --timeout=15`.

### 2.3. Windows Atomic State Swapping (No File Locking / EBUSY)
* **Problem**: Writing directly to `%TEMP%/mpv_dl_state_<id>.json` every 250ms collides with Lua `io.open()` read attempts on Windows NTFS, causing `Permission Denied` / sharing violation crashes.
* **Specification**:
  - In `tools/download_worker.py`:
    - Status updates are written to `f"{state_path}.tmp"`.
    - Atomically rename using `os.replace(f"{state_path}.tmp", state_path)` (guaranteed atomic on Windows via `MoveFileExW` with `MOVEFILE_REPLACE_EXISTING`).
  - In `scripts/player-toolbar.lua`:
    - The JSON file read routine is wrapped in `pcall()`.
    - If a transient read collision occurs, it silently ignores the tick and waits for the next 250ms interval.

### 2.4. UOSC Core Non-Destructive Design
* **Problem**: Directly editing `uosc/elements/Button.lua` complicates future upstream updates and breaks if UOSC is reinstalled.
* **Specification**:
  - **Stock UOSC Fallback**: `player-toolbar.lua` natively updates `badge` (`45%`, `OK`, `SAVED`) and `tooltip` (`Downloading: 45% (14.2 MB/s • ETA 00:06 • 16 threads)`), which work out of the box with zero changes to UOSC.
  - **Micro Bottom Bar Enhancer**: Provide an idempotent patcher (`tools/patch_uosc_button.py`) that safely adds `progress` support to `Button.lua` if present, without altering base control logic. If unpatched, the toolbar functions cleanly without errors.

### 2.5. Full Authentication & Header Passthrough
* **Problem**: Protected streams (e.g. adult platforms, Twitter/X, Vimeo) require active session cookies, specific User-Agents, and referer headers to avoid 401/403 errors.
* **Specification**:
  - In `scripts/player-toolbar.lua`:
    - Extract `user-agent = mp.get_property('user-agent')`
    - Extract `referrer = mp.get_property('referrer')`
    - Extract `cookies = mp.get_property('cookies')` (or `cookies-file`)
    - Pass headers in worker arguments.
  - In `tools/download_worker.py`:
    - Pass to `yt-dlp`: `--user-agent <ua>`, `--referer <ref>`, `--add-header "Cookie:<val>"`.
    - Forward to `aria2c`: `--header="User-Agent: <ua>"`, `--header="Referer: <ref>"`, `--header="Cookie: <val>"`.

---

## 3. Component Design & Implementation Details

### 3.1. `deploy/registry.py` (Standard Dependency Registration)
Add `aria2` to the package registry:
```python
"aria2": {
    "windows": {"method": "winget", "id": "aria2.aria2"},
    "arch":    {"method": "pacman", "pkg": "aria2"},
    "ubuntu":  {"method": "apt",    "pkg": "aria2"},
    "fedora":  {"method": "dnf",    "pkg": "aria2"},
    "macos":   {"method": "brew",   "pkg": "aria2"},
    "verify":  ["aria2c", "--version"],
}
```

### 3.2. `tools/download_worker.py` (Headless Background Worker)
Command line interface:
`python tools/download_worker.py --state-file <path> --url <url> --output <template> [--audio-only] [--format <fmt>] [--user-agent <ua>] [--referer <ref>] [--cookies <cookies>]`

**Worker Behavior**:
1. Checks for `aria2c` binary in `PATH` or `C:\Program Files\mpv\aria2c.exe` or `%LOCALAPPDATA%\Microsoft\WinGet\Links\aria2c.exe`.
2. Assembles `yt-dlp` arguments:
   - For progressive MP4 / single files: if `aria2c` is present, uses `--downloader aria2c --downloader-args "aria2c:-x 16 -s 16 -k 1M -j 16 --retry-wait=2 --max-tries=3"`.
   - For HLS/DASH or if `aria2c` is absent: uses `--concurrent-fragments 6`.
   - Headers: passes `--user-agent`, `--referer`, and cookie headers.
   - Progress streaming: `--newline --progress`.
3. Runs subprocess with `capture_stdout=PIPE`, reads lines as they arrive.
4. Regex parses:
   - Percentage: `r'\[download\]\s+([0-9.]+)%'`
   - Speed: `r'at\s+([^\s]+)'`
   - ETA: `r'ETA\s+([0-9:]+)'`
5. Writes atomic JSON updates to state file:
   ```json
   {
     "status": "downloading",
     "percent": 45.2,
     "percent_int": 45,
     "speed": "14.2MiB/s",
     "eta": "00:06",
     "threads": 16
   }
   ```
6. On exit, writes `{"status": "completed", "code": 0}` or `{"status": "error", "message": "<err>"}`.

### 3.3. `scripts/modules/stream_policy.lua`
- Update `analyze_cache_coverage` to enforce `bof == true` and `eof == true` before returning `is_complete = true`.
- Add `build_worker_args(target_url, output_path, is_audio_only, ytdl_format, headers, session_id)` helper.

### 3.4. `scripts/player-toolbar.lua`
- `start_download`:
  1. Checks `analyze_cache_coverage`. If complete with `bof` and `eof`, instant export via `dump-cache` (badge `SAVED`, 0 MB downloaded).
  2. If unbuffered, generates session ID, creates state file path in `%TEMP%`, and launches `tools/download_worker.py` via `mp.command_native_async({name = 'subprocess', playback_only = false, ...})`.
  3. Starts periodic timer (250ms) polling the state file with `pcall`.
  4. Calls `publish_download()` with `{ progress = pct / 100, badge = pct .. '%', tooltip = ... }`.
  5. On completion, sets badge to `OK` for 4 seconds, cleans up timer and temp files.

---

## 4. Verification & Testing Plan

1. **Unit Tests**:
   - `tests/lua/test_stream_policy.lua`: Test `bof`/`eof` validation in `analyze_cache_coverage` (verify missing BOF/EOF correctly rejects cache dumping).
   - `tests/test_download_worker.py`: Test `download_worker.py` argument parsing, regex progress extraction, atomic `.tmp` state file replacement, and header forwarding.
2. **Integration Verification**:
   - Install `aria2` via `winget install --id aria2.aria2 -e --accept-package-agreements --accept-source-agreements`.
   - Test live download with `txxx.com` and YouTube streams.
   - Verify 16-connection speed, live button percentage badge progression (`12%` → `45%` → `85%` → `OK`), and absence of any sharing violation errors.
