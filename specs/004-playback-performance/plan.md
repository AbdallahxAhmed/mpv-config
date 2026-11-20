# Implementation Plan: Playback Performance — Display Sync Fixes

**Branch**: `004-playback-performance` (merged to `main`) | **Date**: 2026-04-26 | **Status**: Implemented — verified on Linux/Wayland 2026-11-19; Windows verification pending | **Spec**: [spec.md](spec.md)

**Code under plan**: [`config/mpv.conf.template`](../../config/mpv.conf.template) ·
[`deploy/deployer.py`](../../deploy/deployer.py) (`_resolve_display_mode`, token substitution, GPU-context resolution) ·
[`tests/test_audit_patches.py`](../../tests/test_audit_patches.py) (`test_spec_004_playback_performance_profiles`)

## Summary

Fix display-resample frame timing jitter on both Windows (Vulkan)
and Linux (KDE Plasma 6.6.4 Wayland). The primary cause is the
`display-resample` + `tscale=oversample` combination struggling
with the non-integer VSync ratio of 143.981/23.976 ≈ 6.006, producing
high jitter (0.8–0.9 on Windows, 0.4 on Linux) and excessive delayed
frames. A secondary Linux-specific cause is unstable Wayland
presentation feedback making the estimated refresh rate variable.

## Technical Context

**Language/Version**: mpv configuration (INI-like format), Lua profile conditions, `{{TOKEN}}` template substitution done by `deploy/deployer.py`
**Primary Dependencies**: mpv 0.37+, gpu-next VO, Vulkan GPU API
**Target Platform**: Windows 10/11 + Linux (KDE Plasma 6.6.4 Wayland)
**Project Type**: Configuration template (playback logic in `config/` only; the deployer only substitutes tokens)
**Constraints**: Constitution Principle I (Boundary Separation) — playback fixes in `config/mpv.conf.template`; no playback logic in `deploy/`

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Boundary Separation | ✅ PASS | Playback fixes live in `config/mpv.conf.template`. The deployer fills `{{VIDEO_SYNC}}`/`{{INTERPOLATION}}` via `_resolve_display_mode()` and resolves the Wayland GPU context, with no config literals added |
| II. Cross-Platform Parity | ✅ PASS | Fix addresses both Windows and Linux |
| III. Dependency Classification | ✅ N/A | No dependency changes |
| IV. Shell Compatibility | ✅ N/A | No shell script changes |
| V. Aesthetic CLI UX | ✅ N/A | No UI changes |
| VI. User Customization | ✅ PASS | Changes are additive to existing profiles; user overrides stay in `mpv.conf.user` |
| VII. Idempotent Operations | ✅ N/A | No installer changes |

## Project Structure

### Documentation (this feature)

```text
specs/004-playback-performance/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 research findings
├── tasks.md             # Task list
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code Changes

```text
config/
└── mpv.conf.template    # All playback changes
deploy/
└── deployer.py          # Pre-existing: fills {{VIDEO_SYNC}}, {{INTERPOLATION}}
                         # (_resolve_display_mode) and resolves the Wayland
                         # GPU context; no playback logic added for this spec
tests/
└── test_audit_patches.py  # String-presence test for the profiles
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

