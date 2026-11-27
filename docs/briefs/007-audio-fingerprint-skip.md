# Brief 007 — Audio-fingerprint intro/outro skip

Status: **agreed plan, ready for spec-kit** (`/specify` → `/plan` → `/tasks`).
Agreed with the user on 2026-11-27. Builds on `46ec084` (chapter detection
in `scripts/modules/skip_detect.lua`, `/` manual skip).

This brief is the input for spec 007. It fixes the *what* and the decisions
already taken; the spec/plan decide the *how* in detail. Where this brief
says "must", it is a user decision — do not re-open it in the spec.

---

## 1. Problem

SmartSkip only auto-skips **chapters**. Since `46ec084` it recognises OP/ED
chapters by name and by length, but a large part of the user's library has
**no chapters at all** (most weekly web releases). For those files nothing is
skipped automatically; the only tool is `/` (fast-forward to next silence).

## 2. Idea

Inside one series the OP (and ED) is the **same audio recording** in every
episode. Fingerprint the audio of the start and the end of episodes, find the
long stretch two episodes share, and that stretch is the OP/ED — with exact
start/end times in both files. Same principle as Jellyfin's Intro Skipper
(intro searched in the first 25 % or first 10 min of an episode, whichever is
smaller, 15 s – 2 min long).

## 3. Decisions taken (do not re-open)

| # | Decision | Choice |
|---|----------|--------|
| D1 | What happens when an OP/ED is detected | **Auto-skip after the existing 3 s SmartSkip countdown** (Esc cancels, Enter skips now) — same UX as chapter auto-skip today |
| D2 | Scope of v1 | **OP + ED**. Preview / recap are out of scope for v1 |
| D3 | When analysis runs | **Current episode first, then the rest of the folder in the background** |
| D4 | Weekly-airing shows | Must work when only the new episode is on disk (old ones deleted). Solved by remembered fingerprints + OP/ED templates (§5.3) |
| D5 | Fingerprint engine | **Own Philips-style fingerprint in numpy**, not Chromaprint. Reason: Arch's `ffmpeg` is very likely built without chromaprint (circular dependency chromaprint ↔ ffmpeg) and it is unverified whether the Windows ffmpeg the deployer installs has it. One code path, identical on Windows and CachyOS. Validated in the spike (§9) |
| D6 | Sources | **Local files only.** Streams/URLs are never analysed |
| D7 | Priority vs chapters | Chapter detection (names, then length — `skip_detect.lua`) wins when it finds the OP/ED. Fingerprints cover files where chapters say nothing. When both exist and the fingerprint boundary is within 3 s of a chapter boundary, snap to the chapter boundary |

## 4. User-visible behaviour (acceptance level)

1. Play episode N of a show whose episode N−1 (or N+1) was ever played or is
   in the same folder → the OP auto-skips with the normal countdown, OSD reads
   e.g. `▷ Auto-Skip in "3": Opening · audio`.
2. Same for the ED near the end of the episode.
3. Weekly show, only the new episode on disk, earlier episodes were played
   (and maybe deleted) on this machine → still skips (templates).
4. Brand-new show, first episode played, nothing else known → no skip (and
   no error). Episode 2 then skips.
5. OP changes in the second cour → the first new-OP episode may not skip;
   the episode after it does (self-healing, §5.3).
6. `>` inside a detected OP/ED jumps to its end. `/` keeps working as today.
7. `Ctrl+.` (auto-skip off) also disables fingerprint skips. `Alt+.` inside a
   detected segment takes it out of auto-skip for this file (same as for
   detected chapters today).
