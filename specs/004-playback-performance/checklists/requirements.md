# Specification Quality Checklist: Playback Performance

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-04-26
**Reviewed against code**: 2026-11-19 (spec Status: Implemented — verified on Linux/Wayland 2026-11-19; Windows verification pending)
**Feature**: [spec.md](../spec.md)

## Content Quality

- [ ] No implementation details (languages, frameworks, APIs) — FALSE: names mpv options, `profile-cond`, and file paths
- [x] Focused on user value and business needs
- [ ] Written for non-technical stakeholders — FALSE: written for the maintainer, in mpv terms
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable (manual runs of the `--term-status-msg` command in spec.md on a 143.98 Hz monitor; covered by the 2026-11-19 Linux/Wayland runs)
- [ ] Success criteria are technology-agnostic (no implementation details) — FALSE: SC-004 names `config/mpv.conf.template` and the deployer
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [ ] All functional requirements have clear acceptance criteria — FR-002 is deferred and has none
- [x] User scenarios cover primary flows
- [ ] Feature meets measurable outcomes defined in Success Criteria — Linux/Wayland met (SC-001, 2026-11-19); Windows (SC-002, SC-003) not measured yet; SC-005 not yet confirmed over 60 s; SC-006 (X11) not measured
- [ ] No implementation details leak into specification — FALSE: FR-001, FR-003, FR-006 name options and files

## Notes

- Items were re-evaluated against the code on 2026-11-19; the original "all passed" claim was not accurate, so the false ones are unticked.
- The spec references mpv-specific terminology (VSync Ratio, jitter, pixel formats) because these are the observable metrics users check. Measuring them is a manual step on the maintainer's 143.98 Hz monitor with the command in spec.md. `vsync-jitter` is recorded but is not a pass criterion.
- **Windows has not been measured yet.** Every Windows-specific item stays open until it is.
- FR-003 supports Constitution Principle I (Boundary Separation): playback fixes stay in `config/mpv.conf.template`; the deployer only fills `{{VIDEO_SYNC}}`, `{{INTERPOLATION}}` and resolves the Wayland GPU context.
- FR-006 (both platforms, `profile-cond` / template tokens) supports Constitution Principle II (Cross-Platform Parity). FR-005 is the streaming-profile requirement; it does not relate to Principle II.
- Edge cases cover VRR (opt-in via `--display-mode vrr`), X11 sessions and driver evolution. The nv12 + AV1 edge case is deferred with FR-002 / User Story 4.
