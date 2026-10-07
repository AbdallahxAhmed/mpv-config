# Feature Specification: Playback Performance — Display Sync Fixes

**Feature Branch**: `004-playback-performance`
**Created**: 2026-04-26
**Status**: Draft (revised with Linux evidence)
**Input**: Fix display-resample sync degradation on 143.981 Hz displays

## Evidence Summary

### Linux — KDE Plasma 6.6.4, Wayland, NVIDIA nvdec

**File**: `[Judas] Wistoria - S02E01.mkv` — H.265 10-bit (p010), 23.976 fps
**Observed**:
- Refresh Rate: `143.981 Hz (specified)` — **126.5232 Hz (estimated)** — variable/unstable
- VSync Ratio: **4.99** (should be ~6.006)
- VSync Jitter: **0.3943**
- Mistimed: **44**, Delayed: **85**
- HW: `nvdec`, VO: `gpu-next`, Context: `waylandvk`

### Windows — NVIDIA Vulkan hwdec

**File 1**: `[Erai-raws] Sousou no Frieren 2nd Season - 10` — H.264 (nv12), 23.976 fps, 5.069 Mbps
**Observed**:
- Refresh Rate: `143.981 Hz (specified)` — **143.9747 Hz (estimated)** — accurate ✅
- VSync Ratio: **6** — correct ✅
- VSync Jitter: **0.909** — very high despite correct ratio ❌
- Mistimed: **2**, Delayed: **172** ❌
- HW: `vulkan`, VO: `gpu-next`, Context: `winvk`
- Format: `nv12`, Levels: `limited`

**File 2**: `[Judas] Wistoria - S02E01.mkv` — H.265 10-bit (p010), 23.976 fps, 623 kbps
**Observed**:
- Refresh Rate: `143.981 Hz (specified)` — **142.0885 Hz (estimated)** — slightly off
- VSync Ratio: **5.9167** — close but not 6 ⚠️
- VSync Jitter: **0.8023** ❌
- Mistimed: **5**, Delayed: **45**, Dropped: **2 (output)**
- HW: `vulkan`, VO: `gpu-next`, Context: `winvk`
- Format: `p010`, Levels: `limited`

### Cross-Platform Comparison

| Metric          | Linux (Wistoria p010) | Win (Frieren nv12) | Win (Wistoria p010) |
|-----------------|----------------------|--------------------|--------------------|
| Estimated Hz    | 126.5 (wrong)        | 143.97 (correct)   | 142.09 (close)     |
| VSync Ratio     | 4.99                 | 6 ✅               | 5.92               |
| VSync Jitter    | 0.39                 | **0.91**           | **0.80**           |
| Mistimed        | 44                   | 2                  | 5                  |
| Delayed         | 85                   | **172**            | 45                 |
| Pixel Format    | p010                 | nv12               | p010               |

**Critical finding**: Windows jitter (0.80–0.91) is **worse** than
Linux (0.39) despite having correct or near-correct VSync Ratio and
refresh rate estimation. This means the problem is NOT just Wayland
compositor timing — there is a fundamental frame timing instability
affecting display-resample on both platforms with the current config.

## Root Cause Analysis

### CAUSE 1 — display-resample Frame Timing Jitter (PRIMARY, CROSS-PLATFORM)

`display-resample` with `interpolation=yes` and `tscale=oversample`
produces high jitter and excessive delayed frames on **both**
platforms, regardless of codec or pixel format:
- Windows (nv12, correct VSync Ratio 6): Jitter **0.909**, Delayed **172**
- Windows (p010, VSync Ratio 5.92): Jitter **0.802**, Delayed **45**
- Linux (p010, VSync Ratio 4.99): Jitter **0.394**, Delayed **85**

The delayed frame count is the most telling metric — even when mpv
calculates the correct VSync Ratio (Windows Frieren = 6), frames
are still presented late 172 times. This points to the
display-resample + oversample combination struggling with the
non-integer ratio of 143.981/23.976 ≈ 6.006 — the tiny fractional
remainder accumulates timing drift that the oversample interpolator
cannot absorb cleanly.

**Affected**: All content using `video-sync=display-resample` with
`interpolation=yes` and `tscale=oversample` on both Linux and
Windows, regardless of codec or pixel format.