8. Movies (outside the episode-length window), clips, streams → nothing runs.
9. **Playback is never disturbed**: no stutter, no dropped frames, no audio
   glitch while analysis runs (the user's #1 priority for this repo).

## 5. Design

### 5.1 Fingerprint (validated in the spike, §9)

- Decode **audio only** with ffmpeg: `-vn -sn -dn`, mono, 5512 Hz, s16le to
  stdout. Head window = first `min(25 % of duration, 600 s)`; tail window =
  last 300 s (`-sseof -300`).
- Frames of 2048 samples, hop 512 (≈ 10.8 fingerprints/s), Hann window,
  power spectrum, 33 log-spaced bands 300–2000 Hz.
- 32 bits per frame: bit m = sign of
  `(E[n,m] − E[n,m+1]) − (E[n−1,m] − E[n−1,m+1])` on log band energy
  (Haitsma & Kalker). Stored as `uint32`.
- Size: ≈ 15 KiB per 6-minute window. Trivial to cache.

### 5.2 Matching

- Candidate offsets: histogram of exact 32-bit matches between the two
  sequences (inverted index), top ~40 offsets.
- For each candidate offset: per-frame bit error rate (popcount of XOR / 32),
  smoothed over 2 s; frames with smoothed BER < 0.30 are "same audio".
- Take the longest run with length 15–130 s. That run gives start/end in
  **both** files.
- OP is searched only in head windows, ED only in tail windows.
- Thresholds (0.30 BER, 2 s smoothing, 15–130 s) are spike values on
  synthetic audio — **must be tuned on the user's real library** (§8).

### 5.3 Memory: works for weekly shows (D4)

Everything is keyed by **file identity, not by the file still existing**:

- **Episode fingerprints**: every episode that is played (or scanned) keeps
  its head/tail fingerprints in the cache, even after the file is deleted.
  Episode N is compared with the remembered fingerprints of nearby episodes
  of the same series (same folder, and/or same normalised series name from
  the filename, e.g. `[Group] Show Name - 05 (1080p) [HASH].mkv` →
  `show name`).
- **Templates**: once an OP/ED is found, its fingerprint slice (~90 s, ~4 KiB)
  is saved as an OP/ED template. A new episode is first matched against the
  saved templates (milliseconds; spike: 1 ms) — this alone finds the OP in a
  fresh weekly episode with no other file on disk. Matching against *all*
  recent templates (not only the guessed series) is cheap and makes naming
  chaos harmless; cap the template store (e.g. 300 most recent).
- **Self-healing**: no template matches (new OP in cour 2) → fall back to
  pairwise with remembered neighbours → the new OP becomes a new template.
- File identity = file size + hash of the first 64 KiB + duration (moving or
  renaming a file must not trigger re-analysis).
- Cache dir: `$XDG_CACHE_HOME/mpv-config/skip/` (default `~/.cache/…`) on
  Linux, `%LOCALAPPDATA%\mpv-config\cache\skip\` on Windows. Never inside
  the repo, never inside `~~/` (the mpv config dir is deployer-managed).

### 5.4 Process model

- **Python helper** inside `src/mpv_config/` (e.g. `audio_skip/` package) +
  CLI subcommand (e.g. `mpv-config skip-scan <file|folder> --json`). Does
  decode, fingerprint, cache, matching. Prints one JSON result per file:
  `{"opening": {"start": 125.0, "end": 214.8, "source": "template|pair",
  "score": …} | null, "ending": … | null}`.
- **Lua side** (SmartSkip, via a module next to `skip_detect.lua`): on
  `file-loaded` for a local episode-length file, start the helper with
  `mp.command_native_async({name="subprocess", …})` — never blocking. When
  the JSON arrives, register the segments and arm a timer for the segment
  start (re-armed on seek; no per-frame polling). If the result arrives while
  already inside the OP, start the countdown immediately.
- **Background folder scan** (D3): after the current episode, the helper
  queues the other episodes in the folder (and the next playlist entry
  first). One ffmpeg at a time.
- **Priority**: helper and its ffmpeg run at low CPU **and low I/O priority**
  (Linux: `nice` + `ionice -c3`; Windows: `BELOW_NORMAL_PRIORITY_CLASS` /
  background mode). Abort the background scan when mpv quits (same
  ownership rules as other agent/helper processes: only kill what we spawned).
- **Interpreter**: the helper needs numpy, so it must run with the Python of
  the mpv-config install (the editable install / venv the deployer uses), not
  a random system `python`. The deployer must make that path known to the Lua
  side (e.g. a key in a deployer-managed script-opts file). Add `numpy` to
  `pyproject.toml` dependencies.
- **Audio track**: fingerprint the same audio language mpv is playing
  (`current-tracks/audio`): dual-audio releases must compare JP with JP.

### 5.5 SmartSkip integration

- Fingerprint segments are a new source next to chapter categories: same
  category names (`opening`, `ending`), same `skip=` list, same countdown,
  OSD, `Esc`/`Enter`, `Ctrl+.`, `Alt+.` behaviour.
- D7 ordering: chapter detection first; fingerprint only fills in what
  chapters did not find; snap to a chapter boundary within 3 s.
- `>` inside a segment → seek to segment end.
- Options in `SmartSkip.conf` (names indicative): `audio_skip=yes`,
  `audio_skip_scan_folder=yes`, `audio_skip_min=15`, `audio_skip_max=130`,
  `audio_skip_ber=0.30`, `audio_skip_snap=3`. Deployed configs are preserved,
  so every new option needs a Lua default.

## 6. Out of scope (v1)

Preview/recap detection · uosc "Skip Intro" button · black-frame or silence
analysis for credits · streams/URLs · sharing fingerprints between machines ·
movies' end credits.

## 7. Repo rules that apply (from the user's standing instructions)

- pathlib everywhere; `subprocess` with list args, never `shell=True`.
- CLI entry points catch exceptions and return proper exit codes.
- Never kill processes the user started; only the ones we spawned.
- No secrets, no hardcoded personal paths; keep the security checks before
  every commit.
- All tests headless and silent (`--no-audio --ao=null --vo=null
  --no-terminal --really-quiet`, no focus stealing) — the user watches videos
  while tests run.
- Python suites: `python -m unittest discover -s tests` (with the project
  venv, `PYTHONPATH=src`); Lua suites: `python tests/run_lua_tests.py`.
  New Lua suites under `tests/lua/test_*.lua` are picked up automatically.
- Commit on `main`, no feature branches; push only when the user says so;
  no `Co-Authored-By` lines.

## 8. Verification

1. **Unit (synthetic)**: generate episodes at test time with ffmpeg (shared
   OP/ED at different offsets, different encodes/bitrates, a different show
   as a negative) — same method as the spike. Assert boundaries within
   ±0.5 s and no match for the other show. Do not commit large media.
2. **Lua**: segment arming, re-arm on seek, countdown, `>`/`Esc`/`Alt+.`,
   chapter-vs-fingerprint priority and 3 s snapping, with a mocked `mp`.
3. **Real library (with the user)**, before calling v1 done:
   - a full season downloaded at once (folder scan path),
   - a weekly show where earlier episodes were deleted (template path),
   - a show whose OP changes mid-season (self-healing path),
   - one dual-audio release.
   Tune BER/smoothing/min-max on these; record the final values in the spec.
4. **Playback**: run the T014-style check (frame drops / delayed frames)
   while a background folder scan is running. Must stay at 0 drops.

## 9. Spike results (2026-11-27, sandbox CPU, synthetic audio)

Synthetic 23.5-min episodes: generated "dialogue" + per-episode BGM, the
same 90 s OP inserted at 2:05 / 0:00 / 0:40, the same ED near the end, each
episode encoded separately (AAC 128k / 96k / 64k), plus a different show.

| Check | Result |
|-------|--------|
| decode + fingerprint, head (352 s) + tail (300 s) | ≈ 1.3 s per episode |
| OP e01↔e02, e02↔e03, e01↔e03 | found, boundaries within ±0.2 s, length 89.6–90.0 s |
| ED, all pairs | found, length 90.1–90.3 s |
| e01 ↔ other show | no match (OP and ED) |
| OP template from e01, searched alone in e03 | found at 40.0 s, 1 ms |
| OP template in the other show | no match |
| pairwise match time | a few ms |

Real anime audio is harder (SFX or dialogue over the OP, TV-size vs full
versions, OP instrumentals reused as BGM) — hence the real-library tuning
step in §8.

Reference implementation used in the spike (starting point, not final code):

```python
SR, FRAME, HOP = 5512, 2048, 512          # ~10.8 fingerprints / second
FPS = SR / HOP

def decode(path, length=None, from_end=None):
    cmd = ["ffmpeg", "-v", "error", "-nostdin"]
    if from_end:
        cmd += ["-sseof", f"-{from_end}"]
    cmd += ["-i", path, "-vn", "-sn", "-dn", "-map", "0:a:0"]
    if length:
        cmd += ["-t", str(length)]
    cmd += ["-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

def fingerprint(x):
    n = 1 + (len(x) - FRAME) // HOP
    idx = np.arange(FRAME)[None, :] + HOP * np.arange(n)[:, None]
    spec = np.abs(np.fft.rfft(x[idx] * np.hanning(FRAME), axis=1)) ** 2
    freqs = np.fft.rfftfreq(FRAME, 1 / SR)
    edges = np.geomspace(300, 2000, 34)
    bands = np.stack([spec[:, (freqs >= edges[i]) & (freqs < edges[i + 1])].sum(1)
                      for i in range(33)], 1)
    e = np.log(bands + 1e-10)
    d = e[:, :-1] - e[:, 1:]
    bits = (d[1:] - d[:-1]) > 0                       # (n-1, 32)
    return np.packbits(bits, axis=1, bitorder="little").view(np.uint32).ravel()

POP = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)

def popcount(v):
    return POP[v.view(np.uint8)].reshape(-1, 4).sum(1)

def best_segment(a, b, min_len=15, max_len=130, ber=0.30, smooth=2.0):
    """Longest run where a[i] ~ b[i - off]. Returns (start_a, start_b, len, off) in s."""
    best, win = None, max(1, int(smooth * FPS))
    kernel = np.ones(win) / win
    pos = {}
    for j, v in enumerate(b):
        pos.setdefault(int(v), []).append(j)
    hist = {}
    for i, v in enumerate(a):
        for j in pos.get(int(v), ()):
            hist[i - j] = hist.get(i - j, 0) + 1
    for off in sorted(hist, key=hist.get, reverse=True)[:40]:
        i0, i1 = max(0, off), min(len(a), len(b) + off)
        if i1 - i0 < min_len * FPS:
            continue
        err = popcount(a[i0:i1] ^ b[i0 - off:i1 - off]) / 32.0
        ok = np.convolve(err, kernel, mode="same") < ber
        dif = np.diff(np.concatenate(([0], ok.astype(np.int8), [0])))
        for s, e in zip(np.where(dif == 1)[0], np.where(dif == -1)[0]):
            length = (e - s) / FPS
            if min_len <= length <= max_len and (best is None or length > best[2]):
                best = ((i0 + s) / FPS, (i0 + s - off) / FPS, length, off)
    return best
```
