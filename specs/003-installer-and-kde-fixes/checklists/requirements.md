# Specification Quality Checklist: Installer & KDE Fixes

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-04-25
**Feature**: [spec.md](../spec.md)
**Re-evaluated**: 2026-11-19 against the code (spec Status: Partially superseded — installer design replaced)

## Content Quality

- [ ] No implementation details (languages, frameworks, APIs) — FALSE: FR-001..FR-008 name files, functions and flags (`deploy/ui.py`, `os.execv`, `--break-system-packages`)
- [x] Focused on user value and business needs
- [ ] Written for non-technical stakeholders — FALSE: written for the maintainer, in package-manager and mpv terms
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [ ] Requirements are testable and unambiguous — FALSE: FR-009 ("MUST be evaluated and configured") and FR-010 ("may involve…") have no testable outcome of their own
- [x] Success criteria are measurable
- [ ] Success criteria are technology-agnostic (no implementation details) — FALSE: SC-002 names `pip list --user`, SC-003 a CLI flag, SC-006 `deploy/deployer.py`
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [ ] Scope is clearly bounded — FALSE for the as-built code: the Windows installer, uv/pipx methods, `sync-deps` and `fast_close.lua` went beyond the spec (recorded under As-built, not as requirements)
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [ ] Feature meets measurable outcomes defined in Success Criteria — SC-003 and SC-005 met; SC-001 superseded; SC-002 and SC-004 not re-measured; SC-006 partly met (O4)
- [ ] No implementation details leak into specification — FALSE: see the first item

## Notes

- The original note said all items passed on the first iteration. Re-evaluated 2026-11-19: the items marked FALSE above are unticked.
- The spec references specific file paths (e.g. `deploy/ui.py`, `deploy/registry.py`) to precisely locate problems, but does NOT prescribe implementation solutions — this is intentional for a bug-fix spec where the problem location is part of the problem description.
- FR-011 explicitly marks window snap behavior as OUT OF SCOPE with a dedicated scope boundary section.
- SC-006 now reads: KDE/Wayland behaviour is expressed in config templates; `deploy/deployer.py` only fills template placeholders per platform. This matches Principle I's rule that the deploy package fills placeholders but does not embed configuration literals. The window sizing helpers currently break it (O4).
- "Dependencies and assumptions identified" stays ticked because they were identified, but the "Rich is the only Category B dependency" assumption is no longer true (see spec.md As-built).
