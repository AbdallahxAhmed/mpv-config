# Implementation Plan: Playback Performance — Display Sync Fixes

**Branch**: `004-playback-performance` | **Date**: 2026-04-26 | **Spec**: [spec.md](file:///c:/Users/Abdallah_Ahmed/Desktop/mpv_construct/mpv-config/specs/004-playback-performance/spec.md)

## Summary

Fix display-resample frame timing jitter on both Windows (Vulkan)
and Linux (KDE Plasma 6.6.4 Wayland). The primary cause is the
`display-resample` + `tscale=oversample` combination struggling
with the non-integer VSync ratio of 143.981/23.976 ≈ 6.006, producing
high jitter (0.8–0.9 on Windows, 0.4 on Linux) and excessive delayed
frames. A secondary Linux-specific cause is unstable Wayland
presentation feedback making the estimated refresh rate variable.

## Technical Context

**Language/Version**: mpv configuration (INI-like format), Lua profile conditions
**Primary Dependencies**: mpv 0.37+, gpu-next VO, Vulkan GPU API
**Target Platform**: Windows 10/11 + Linux (KDE Plasma 6.6.4 Wayland)
**Project Type**: Configuration file (no code — config/ directory only)
**Constraints**: Constitution Principle I (Boundary Separation) — changes in `config/` only

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Boundary Separation | ✅ PASS | All changes in `config/mpv.conf.template` only |
| II. Cross-Platform Parity | ✅ PASS | Fix addresses both Windows and Linux |
| III. Dependency Classification | ✅ N/A | No dependency changes |
| IV. Shell Compatibility | ✅ N/A | No shell script changes |
| V. Aesthetic CLI UX | ✅ N/A | No UI changes |
| VI. User Customization | ✅ PASS | Changes are additive to existing profiles |
| VII. Idempotent Operations | ✅ N/A | No installer changes |

## Project Structure

### Documentation (this feature)

```text
specs/004-playback-performance/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 research findings
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code Changes

```text
config/
└── mpv.conf.template    # ONLY file modified
```

## Phase 0: Research Findings

### R1 — `tscale=oversample` Behavior at Non-Integer Ratios

**Decision**: Replace `tscale=oversample` with `tscale=linear` in
both `[live-action]` and `[anime]` profiles.

**Rationale**: `oversample` is the sharpest temporal scaler but
produces the worst jitter at non-integer VSync ratios. At
143.981/23.976 ≈ 6.006, the 0.006 fractional remainder means every
~167 frames, the oversample algorithm must absorb an extra timing
quantum. `oversample` handles this poorly because it uses a
nearest-neighbor-like approach that creates sharp timing
discontinuities. `linear` uses linear blending which absorbs the
fractional drift smoothly, trading a barely perceptible softness
for dramatically reduced jitter and delayed frames.

**Alternatives considered**:
- `sphinx`: Too niche, inconsistent results, requires manual tuning
- `mitchell`/`catmull_rom`: Over-smooth, soap opera effect
- `box`: Worst visual quality
- Keep `oversample`: Unacceptable jitter on both platforms

### R2 — `override-display-fps` for Wayland Estimation Fix

**Decision**: Add `override-display-fps=143.981` via a conditional
Linux/Wayland profile in the template.

**Rationale**: On KDE Plasma Wayland, mpv's estimated refresh rate
is variable and unstable (observed fluctuating around 126 Hz).
`override-display-fps` forces mpv to use a fixed rate for
display-resample calculations instead of its broken estimation.
Research warns this can conflict with `display-resample` in some
setups, but the alternative (unstable estimation → VSync Ratio ~5)
is worse. This should be gated behind a conditional profile so it
only activates on Linux/Wayland.

**Important caveat**: `override-display-fps` is NOT recommended as
a general practice. It's a targeted workaround for the specific
KDE Plasma Wayland presentation feedback bug. If the compositor is
fixed in a future KDE release, this override should be re-evaluated.

**Alternatives considered**:
- Do nothing: Leaves VSync Ratio at ~5 on Linux — unacceptable
- `kscreen-doctor` refresh rate switching: Too invasive, requires
  external tooling, violates Constitution Principle I
- `gpu-context=x11egl` (XWayland fallback): Loses native Wayland
  benefits (HDR, VRR, input latency)

### R3 — `video-timing-offset` Tuning

**Decision**: Add `video-timing-offset=0.01` to the profiles that
use `display-resample`.

**Rationale**: `video-timing-offset` adjusts when mpv delivers
frames relative to the V-Sync boundary. The default (0.050) may be
too aggressive for Vulkan + gpu-next, causing frames to be
scheduled too close to the deadline and arriving "delayed". A
smaller offset (0.01) gives the GPU more breathing room for frame
presentation. This is a conservative change that can be tuned
further based on testing.

### R4 — `video-sync-max-video-change` Tuning

**Decision**: Not changing this value initially. The default (1%)
is adequate for the 143.981/23.976 ratio which only requires
~0.1% speed adjustment.

**Rationale**: The required speed change is
(6.006 - 6) / 6 × 100 ≈ 0.1%, well within the 1% default
threshold. Increasing this could mask worse problems.

### R5 — Adaptive Sync / VRR Conflict

**Decision**: Document in config comments that `display-resample`
should be disabled when VRR/G-Sync is active. The
`[protocol.https]` profile already uses `video-sync=audio` which
is correct for streaming and VRR.

**Rationale**: Research confirms a known conflict between
`display-resample` and Adaptive Sync on KDE Wayland. If VRR is
active, `video-sync=audio` is the correct mode since the display
adapts to the content rate.

## Phase 1: Implementation Design

### Change 1 — Replace `tscale=oversample` with `tscale=linear` (CROSS-PLATFORM)

**File**: `config/mpv.conf.template`
**Profiles affected**: `[live-action]`, `[anime]`

Both profiles currently have:
```ini
video-sync=display-resample
interpolation=yes
tscale=oversample
```

Change to:
```ini
video-sync=display-resample
interpolation=yes
tscale=linear
```

**Impact**: Reduces jitter at non-integer VSync ratios. Minimal
visual quality difference — `linear` is still a sharp temporal
scaler, just slightly softer than `oversample` during the
sub-frame blending that handles the 0.006 fractional remainder.

### Change 2 — Add `video-timing-offset` (CROSS-PLATFORM)

**File**: `config/mpv.conf.template`
**Profiles affected**: `[live-action]`, `[anime]`

Add to both profiles:
```ini
video-timing-offset=0.01
```

**Impact**: Gives the Vulkan renderer more headroom for frame
delivery, reducing "delayed" frame count.

### Change 3 — Add Wayland `override-display-fps` Conditional Profile (LINUX ONLY)

**File**: `config/mpv.conf.template`

Add a new conditional profile that activates ONLY on Linux/Wayland
when the display reports ~144 Hz:

```ini
# ── Wayland Refresh Rate Stabilization ────────────────────────
# KDE Plasma 6.6.4 Wayland provides unstable presentation feedback,
# causing mpv's estimated refresh rate to wander. This forces mpv
# to trust the specified rate for display-resample calculations.
# Re-evaluate after KDE Plasma 7 or when compositor timing improves.
[wayland-144hz-fix]
profile-desc="Fix unstable display-resample on KDE Wayland 144Hz"
profile-cond=p["display-fps"] > 140 and p["display-fps"] < 148 and string.find(p["options/gpu-context"] or "", "wayland") ~= nil
override-display-fps=143.981
profile-restore=copy
```

**Impact**: Linux/Wayland only. Forces mpv to use 143.981 Hz
instead of its unstable estimation. The `profile-cond` ensures:
1. Only activates when display-fps is near 144 Hz (140–148 range)
2. Only activates under a Wayland GPU context
3. Does not affect Windows, X11, or other refresh rates
4. Uses `profile-restore=copy` so it reverts cleanly

### Change 4 — Add VRR/G-Sync Documentation Comment

**File**: `config/mpv.conf.template`

Add a comment block before the `[live-action]` profile:

```ini
# ── IMPORTANT: Adaptive Sync / VRR / G-Sync ──────────────────
# If your display uses Variable Refresh Rate (FreeSync/G-Sync),
# display-resample may CONFLICT with VRR. Consider using:
#   video-sync=audio
#   interpolation=no
# The [protocol.https] streaming profile already uses this mode.
```

### Files NOT Changed

- `deploy/*.py` — No installer/deployer changes (Constitution I)
- `config/input.conf.template` — No keybinding changes needed
- `config/script-opts/*` — No script-opts changes needed

## Verification Plan

### Manual Testing (Primary)

1. **Windows (nv12 H.264 — Frieren)**:
   - Play with new config, check Shift+I stats
   - Target: VSync Jitter < 0.30, Delayed < 50

2. **Windows (p010 H.265 — Wistoria)**:
   - Play with new config, check Shift+I stats
   - Target: VSync Ratio 6 (±0.05), Jitter < 0.30

3. **Linux KDE Wayland (p010 H.265 — Wistoria)**:
   - Play with new config, check Shift+I stats
   - Target: VSync Ratio 6 (±0.10), Jitter < 0.20
   - Verify `override-display-fps` is active (check stats)

4. **Anime profile (any anime file)**:
   - Verify Anime4K shaders still work
   - Verify no frame drops from shader pipeline

5. **Streaming profile (YouTube)**:
   - Verify `[protocol.https]` still uses `video-sync=audio`
   - Confirm no display-resample activation during streaming

### Automated Verification

```bash
# Verify no deploy/ changes
git diff --name-only | grep -v '^config/'
# Should return empty

# Verify template still has all required placeholders
grep '{{SHADER_SEP}}\|{{GPU_API}}\|{{HWDEC}}\|{{VO}}' config/mpv.conf.template
```

## Complexity Tracking

No constitution violations. All changes are config-only.