### CAUSE 2 — Unstable Wayland Presentation Timing (LINUX-SPECIFIC)

On Linux (KDE Plasma 6.6.4 Wayland), mpv's estimated refresh rate
is **variable and unstable** (observed at 126.5 Hz, fluctuating),
even though the specified rate is correct (143.981 Hz). This
compounds Cause 1 by making the VSync Ratio itself wrong (~5
instead of ~6).

The Wayland compositor's presentation feedback timing is jittery,
causing mpv's estimation algorithm to wander. On Windows, this
estimation is accurate (143.97 Hz), so Windows at least gets the
correct VSync Ratio — but still suffers from Cause 1 jitter.

**Affected**: Linux KDE Plasma Wayland only.

### CAUSE 3 — Pixel Format / Codec Correlation (UNCONFIRMED)

Initially suspected as nv12 color conversion overhead, but the
evidence does NOT support pixel format as a primary factor:
- p010 (10-bit) shows the same problems on both platforms
- nv12 (8-bit) on Windows has correct VSync Ratio but high jitter
- The low-bitrate Wistoria p010 (623 kbps) performs worse than the
  higher-bitrate Frieren nv12 (5 Mbps) on Windows, suggesting
  bitrate or encode complexity may matter more than pixel format

**Status**: Needs further investigation. Not actionable until
Causes 1 and 2 are addressed.

## User Scenarios & Testing

### User Story 1 — Correct Refresh Rate Under Wayland (Priority: P0)

A user plays any video file on Linux KDE Plasma Wayland with a
143.981 Hz display. mpv's display-resample uses the correct refresh
rate (143.981 Hz), not an incorrect estimate (126.5 Hz), producing
the correct VSync Ratio of ~6 for 23.976 fps content.

**Why this priority**: This is the root cause of ALL display-resample
failures on the user's Linux setup. Without fixing the refresh rate,
no other sync improvement matters.

**Independent Test**: Play any 23.976 fps file with
`video-sync=display-resample` on KDE Plasma Wayland. Check
Shift+I stats: "Refresh Rate" specified vs estimated values.

**Acceptance Scenarios**:

1. **Given** a 23.976 fps file playing on KDE Plasma Wayland at
   143.981 Hz,
   **When** display-resample is active,
   **Then** VSync Ratio stabilizes at 6 (±0.05), jitter stays
   below 0.10, and mistimed frames remain below 5 over a 60-second
   window.

2. **Given** the same file playing on X11 (not Wayland),
   **When** display-resample is active,
   **Then** behavior is unchanged — the fix does not negatively
   affect X11 sessions.

---

### User Story 2 — Smooth nv12 Playback on Windows (Priority: P2)

A user plays an 8-bit H.265 WEB-DL file (nv12 pixel format) on
Windows with a 143.981 Hz display. Playback achieves VSync Ratio ~6
with jitter below 0.10.

**Acceptance Scenarios**:

1. **Given** a 23.976 fps nv12 H.265 file playing on Windows at
   143.981 Hz,
   **When** display-resample is active,
   **Then** VSync Ratio stabilizes at 6 (±0.05) and jitter stays
   below 0.10.

---

### User Story 3 — Existing Profile Compatibility (Priority: P1)

All changes integrate cleanly with the existing `[live-action]`,
`[anime]`, `[protocol.https]`, and `[protocol.file]` profiles.
No profile's behavior is altered in a way that degrades playback
for content that was already playing smoothly.

**Acceptance Scenarios**:

1. **Given** a file that triggers the `[anime]` profile,
   **When** Anime4K shaders are active with the fix applied,
   **Then** shader performance and VSync Ratio are unchanged.

2. **Given** a YouTube stream via `[protocol.https]`,
   **When** played with `video-sync=audio` (the streaming profile),
   **Then** behavior is identical — the fix does not inject
   display-resample into the streaming profile.

---

### Edge Cases

- **24.000 fps content**: VSync Ratio = 143.981/24 ≈ 5.999. The
  fix must work for any frame rate, not just 23.976.
- **60 fps content at 143.981 Hz**: VSync Ratio ≈ 2.4. display-
  resample inherently struggles here; the fix must not make it worse.
- **nv12 + AV1 combination**: Files hitting multiple causes must
  be handled correctly.
