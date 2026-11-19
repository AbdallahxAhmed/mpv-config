# Feature Specification: Playback Performance — Display Sync Fixes

**Feature Branch**: `004-playback-performance`
**Created**: 2026-04-26
**Status**: Implemented — verified on Linux/Wayland 2026-11-19. Windows verification pending. FR-002 (nv12 mitigation) deferred.
**Input**: Fix display-resample sync degradation on 143.981 Hz displays

## Verification Method

### Pass criteria

Measured over **at least 60 s of playback without seeking**, on a
143.98 Hz panel with 23.976 fps content:

| Property | Pass criterion |
|----------|----------------|
| `vsync-ratio` | Stable at 6 (±0.05) |
| `vo-delayed-frame-count` | 0 after startup |
| `frame-drop-count` | 0 after startup |
| `mistimed-frame-count` | Does not increase after startup. A value of 1–2 set at startup is acceptable; bare mpv (`--no-config`) shows the same |
| `avsync` | Within ±0.005 s |
| `vsync-jitter` | **Recorded, not a pass criterion** |

Earlier proposals (jitter below 0.30 as the pass mark, VSync ratio
tolerance ±0.10) are rejected.

**Why `vsync-jitter` is not a pass criterion (measured)**: on KDE
Wayland, Anime4K A+A raises `vsync-jitter` to about 0.44 while
`vo-delayed-frame-count` stays 0. In mpv, `vsync-jitter` is the spread
of the reported flip-to-flip intervals, while the delayed counter
counts frames that land on the wrong vsync. The panel only shows
frames at vsyncs, so the delayed, mistimed and drop counters are the
ones that reflect what is on screen.

### How to measure

These are manual runs on the maintainer's 143.98 Hz monitor, not
automated tests:

```sh
mpv --no-resume-playback --length=90 --term-status-msg='ratio=${vsync-ratio} jitter=${vsync-jitter} avsync=${avsync} drop=${frame-drop-count} delayed=${vo-delayed-frame-count} mistimed=${mistimed-frame-count}' <file>
```

Read the last status line after the first ~5 s (startup) and at the
end of the run. The counters must not have grown in between.

The only automated coverage is string-presence assertions on the
template in
`tests/test_audit_patches.py::test_spec_004_playback_performance_profiles`.

## Measurement results — 2026-11-19

**Environment**: CachyOS, KDE Plasma Wayland, NVIDIA RTX 3060, panel
1920x1080 @ 143.98 Hz (per `kscreen-doctor`), VRR off, `vo=gpu-next`,
`hwdec=nvdec`.

**Test files** (by title): *Black Clover* S02E05 (H.264, nv12);
*Kusuriya no Hitorigoto* S03E07 (AV1, p010).

### Isolation runs — Black Clover, 45 s each

These isolate which layer adds jitter. They are shorter than the 60 s
pass window and are diagnostic only.

| Run | jitter | delayed | mistimed | drop |
|-----|--------|---------|----------|------|
| bare mpv (`--no-config`, display-resample, software decode) | 0.0748 | 1 | 1 | – |
| + nvdec + interpolation + `tscale=oversample` | 0.1084 | 5 | 3 | 0 |
| + Anime4K A+A | 0.439 | 0 | 2 | 0 |

### Full config

| File | Duration | ratio | jitter | avsync | delayed | mistimed | drop | Result |
|------|----------|-------|--------|--------|---------|----------|------|--------|
| Black Clover S02E05 | 60+ s, no resume | 6 | – | +0.00039 s | 0 | 2 (set at startup, constant) | 0 | **Pass** |
| Kusuriya no Hitorigoto S03E07 | short run (< 60 s) | 6 | 0.4348 | −0.00193 s | 0 | 1 | 0 | Consistent, but below the 60 s window |

### Observations

- Bare mpv reported `display-fps` 143.981 by itself, matching
  `display-fps-override = 143.981` in `[wayland-144hz-fix]`. On this
  setup the estimation was not unstable, unlike the 126.5 Hz evidence
  below. The override is consistent with, not contradicted by, the
  measurement.
- **Not reproduced**: earlier first runs showed delayed 8–9 and drop 1.
  Later runs did not reproduce this. Likely causes are first-run shader
  compilation or a resume seek, but this is not confirmed.
