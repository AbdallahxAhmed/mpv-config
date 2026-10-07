# Research: Playback Performance — Display Sync Fixes

**Date**: 2026-04-26
**Spec**: [spec.md](file:///c:/Users/Abdallah_Ahmed/Desktop/mpv_construct/mpv-config/specs/004-playback-performance/spec.md)

## Research Questions & Findings

### Q1: Why does `tscale=oversample` produce high jitter at 143.981 Hz?

**Finding**: `oversample` uses a nearest-neighbor-like approach to
temporal scaling. At exactly integer VSync ratios (e.g., 120/24 = 5),
it works perfectly. But at 143.981/23.976 ≈ 6.006, the 0.006
fractional remainder means every ~167 frames, one display refresh
must accommodate a "partial" video frame. `oversample` handles this
by snapping to the nearest whole frame, creating a sharp timing
discontinuity that registers as jitter and delayed frames.

**Source**: mpv manual, community testing, GitHub issues

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
| oversample | Highest | Worst at non-integer | ❌ Current |
| linear | High | Good | ✅ Proposed |
| mitchell | Medium | Good | ❌ Too smooth |
| catmull_rom | Medium | Good | ❌ Too smooth |
| sphinx | Variable | Unknown | ❌ Unreliable |

### Q3: Can `override-display-fps` fix Wayland estimation instability?

**Finding**: Yes, but with caveats. `override-display-fps` forces
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

**Finding**: Adjusts when mpv delivers frames relative to V-Sync.
Default is 0.050 (5% of frame time before V-Sync). A smaller value
(0.01) allows the frame to be delivered closer to the V-Sync
boundary, giving the GPU/compositor more time to process the frame.
This can reduce "delayed" frames when the rendering pipeline is
tight (Vulkan + gpu-next + shaders).

### Q5: Does Adaptive Sync / VRR conflict with display-resample?

**Finding**: Yes, confirmed. When VRR is active, the display adapts
its refresh rate to match the content. `display-resample` fights
this by trying to match the video to a fixed display rate. The two
mechanisms conflict, causing worse results than either alone.
Correct approach for VRR: use `video-sync=audio` and let the
display adapt. The current `[protocol.https]` profile already does
this correctly.

## All NEEDS CLARIFICATION: Resolved

No unresolved questions remain.