- **VRR/G-Sync displays**: display-resample should not be forced
  on VRR setups where `video-sync=audio` is optimal. The fix must
  not conflict with VRR.
- **GPU driver updates**: Wayland presentation feedback accuracy
  may improve. The fix should be conservative (override, not hack)
  so it remains safe as compositors improve.
- **X11 fallback sessions**: If a user runs KDE in X11 mode, the
  refresh rate fix should either not apply or remain harmless.

## Requirements

### Functional Requirements

- **FR-001**: The mpv configuration MUST compensate for KDE Plasma
  Wayland's unstable presentation feedback timing so that
  display-resample can maintain sync. This may involve
  `override-display-fps` to force mpv to trust the specified rate
  instead of its unstable estimation, `video-timing-offset`
  adjustments, `video-sync-max-video-change` tuning, or a
  combination of options that stabilize the frame scheduling
  algorithm despite jittery compositor timing.

- **FR-002**: The mpv configuration SHOULD include settings that
  mitigate nv12 color conversion overhead on Windows when possible,
  without disabling hardware decoding entirely.

- **FR-003**: All configuration changes MUST reside exclusively
  in `config/mpv.conf.template` (and optionally
  `config/input.conf.template` for debug bindings). No changes to
  `deploy/*.py` or root-level scripts for playback fixes.

- **FR-004**: The existing `[live-action]` and `[anime]` profiles
  MUST NOT be altered in a way that degrades playback for content
  that currently plays smoothly.

- **FR-005**: The `[protocol.https]` streaming profile (which uses
  `video-sync=audio`) MUST NOT be affected by any display-resample
  fixes.

- **FR-006**: The fix MUST work on both Linux and Windows. If
  platform-specific configuration is needed, it MUST use mpv's
  conditional profile system (`profile-cond`) or the existing
  template token system.

### Key Entities

- **VSync Ratio**: mpv's measured ratio of display refresh rate
  to video frame rate. For 143.981 Hz / 23.976 fps, the ideal
  ratio is 6.006. Stable ratio indicates smooth playback.

- **Jitter**: Frame timing variance reported by mpv stats.
  Values below 0.10 indicate smooth playback. Values above 0.30
  indicate visible judder.

- **Mistimed/Delayed Frames**: Frames displayed at the wrong VSync
  boundary. Ideally 0; values above 10 are noticeable. Screenshot
  shows 44 mistimed + 85 delayed.

- **Estimated vs Specified Refresh Rate**: mpv has two refresh rate
  values — "specified" (from the display mode) and "estimated"
  (from internal frame timing measurement). When these diverge
  significantly, display-resample breaks.

- **override-display-fps**: mpv option that forces a specific
  refresh rate, bypassing the broken estimation. This is the most
  likely fix for Cause 1.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Playing a 23.976 fps file on KDE Plasma Wayland at
  143.981 Hz with display-resample produces VSync Ratio 6 (±0.05)
  and jitter below 0.10, despite the compositor's unstable
  presentation feedback.

- **SC-002**: Playing a 23.976 fps nv12 H.265 file on Windows at
  143.981 Hz with display-resample produces VSync Ratio 6 (±0.05)
  and jitter below 0.10.

- **SC-003**: Playing a 10-bit H.265 file that currently works on
  Windows (VSync Ratio 6, jitter 0.05) shows zero degradation.

- **SC-004**: All config changes reside exclusively in `config/`
  — zero modifications to `deploy/` or root-level scripts.

- **SC-005**: The `[anime]` profile with Anime4K shaders active
  shows no VSync Ratio degradation after the fix.

- **SC-006**: X11 sessions on Linux are unaffected by the fix.

## Assumptions

- The primary target is a 143.981 Hz display on KDE Plasma 6.6.4
  Wayland with NVIDIA GPU using nvdec hardware decoding.
- The GPU is NVIDIA with recent drivers on both Linux and Windows.
- mpv version is 0.37+ with `gpu-next` video output and Vulkan
  GPU API.
- `auto-safe` hwdec mode is in use.
- The Wayland refresh rate estimation bug is a known compositor
  limitation — the fix must work around it at the mpv config level,
  not require compositor patches.
- The fix will use mpv configuration options and conditional
  profiles only — no external scripts, no Lua plugins, no
  deployer changes.