- The full-config runs used the runtime `tscale` set by
  `scripts/smart_motion.lua` (`default_tscale=oversample`), not the
  profiles' `tscale=linear`. See Open items.

### Not measured

- **Windows**: not measured yet. All Windows criteria are pending.
- X11 sessions, 24.000 fps and 60 fps content.

## Open items

- **smart_motion.lua needs its own spec or a section here.** It is not
  covered by any spec, yet at runtime it sets `tscale` from
  `default_tscale` in `script-opts/smart_motion.conf` (currently
  `oversample`). That overrides the profiles' `tscale=linear`. It also
  sets `video-sync=display-resample` and `interpolation` on local files.
  That overrides the deployer's VRR mode (`video-sync=audio`,
  `interpolation=no`) unless smart_motion is disabled.
- **Windows verification**: run the measurement command on Windows
  (nv12 and p010 files) against the pass criteria above.
- **Delayed 8–9 / drop 1 on first runs**: not reproduced; re-check on a
  cold shader cache.

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

**Resolution**: the profiles `[live-action]` and `[anime]` set
`tscale = linear`, but `scripts/smart_motion.lua` overrides `tscale`
at runtime with `default_tscale` (currently `oversample`), so `linear`
is not the effective runtime value. `video-timing-offset = 0.01` is not
used under `display-resample` (see FR-001). The 2026-11-19 Linux
measurements pass with the runtime `oversample` (delayed 0, drop 0).

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

**Resolution**: `display-fps-override = 143.981` in the conditional
`[wayland-144hz-fix]` profile (the option was called
`override-display-fps` before mpv 0.37; the old name now only emits a
deprecation warning).

### CAUSE 3 — Pixel Format / Codec Correlation (UNCONFIRMED)

Initially suspected as nv12 color conversion overhead, but the
evidence does NOT support pixel format as a primary factor:
- p010 (10-bit) shows the same problems on both platforms
- nv12 (8-bit) on Windows has correct VSync Ratio but high jitter
- The low-bitrate Wistoria p010 (623 kbps) performs worse than the
  higher-bitrate Frieren nv12 (5 Mbps) on Windows, suggesting
  bitrate or encode complexity may matter more than pixel format

**Status**: Needs further investigation. Not actionable until
Causes 1 and 2 are addressed. Causes 1 and 2 are now addressed, so this
remains **deferred**: no nv12-specific mitigation is implemented (see
FR-002 and User Story 4).

## User Scenarios & Testing

### User Story 1 — Clean display-resample Frame Timing (Priority: P0)

A user plays a 23.976 fps file on a 143.98 Hz display on Windows or
Linux with `video-sync=display-resample`. No frames are delayed or
dropped after startup, and the VSync ratio holds at 6.

**Why this priority**: Cause 1 affects both platforms regardless of
codec, so it is the primary fix.

**Independent Test (manual)**: run the measurement command from
*Verification Method* for at least 60 s without seeking.

**Acceptance Scenarios**:

1. **Given** a 23.976 fps file at 143.98 Hz,
   **When** display-resample is active,
   **Then** `vsync-ratio` is 6 (±0.05), `vo-delayed-frame-count` and
   `frame-drop-count` stay 0 after startup, `mistimed-frame-count`
   does not increase after startup, and `avsync` stays within
   ±0.005 s. Linux/Wayland: **passed 2026-11-19**. Windows: pending.

---

### User Story 2 — Correct Refresh Rate Under Wayland (Priority: P1)

A user plays any video file on Linux KDE Plasma Wayland with a
143.981 Hz display. mpv's display-resample uses the specified refresh
rate (143.981 Hz), not an unstable estimate (126.5 Hz), producing a
VSync Ratio near 6 for 23.976 fps content.

**Why this priority**: Cause 2 breaks the VSync Ratio itself on Linux,
but it only affects one platform, so it ranks below the cross-platform
fix.

**Independent Test (manual)**: Run the measurement command on KDE
Plasma Wayland with a 23.976 fps file.

**Acceptance Scenarios**:

1. **Given** a 23.976 fps file playing on KDE Plasma Wayland at
   143.981 Hz,
   **When** display-resample is active,
   **Then** `[wayland-144hz-fix]` is active and the User Story 1 pass
   criteria hold (ratio 6 ±0.05). **Passed 2026-11-19** (Black Clover,
   60+ s).