**Runtime reality (2026-11-19)**: the profile value is not the effective
`tscale`. `scripts/smart_motion.lua` sets `tscale` at runtime from
`default_tscale` in `config/script-opts/smart_motion.conf`, currently
`oversample`. The Linux measurements in [spec.md](spec.md#measurement-results--2026-11-19)
were therefore taken with `oversample` and pass (delayed 0, drop 0).
The rationale above, that `oversample` causes delayed frames at this
ratio, is not confirmed by those measurements. smart_motion is not
covered by any spec; see Open items.

### R2 — `display-fps-override` for Wayland Estimation Fix

**Decision**: Add `display-fps-override = 143.981` (formerly
`override-display-fps`, renamed in mpv 0.37) via a conditional
Linux/Wayland profile in the template.

**Rationale**: On KDE Plasma Wayland, mpv's estimated refresh rate
is variable and unstable (observed fluctuating around 126 Hz).
`display-fps-override` forces mpv to use a fixed rate for
display-resample calculations instead of its broken estimation.
Research warns this can conflict with `display-resample` in some
setups, but the alternative (unstable estimation → VSync Ratio ~5)
is worse. This should be gated behind a conditional profile so it
only activates on Linux/Wayland.

**Important caveat**: `display-fps-override` is NOT recommended as
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

**Decision (as implemented)**: `video-timing-offset = 0.01` is set in
`[live-action]` and `[anime]`.

**Effect**: per the mpv manual (`--video-timing-offset`), the option
"applies only to audio timing modes (e.g. `--video-sync=audio`). In
other modes (`--video-sync=display-...`), video timing relies on vsync
blocking, and this option is not used." Under `display-resample`, the
default mode, it therefore has no effect. It only matters in the
deployer's VRR mode (`--display-mode vrr`, `video-sync=audio`). Since
2026-11-20 that mode also writes `enabled=no` into a fresh
`smart_motion.conf`, so `smart_motion.lua` no longer re-sets
`video-sync=display-resample` there (see Open items).

### R4 — `video-sync-max-video-change` Tuning

**Decision**: Not changing this value initially. The default (1%)
is adequate for the 143.981/23.976 ratio which only requires
~0.1% speed adjustment.

**Rationale**: The required speed change is
(6.006 - 6) / 6 × 100 ≈ 0.1%, well within the 1% default
threshold. Increasing this could mask worse problems.

### R5 — Adaptive Sync / VRR Conflict

**Decision**: Document in config comments that `display-resample`
should be disabled when VRR/G-Sync is active. VRR is selected with
`--display-mode vrr`, which makes the deployer render
`video-sync=audio` and `interpolation=no` through `{{VIDEO_SYNC}}` /
`{{INTERPOLATION}}` (`_resolve_display_mode`). The default (`auto`)
resolves to `display-resample`.

`[protocol.https]` does NOT use `video-sync=audio`: it inherits
`display-resample` on purpose, because at 144 Hz a 30 fps stream under
`video-sync=audio` has a 144/30 = 4.8 cadence (micro-judder). Its large
cache (800 MiB / 60 s readahead / `cache-pause=no`) handles network
jitter instead.

**Rationale**: Research confirms a known conflict between
`display-resample` and Adaptive Sync on KDE Wayland. If VRR is
active, `video-sync=audio` is the correct mode since the display
adapts to the content rate. VRR is not auto-detected; the user opts in
with `--display-mode vrr`.

## Phase 1: Implementation Design

### Change 1 — Replace `tscale=oversample` with `tscale=linear` (CROSS-PLATFORM)

**File**: `config/mpv.conf.template`
**Profiles affected**: `[live-action]`, `[anime]`

Both profiles previously had `tscale=oversample`. They now have (with
`video-sync` coming from `{{VIDEO_SYNC}}` in the base section and
`interpolation` from `{{INTERPOLATION}}`):
```ini
interpolation             = {{INTERPOLATION}}
tscale                    = linear
```

**Impact**: The profile value is overridden at runtime by
`smart_motion.lua` (`default_tscale`, currently `oversample`), so
`linear` is not the effective runtime `tscale`. See R1.

### Change 2 — Add `video-timing-offset` (CROSS-PLATFORM)

**File**: `config/mpv.conf.template`
**Profiles affected**: `[live-action]`, `[anime]`

Add to both profiles:
```ini
video-timing-offset       = 0.01
```

**Impact**: None under `display-resample` (the default). Used only
with `video-sync=audio`, i.e. the deployer's VRR mode. See R3. The
template now carries a comment above each line saying so.

### Change 3 — Add Wayland `display-fps-override` Conditional Profile (LINUX ONLY)

> **Superseded 2026-11-20.** The profile below pinned 143.981 on every 140–148 Hz
> Wayland panel and, because `display-fps` reports an active override, never
> released it. It is replaced by `scripts/display_fps_guard.lua`: the deployer
> detects the active mode (`kscreen-doctor`, then `xrandr`) and passes it via
> `script-opts-append`; the script pins the compositor-reported rate only while it
> matches that mode, and re-checks on every file and display move.

**File**: `config/mpv.conf.template`
**Position**: between `[anime]` and `[protocol.file]` (before the
streaming profiles).

```ini
# ── Wayland Refresh Rate Stabilization ────────────────────────
# KDE Plasma 6.6.4 Wayland provides unstable presentation feedback,
# causing mpv's estimated refresh rate to wander. This forces mpv
# to trust the specified rate for display-resample calculations.
# Re-evaluate after KDE Plasma 7 or when compositor timing improves.
[wayland-144hz-fix]
profile-desc              = "Fix unstable display-resample on KDE Wayland 144Hz"
profile-cond              = (p["display-fps"] or 0) > 140 and (p["display-fps"] or 0) < 148 and ((type(p["current-gpu-context"]) == "string" and p["current-gpu-context"]:find("wayland") ~= nil) or (type(p["options/gpu-context"]) == "string" and p["options/gpu-context"]:find("wayland") ~= nil) or (type(p["options/gpu-context"]) == "table" and table.concat(p["options/gpu-context"], ","):find("wayland") ~= nil))
display-fps-override      = 143.981
profile-restore           = copy
```

**Impact**: Linux/Wayland only. The `profile-cond` ensures:
1. Only activates when display-fps is near 144 Hz (strictly between
   140 and 148); `display-fps` is null-guarded with `or 0`.
2. Only activates under a Wayland GPU context, checked against the
   runtime `current-gpu-context` and against `options/gpu-context`
   whether mpv reports it as a string or a list.
3. Does not affect Windows, X11, or other refresh rates.
4. Uses `profile-restore=copy` so it reverts cleanly.

The deployer sets `gpu-context` (`waylandvk` on Wayland, `x11vk` on
X11) through `{{GPU_CONTEXT}}` in `deploy/deployer.py`.

### Change 4 — Add VRR/G-Sync Documentation Comment

**File**: `config/mpv.conf.template`

Add a comment block before the `[live-action]` profile:

```ini
# ── IMPORTANT: Adaptive Sync / VRR / G-Sync ──────────────────
# If your display uses Variable Refresh Rate (FreeSync/G-Sync),
# display-resample may CONFLICT with VRR. Consider using:
#   video-sync=audio
#   interpolation=no
# The deployer's VRR display mode (--display-mode vrr) writes exactly these
# values (video-sync=audio, interpolation=no), so no manual edit is needed.
# It also seeds script-opts/smart_motion.conf with enabled=no, so
# scripts/smart_motion.lua cannot switch video-sync back at runtime.
```

(The earlier "Caveat: … disable it (smart_motion.conf enabled=no)" lines
were replaced on 2026-11-20, once the deployer started doing that itself.)

The stale sentence "The [protocol.https] streaming profile already uses
this mode" was removed on 2026-11-19. `[protocol.https]` keeps
`display-resample` on purpose (see R5), and its inline comment now says
where `video-sync`, `interpolation` and `tscale` come from.

### Files NOT Changed by this feature

- `deploy/*.py` — no playback logic added. The pre-existing token
  substitution (`{{VIDEO_SYNC}}`, `{{INTERPOLATION}}`, `{{GPU_CONTEXT}}`)
  is what renders the template.
- `config/script-opts/*` — no script-opts changes needed

`config/input.conf.template` holds the independent `Shift+F4` / `Alt+t`
`tscale` cycling bindings (manual motion-scaler overrides, tested by
`tests/test_smart_motion.py`); they are not part of this feature.

## Verification Plan

### Manual measurement (primary — maintainer's 143.98 Hz monitor)

Pass criteria, criteria rationale and the measurement command are in
[spec.md — Verification Method](spec.md#verification-method). In short,
over ≥ 60 s without seeking: `vsync-ratio` 6 (±0.05), no delayed or
dropped frames after startup, `mistimed-frame-count` not increasing
after startup, `avsync` within ±0.005 s. `vsync-jitter` is recorded but
is not a pass criterion.

```sh
mpv --no-resume-playback --length=90 --term-status-msg='ratio=${vsync-ratio} jitter=${vsync-jitter} avsync=${avsync} drop=${frame-drop-count} delayed=${vo-delayed-frame-count} mistimed=${mistimed-frame-count}' <file>
```

| # | Scenario | Status |
|---|----------|--------|
| 1 | Linux KDE Wayland, 23.976 fps, full config | **Passed 2026-11-19** (Black Clover S02E05, 60+ s) |
| 2 | Linux, Anime4K A+A | Delayed 0 / drop 0 in a 45 s isolation run and a short Kusuriya run; full 60 s run pending |
| 3 | Windows nv12 | **Pending** — not measured |
| 4 | Windows p010 | **Pending** — not measured |
| 5 | Streaming (`[protocol.https]` keeps `display-resample`) | Pending |
| 6 | X11 session (`[wayland-144hz-fix]` inactive) | Pending |

Results: [spec.md — Measurement results — 2026-11-19](spec.md#measurement-results--2026-11-19).

### Automated verification

```bash
python -m unittest tests.test_audit_patches
# test_spec_004_playback_performance_profiles asserts, as strings:
# tscale = linear + video-timing-offset = 0.01 in [live-action]/[anime],
# the display-fps range and `display-fps-override = 143.981` +
# `profile-restore = copy` in [wayland-144hz-fix].
```

It does not measure any timing property, and it does not reflect the
runtime `tscale` set by `smart_motion.lua`.

## Open items

- **smart_motion.lua needs its own spec or a section here.** It sets
  `tscale` (from `default_tscale`, currently `oversample`),
  `video-sync` and `interpolation` at runtime, overriding both the
  profiles' `tscale=linear`. *The VRR override was fixed 2026-11-20
  (`1a38d97`): VRR mode seeds `smart_motion.conf` with `enabled=no`.*
- **Windows verification pending.**
- **First-run delayed 8–9 / drop 1**: not reproduced; re-check with a
  cold shader cache.

## Complexity Tracking

No constitution violations. Playback changes are config-only; the deployer's token substitution is pre-existing.
