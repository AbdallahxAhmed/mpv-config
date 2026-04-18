# Implementation Plan: MPV Playback Keys & Config Tuning

**Feature**: [spec.md](file:///home/abdallahx/Desktop/mpv-config/specs/002-mpv-playback-keys/spec.md)  
**Branch**: `002-mpv-playback-keys`  
**Created**: 2026-04-19

---

## Technical Context

### Current State

The project uses two template files that the deployer patches and deploys:
- `config/mpv.conf.template` → `~/.config/mpv/mpv.conf`
- `config/input.conf.template` → `~/.config/mpv/input.conf`

Script-specific settings live in `config/script-opts/*.conf` and are copied as-is.

### Keybinding Conflict Analysis

Extracted from source code — all hardcoded default bindings across installed scripts:

| Key | Script | Binding Name | Action |
|-----|--------|--------------|--------|
| `h` | **memo** | `memo-history` | Open watch history |
| `h` | **sponsorblock** | `upvote_segment` | Upvote SponsorBlock segment |
| `H` | **sponsorblock** | `downvote_segment` | Downvote SponsorBlock segment |
| `g` | **sponsorblock** | `set_segment` | Mark segment start/end |
| `G` | **sponsorblock** | `submit_segment` | Submit segment to API |
| `n` | **autosubsync** | `autosubsync-menu` | Open subtitle sync menu |
| `RIGHT` | **evafast** | `evafast` | Hybrid fast-forward |

**Conflict**: `h` is bound by both memo and sponsorblock.

### Resolution Strategy

mpv's `input.conf` has **higher priority** than script-internal `mp.add_key_binding()` defaults. When a key is defined in `input.conf` via `script-binding <script-name>/<binding-name>`, it overrides the script's built-in default. This means:

1. We do **NOT** need to modify any Lua script source code.
2. We do **NOT** need to patch `script-opts/memo.conf` (it has no keybinding options).
3. We only need to add explicit `input.conf` entries that re-assign conflicting keys.

SponsorBlock also registers named bindings (`sponsorblock_set_segment`, `sponsorblock_upvote`, etc.) with `nil` as the default key — these are already conflict-free. The conflict comes only from the convenience aliases (`g`, `h`, `H`, `G`) hardcoded alongside them.

---

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Terminology Separation | ✅ Pass | All changes are in `config/` templates (mpv config), not in `deploy/` automation code |
| II. OS Parity | ✅ Pass | `mpv.conf` and `input.conf` settings are platform-agnostic. Screenshot path uses `~/` which mpv expands correctly on all OS |
| III. Fish Environment | ✅ N/A | No shell script changes |
| IV. CLI Aesthetics | ✅ N/A | No CLI/UI changes — config-only feature |

---

## Proposed Changes

### Component 1: Keybinding Conflict Resolution

#### [MODIFY] [input.conf.template](file:///home/abdallahx/Desktop/mpv-config/config/input.conf.template)

**Strategy**: Override conflicting defaults by explicitly assigning non-conflicting keys in `input.conf.template`.

**Proposed Keybinding Map (complete, conflict-free)**:

| Key | Action | Script | Rationale |
|-----|--------|--------|-----------|
| `CTRL+1..6` | Anime4K modes A/B/C/A+A/B+B/C+A | *(existing)* | Unchanged |
| `CTRL+0` | Clear shaders | *(existing)* | Unchanged |
| `F1` | Screenshot (video only) | mpv built-in | Unchanged |
| `F2` | Screenshot (with subs) | mpv built-in | Unchanged |
| `F3` | Toggle deband | mpv built-in | Unchanged |
| `F4` | Toggle interpolation | mpv built-in | Unchanged |
| `F5` | Cycle audio track | mpv built-in | Unchanged |
| `F6` | Cycle subtitle track | mpv built-in | Unchanged |
| `F7` | Toggle subtitle visibility | mpv built-in | Unchanged |
| `F8` | Dynamic audio normalizer | mpv built-in | Unchanged |
| `h` | **Memo: watch history** | memo | **Keep** — most frequently used |
| `g` | Set SponsorBlock segment | sponsorblock | Keep (rarely used, power-user) |
| `G` | Submit SponsorBlock segment | sponsorblock | Keep (rarely used, power-user) |
| `B` | **SponsorBlock: upvote** | sponsorblock | **Moved from `h`** — `B` for "Block/vote" |
| `SHIFT+B` | **SponsorBlock: downvote** | sponsorblock | **Moved from `H`** — consistent with `B` |
| `n` | Autosubsync menu | autosubsync | Unchanged |
| `RIGHT` | Evafast | evafast | Unchanged |

**Implementation**: Add these lines to `input.conf.template`:

```
# ─── Conflict Resolution: SponsorBlock voting moved from h/H to B/Shift+B ───
B    script-binding sponsorblock_upvote
Shift+B  script-binding sponsorblock_downvote
h    script-binding memo-history
```

This approach:
- Keeps `h` for memo (most common use — watch history)
- Moves SponsorBlock voting to `B` / `Shift+B` (mnemonic: "Block")
- Does not touch `g`/`G` (no conflict — memo doesn't use them)

---

### Component 2: Lossless Screenshot Settings

#### [MODIFY] [mpv.conf.template](file:///home/abdallahx/Desktop/mpv-config/config/mpv.conf.template)

Add the following block after the shader cache section:

```ini
# ─── Screenshot Settings ─────────────────────────────────────────
screenshot-format=png
screenshot-png-compression=0
screenshot-high-bit-depth=yes
screenshot-directory=~/Pictures/mpv-screenshots
screenshot-template="%F_%P"
```

| Setting | Value | Rationale |
|---------|-------|-----------|
| `screenshot-format` | `png` | Lossless, universally supported |
| `screenshot-png-compression` | `0` | Fastest save (no compression delay), file size is secondary to speed |
| `screenshot-high-bit-depth` | `yes` | Preserve 10-bit color from HEVC/HDR content |
| `screenshot-directory` | `~/Pictures/mpv-screenshots` | Fixed, organized location. `~/` is expanded by mpv on all platforms |
| `screenshot-template` | `%F_%P` | `%F` = filename without extension, `%P` = timestamp (HH:MM:SS.mmm). Produces: `Dr.Stone_S04E25_00-07-32.621.png` |

---

### Component 3: YouTube Optimization Profile

#### [MODIFY] [mpv.conf.template](file:///home/abdallahx/Desktop/mpv-config/config/mpv.conf.template)

Add a conditional auto-profile for streaming URLs. This profile activates **only** for `https://` URLs, keeping local file playback completely unaffected.

```ini
# ─── YouTube / Streaming Optimization ────────────────────────────
[protocol.https]
profile-desc="Optimized cache and format for YouTube/streaming"

# Format: 1080p max, highest video bitrate, best audio (opus > aac)
ytdl-format=bestvideo[height<=?1080][vcodec!~='vp0?9']+bestaudio[acodec=opus]/bestvideo[height<=?1080]+bestaudio/best

# Aggressive read-ahead cache for fast seeking
cache=yes
demuxer-max-bytes=800M
demuxer-max-back-bytes=200M
demuxer-readahead-secs=300

# Precise seeking for instant response
hr-seek=yes
hr-seek-framedrop=no

# Disable interpolation for streaming (reduces decode overhead)
interpolation=no
video-sync=audio

[protocol.http]
profile=protocol.https
```

**Value Rationale**:

| Setting | Value | Why |
|---------|-------|-----|
| `ytdl-format` | `bestvideo[height<=?1080][vcodec!~='vp0?9']+bestaudio[acodec=opus]/...` | Excludes VP9 on hardware without native VP9 decode (NVIDIA nvdec handles H.264/HEVC better). Prefers Opus audio (higher quality at lower bitrate). Falls back gracefully. |
| `demuxer-max-bytes` | `800M` | Buffers ~5-8 minutes of 1080p ahead. Large enough for instant forward-seeking within the buffered window. |
| `demuxer-max-back-bytes` | `200M` | Keeps ~1-2 minutes of already-played content in memory for instant backward-seeking. |
| `demuxer-readahead-secs` | `300` | Tells the demuxer to read up to 5 minutes ahead when bandwidth permits. Fills the buffer aggressively during playback. |
| `hr-seek` | `yes` | High-resolution seek: seeks to exact frame, not just nearest keyframe. Eliminates the "blurry skip" feeling. |
| `hr-seek-framedrop` | `no` | Renders every frame during seek instead of dropping. Smoother seeking experience. |
| `interpolation=no` | Streaming only | Interpolation adds decode overhead; unnecessary for streaming where frame timing is already approximate. |
| `video-sync=audio` | Streaming only | Simpler sync model for streaming, avoids frame timing issues caused by network jitter. |

---

## Verification Plan

### Manual Testing

1. **Keybinding test**: Open a video, press `h` → memo history must open. Press `B` → SponsorBlock upvote must fire. Press `g` → segment marker must appear. Confirm no key triggers two actions.

2. **Screenshot test**: Press `F1` during playback → check `~/Pictures/mpv-screenshots/` for a PNG file. Verify filename matches `VideoName_HH-MM-SS.mmm.png`. Verify file is lossless PNG with correct bit depth.

3. **YouTube seeking test**:
   ```bash
   mpv "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
   ```
   - Seek forward 30s → playback should resume within 2 seconds.
   - Seek backward to buffered position → should resume instantly.
   - Verify `demuxer-max-bytes` is active: press `i` twice to see cache stats.

4. **Local file regression test**: Play a local file and verify cache settings are NOT the streaming values (demuxer-max-bytes should be the default 500M, not 800M).

### Automated Verification

Run the existing verifier:
```bash
python3 setup.py --verify
```

---

## Files Changed Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `config/input.conf.template` | MODIFY | Add conflict-resolution keybindings for SponsorBlock voting |
| `config/mpv.conf.template` | MODIFY | Add screenshot settings block + YouTube streaming profile |