2. **Given** the same file playing on X11 or Windows,
   **When** display-resample is active,
   **Then** `[wayland-144hz-fix]` does not activate and behavior is
   unchanged. Not measured yet.

---

### User Story 3 — Existing Profile Compatibility (Priority: P1)

All changes integrate cleanly with the existing `[live-action]`,
`[anime]`, `[protocol.https]`, and `[protocol.file]` profiles.
No profile's behavior is altered in a way that degrades playback
for content that was already playing smoothly.

**Acceptance Scenarios**:

1. **Given** a file that triggers the `[anime]` profile,
   **When** Anime4K shaders are active with the fix applied,
   **Then** shader performance and VSync Ratio are unchanged. Linux:
   delayed 0 / drop 0 with Anime4K A+A (45 s isolation run; Kusuriya
   short run ratio 6). Jitter rises to ~0.44, which is expected and not
   a pass criterion.

2. **Given** a YouTube stream via `[protocol.https]`,
   **When** played,
   **Then** it inherits `video-sync` from the base config
   (`{{VIDEO_SYNC}}`) and `interpolation` from the active content
   profile; `tscale` is set at runtime by `smart_motion.lua` (see
   FR-005). Not measured yet.
   Cache settings protect against network jitter.

---

### User Story 4 — Smooth nv12 Playback on Windows (Priority: P2, DEFERRED)

A user plays an 8-bit H.265 WEB-DL file (nv12 pixel format) on
Windows with a 143.981 Hz display and gets VSync Ratio ~6 with jitter
below 0.10.

**Status**: **Deferred, not implemented.** Cause 3 (pixel format /
codec correlation) is unconfirmed, and the evidence does not support
pixel format as the primary factor. User Story 1 is expected to cover
nv12 content too; whether anything nv12-specific is still needed is to
be decided after measuring with the User Story 1 fix. No task exists
for it.

---

### Edge Cases

- **24.000 fps content**: VSync Ratio = 143.981/24 ≈ 5.999. The
  fix must work for any frame rate, not just 23.976. Not separately
  verified.
- **60 fps content at 143.981 Hz**: VSync Ratio ≈ 2.4. display-
  resample inherently struggles here; the fix must not make it worse.
  Not separately verified.
- **nv12 + AV1 combination**: Not addressed (see User Story 4).
- **VRR/G-Sync displays**: display-resample is NOT auto-disabled, and
  `smart_motion.lua` re-sets `video-sync=display-resample` at runtime
  on local files even in VRR mode (see Open items). The
  default `auto` display mode resolves to `display-resample`
  (`video-sync=display-resample`, `interpolation=yes`). VRR users must
  pass `--display-mode vrr` to the deployer, which renders
  `video-sync=audio` and `interpolation=no`. The template carries a
  comment block above `[live-action]` documenting the conflict.
- **GPU driver updates**: Wayland presentation feedback accuracy
  may improve. The fix is conservative (a gated override profile) so it
  remains safe as compositors improve.
- **X11 fallback sessions**: `[wayland-144hz-fix]` requires a
  `wayland` GPU context, so it does not activate on X11.

## Requirements

### Functional Requirements

- **FR-001**: The mpv configuration MUST compensate for KDE Plasma
  Wayland's unstable presentation feedback timing so that
  display-resample can maintain sync. Implemented via
  `display-fps-override = 143.981` in the conditional
  `[wayland-144hz-fix]` profile. The profiles also set
  `tscale = linear`, but `smart_motion.lua` overrides `tscale` at
  runtime (see Open items). They also set `video-timing-offset = 0.01`;
  per the mpv manual this option applies only to audio timing modes
  (`video-sync=audio`). Under `display-resample` (the default mode) it
  is not used. It only matters in the deployer's VRR mode.
  `video-sync-max-video-change` is intentionally left at its default
  (see research R4).

- **FR-002** (**DEFERRED — not implemented**): The mpv configuration
  SHOULD include settings that mitigate nv12 color conversion overhead
  on Windows without disabling hardware decoding. Deferred because
  Cause 3 is unconfirmed ("needs further investigation").

