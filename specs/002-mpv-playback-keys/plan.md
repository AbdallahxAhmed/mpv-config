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

Full audit of **every** hardcoded default binding across all 9 installed scripts:

| Key | Script | Binding Name | Action | Conflict? |
|-----|--------|--------------|--------|-----------|
| `h` | **memo** | `memo-history` | Open watch history | ⚠️ YES — same as sponsorblock |
| `h` | **sponsorblock** | `upvote_segment` | Upvote segment | ⚠️ YES — same as memo |
| `H` | **sponsorblock** | `downvote_segment` | Downvote segment | |
| `g` | **sponsorblock** | `set_segment` | Mark segment start/end | |
| `G` | **sponsorblock** | `submit_segment` | Submit segment | |
| `n` | **autosubsync** | `autosubsync-menu` | Open subtitle sync menu | ⚠️ YES — same as SmartSkip |
| `n` | **SmartSkip** | `cancel_autoskip_countdown` | Cancel autoskip countdown | ⚠️ YES — same as autosubsync |
| `Shift+n` | **SmartSkip** | `add_chapter` | Add chapter at position | |
| `Alt+n` | **SmartSkip** | `remove_chapter` | Remove current chapter | |
| `Ctrl+n` | **SmartSkip** | `write_chapters` | Save chapters to file | |
| `>` | **SmartSkip** | `smart_next` | Smart skip next | |
| `<` | **SmartSkip** | `smart_prev` | Smart skip prev | |
| `?` | **SmartSkip** | `silence_skip` | Trigger silence skip | |
| `Ctrl+.` | **SmartSkip** | `toggle_autoskip` | Toggle autoskip | |
| `Alt+.` | **SmartSkip** | `toggle_category_autoskip` | Toggle category autoskip | |
| `Ctrl+RIGHT` | **SmartSkip** | `chapter_next` | Next chapter | |
| `Ctrl+LEFT` | **SmartSkip** | `chapter_prev` | Previous chapter | |
| `RIGHT` | **evafast** | `evafast` | Hybrid fast-forward | |

**Conflicts found: 2**
1. `h` → memo vs sponsorblock
2. `n` → autosubsync vs SmartSkip (cancel_autoskip_countdown)

### Resolution Strategy

mpv's `input.conf` has **higher priority** than script-internal `mp.add_key_binding()` defaults. SmartSkip uses `script-opts/SmartSkip.conf` for its keybinds, so we fix that conflict there.

1. `input.conf.template` — override memo/sponsorblock `h` conflict
2. `script-opts/SmartSkip.conf` — change `cancel_autoskip_countdown_keybind` from `["esc", "n"]` to `["esc"]` (remove `n`)

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

**Strategy**: Override conflicting defaults by explicitly assigning non-conflicting keys in `input.conf.template`. Design keys to be **intuitive** — each key is a mnemonic for its action.

**Complete Keybinding Reference (conflict-free, intuitive)**:

```
┌─────────────────────────────────────────────────────────────────┐
│                    MPV Keybinding Quick Reference                │
├─────────────┬───────────────────────────────────────────────────┤
│             │  🎨 Anime4K Shaders (CTRL + number)              │
│ CTRL+1      │  Mode A (Sharp)                                  │
│ CTRL+2      │  Mode B (Soft)                                   │
│ CTRL+3      │  Mode C (Denoise)                                │
│ CTRL+4      │  Mode A+A (Ultra Sharp)                          │
│ CTRL+5      │  Mode B+B (Ultra Soft)                           │
│ CTRL+6      │  Mode C+A (Denoise + Sharp)                      │
│ CTRL+0      │  Clear all shaders                               │
├─────────────┼───────────────────────────────────────────────────┤
│             │  📸 Screenshots & Display (F-keys)               │
│ F1          │  Screenshot (video only, no subs)                │
│ F2          │  Screenshot (with subtitles)                     │
│ F3          │  Toggle deband filter                            │
│ F4          │  Toggle interpolation (motion smoothing)         │
│ F5          │  Cycle audio track                               │
│ F6          │  Cycle subtitle track                            │
│ F7          │  Show/hide subtitles                             │
│ F8          │  Night mode (normalize loud audio)               │
├─────────────┼───────────────────────────────────────────────────┤
│             │  📜 Scripts — Everyday (single letter)           │
│ h           │  History — open watch history (memo)             │
│ n           │  Subtitle syNc menu (autosubsync)                │
│ RIGHT       │  Fast-forward (evafast)                          │
├─────────────┼───────────────────────────────────────────────────┤
│             │  ⏭️  SmartSkip (>, <, ?, Ctrl/Shift/Alt+N)       │
│ >           │  Smart next (skip intro/outro/silence)           │
│ <           │  Smart previous                                  │
│ ?           │  Trigger silence skip                            │
│ Ctrl+.      │  Toggle autoskip on/off                          │
│ Alt+.       │  Toggle category autoskip                        │
│ Ctrl+RIGHT  │  Next chapter                                    │
│ Ctrl+LEFT   │  Previous chapter                                │
│ Shift+n     │  Add chapter at current position                 │
│ Alt+n       │  Remove current chapter                          │
│ Ctrl+n      │  Save chapters to file                           │
├─────────────┼───────────────────────────────────────────────────┤
│             │  🚫 SponsorBlock (B = Block)                     │
│ g           │  Mark segment start/end                          │
│ G           │  Submit segment to SponsorBlock API              │
│ B           │  Upvote segment (👍 = B for Block)               │
│ Shift+B     │  Downvote segment (👎)                           │
└─────────────┴───────────────────────────────────────────────────┘
```

**Why these choices are intuitive**:
- **`h` = History** — mnemonic, most used daily feature
- **`n` = syNc** — already established, stays for autosubsync
- **`B` = Block** — SponsorBlock voting, `B` for "Block" is obvious
- **`>` / `<`** — forward/backward arrows are natural for skip
- **F-keys** — system-level functions, like a "function row" on a keyboard
- **CTRL+number** — shader presets, like preset slots on audio equipment
- **SmartSkip** uses `n`-family (`Shift+n`, `Alt+n`, `Ctrl+n`) — all chapter operations logically grouped

**Implementation in `input.conf.template`**:

```
# ─── Script Keybindings (conflict-free) ──────────────────────────

# History (memo) — h = History
h    script-binding memo-history

# SponsorBlock voting — B = Block (moved from h/H to avoid memo conflict)  
B    script-binding sponsorblock_upvote
Shift+B  script-binding sponsorblock_downvote

# Subtitle sync (autosubsync) — n = syNc
n    script-binding autosubsync-menu
```

#### [MODIFY] [SmartSkip.conf](file:///home/abdallahx/Desktop/mpv-config/config/script-opts/SmartSkip.conf)

Remove `n` from SmartSkip's cancel countdown keybind (conflicts with autosubsync's `n`):

```diff
-cancel_autoskip_countdown_keybind=["esc", "n"]
+cancel_autoskip_countdown_keybind=["esc"]
```

`esc` alone is sufficient and more intuitive for "cancel"

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
| `config/input.conf.template` | MODIFY | Add conflict-resolution keybindings (`h`→memo, `B`→sponsorblock) |
| `config/mpv.conf.template` | MODIFY | Add screenshot settings block + YouTube streaming profile |
| `config/script-opts/SmartSkip.conf` | MODIFY | Remove `n` from cancel_autoskip to resolve autosubsync conflict |
