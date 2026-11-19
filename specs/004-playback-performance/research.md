# Research: Playback Performance — Display Sync Fixes

**Date**: 2026-04-26
**Status**: Implemented — verified on Linux/Wayland 2026-11-19; Windows verification pending. Q1–Q3 and Q5 are the author's working notes, not cited sources; Q4 is checked against the mpv manual; Q6 is from measurement.
**Spec**: [spec.md](spec.md)

## Research Questions & Findings

### Q1: Why does `tscale=oversample` produce high jitter at 143.981 Hz?

**Finding**: `oversample` uses a nearest-neighbor-like approach to
temporal scaling. At exactly integer VSync ratios (e.g., 120/24 = 5),
it works perfectly. But at 143.981/23.976 ≈ 6.006, the 0.006
fractional remainder means every ~167 frames, one display refresh
must accommodate a "partial" video frame. `oversample` handles this
by snapping to the nearest whole frame, creating a sharp timing
discontinuity that registers as jitter and delayed frames.

**Source**: mpv manual, community testing, GitHub issues (no links recorded; verify against the mpv manual before relying on them)

**Status (2026-11-19)**: not confirmed. The effective runtime `tscale`
is `oversample` (set by `scripts/smart_motion.lua`), and the full-config
Linux runs with it show delayed 0 and drop 0. `smart_motion.conf`
records that `oversample` and `linear` measure the same in mpv's
telemetry.

### Q2: What temporal scalers reduce jitter at non-integer ratios?

**Finding**: `linear` is the recommended alternative. It blends
frames linearly during the partial overlap, smoothly absorbing the
fractional drift. The visual impact is minimal — a barely
perceptible softness during the sub-frame blend, noticeable only
in motion freeze-frames. Other options (`mitchell`, `catmull_rom`)
over-smooth and create soap-opera effect. `sphinx` is niche and
unreliable.

| Scaler | Sharpness | Jitter Tolerance | Recommendation |
|--------|-----------|------------------|----------------|
| oversample | Highest | Worst at non-integer | ❌ Previous default (still selectable at runtime via `Alt+t`) |
| linear | High | Good | ✅ Proposed |
| mitchell | Medium | Good | ❌ Too smooth |
| catmull_rom | Medium | Good | ❌ Too smooth |
| sphinx | Variable | Unknown | ❌ Unreliable |

### Q3: Can `display-fps-override` fix Wayland estimation instability?

**Finding**: Yes, but with caveats. `display-fps-override` (called
`override-display-fps` before mpv 0.37) forces
mpv to use a fixed refresh rate instead of its runtime estimation.
On Wayland, the estimation is broken due to inconsistent compositor
presentation feedback. Forcing the correct rate (143.981) stabilizes
display-resample calculations.

**Caveats**:
- Should NOT be used globally — only as a workaround for broken
  Wayland timing
- Can conflict with VRR/Adaptive Sync if enabled
- Should be gated behind a conditional profile that only activates
  on Wayland with ~144 Hz displays
- May become unnecessary when KDE Plasma improves its presentation
  feedback protocol

### Q4: What does `video-timing-offset` control?

**Finding** (mpv manual, `--video-timing-offset`): it controls how long
before the display target time a frame is rendered (default 0.050). It
"applies only to audio timing modes (e.g. `--video-sync=audio`). In
other modes (`--video-sync=display-...`), video timing relies on vsync
blocking, and this option is not used."

So the template's `video-timing-offset = 0.01` has no effect under
`display-resample`, the default mode. It only matters in the deployer's
VRR mode (`video-sync=audio`).

### Q5: Does Adaptive Sync / VRR conflict with display-resample?

**Finding**: Yes, confirmed. When VRR is active, the display adapts
its refresh rate to match the content. `display-resample` fights
this by trying to match the video to a fixed display rate. The two
mechanisms conflict, causing worse results than either alone.
Correct approach for VRR: use `video-sync=audio` and let the
display adapt. The template does this through the deployer's
`--display-mode vrr` (`_resolve_display_mode`). The `[protocol.https]`
profile does NOT use `video-sync=audio`: it keeps `display-resample`
on purpose, because 30 fps at 144 Hz under `video-sync=audio` has a
non-integer 4.8 cadence (micro-judder), and its large cache handles
network jitter.

### Q6: Is `vsync-jitter` a good pass criterion?

**Finding** (measured 2026-11-19, KDE Wayland): no. Anime4K A+A raises
`vsync-jitter` to about 0.44 while `vo-delayed-frame-count` stays 0.
`vsync-jitter` is the spread of the reported flip-to-flip intervals;
the delayed counter counts frames that land on the wrong vsync. The
panel only shows frames at vsyncs, so the delayed, mistimed and drop
counters reflect what is on screen. `vsync-jitter` is recorded but is
not a pass criterion.

## All NEEDS CLARIFICATION: Resolved

No unresolved questions remain for the implemented fixes, except that
`smart_motion.lua` (runtime `tscale`, `video-sync`, `interpolation`) is
not covered by any spec. Pixel format
/ codec correlation (spec Cause 3, FR-002) is explicitly deferred as
"needs further investigation".