- **FR-003**: Playback fixes MUST live in `config/mpv.conf.template`
  (and optionally `config/input.conf.template` for debug bindings), with
  no playback-specific logic added to `deploy/*.py` or root-level
  scripts. The template is rendered by the deployer
  (`deploy/deployer.py`), which fills `{{VIDEO_SYNC}}` and
  `{{INTERPOLATION}}` from `_resolve_display_mode()` and resolves the
  Wayland GPU context (`{{GPU_CONTEXT}}`: `waylandvk` on Wayland,
  `x11vk` on X11). This substitution layer is the expected boundary
  under Constitution Principle I.

- **FR-004**: The existing `[live-action]` and `[anime]` profiles
  MUST NOT be altered in a way that degrades playback for content
  that currently plays smoothly.

- **FR-005**: The `[protocol.https]` streaming profile MUST NOT be
  altered by the display-resample fixes. It deliberately keeps
  `display-resample` (inherited from the base config) and does not set
  `video-sync=audio`. Reason: at a fixed 144 Hz, 30 fps with
  `video-sync=audio` gives a 144/30 = 4.8 non-integer cadence, which
  causes micro-judder. The larger cache (800 MiB, 60 s readahead,
  `cache-pause=no`) absorbs network jitter that the old
  `video-sync=audio` fallback was compensating for. `[protocol.http]`
  and `[protocol.ytdl]` alias this profile. VRR users get
  `video-sync=audio` globally via `--display-mode vrr` (subject to the
  smart_motion caveat in Open items).

- **FR-006**: The fix MUST work on both Linux and Windows. Platform
  differences use mpv's conditional profile system (`profile-cond`) or
  the deployer's template token system.

### Key Entities

- **VSync Ratio**: mpv's measured ratio of display refresh rate
  to video frame rate. For 143.981 Hz / 23.976 fps, the ideal
  ratio is 6.006. Stable ratio indicates smooth playback.

- **Jitter** (`vsync-jitter`): the spread of the reported
  flip-to-flip intervals. Recorded, but not a pass criterion: it can
  reach ~0.44 under Anime4K while no frame lands on the wrong vsync.

- **Mistimed/Delayed Frames**: Frames displayed at the wrong VSync
  boundary. Ideally 0; values above 10 are noticeable. The Linux
  evidence screenshot shows 44 mistimed + 85 delayed.

- **Estimated vs Specified Refresh Rate**: mpv has two refresh rate
  values — "specified" (from the display mode) and "estimated"
  (from internal frame timing measurement). When these diverge
  significantly, display-resample breaks.

- **display-fps-override**: mpv option (formerly `override-display-fps`)
  that forces a specific refresh rate, bypassing the unstable
  estimation. It is the fix for Cause 2 (Wayland), not Cause 1.

## Success Criteria

### Measurable Outcomes

All measured outcomes are **manual runs** of the command in
*Verification Method* on the maintainer's 143.98 Hz monitor (≥ 60 s,
no seeking). "Pass criteria" means: `vsync-ratio` 6 (±0.05),
`vo-delayed-frame-count` = 0 and `frame-drop-count` = 0 after startup,
`mistimed-frame-count` not increasing after startup, `avsync` within
±0.005 s. `vsync-jitter` is recorded only.

- **SC-001**: A 23.976 fps file on KDE Plasma Wayland meets the pass
  criteria. **Met 2026-11-19** (Black Clover S02E05).

- **SC-002**: A 23.976 fps file on Windows meets the pass criteria.
  **Pending** — Windows not measured yet.

- **SC-003**: A 10-bit H.265 file that previously worked on Windows
  shows no degradation. **Pending** — Windows not measured yet.

- **SC-004**: Playback fixes are confined to `config/mpv.conf.template`;
  the deployer only fills `{{VIDEO_SYNC}}`, `{{INTERPOLATION}}` and
  resolves the Wayland GPU context, with no playback-specific logic
  added (code review).

- **SC-005**: The `[anime]` profile with Anime4K shaders active keeps
  `vsync-ratio` at 6 with no delayed or dropped frames. Linux evidence:
  45 s isolation run (delayed 0, drop 0) and a short Kusuriya run
  (ratio 6, delayed 0, drop 0). **Not yet confirmed over a full 60 s
  window.**

- **SC-006**: X11 sessions on Linux are unaffected: `[wayland-144hz-fix]`
  does not activate. **Not measured.**

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
- The fix uses mpv configuration options and conditional profiles in
  the template, with the deployer's existing token substitution. No
  external scripts and no Lua plugins are involved in the sync fix.
