# Specification Quality Checklist: Playlist Drag-to-Reorder

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-20
**Feature**: [spec.md](../spec.md)

## Content Quality

- [ ] No implementation details (languages, frameworks, APIs) — see Notes 1
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain — resolved 2026-11-20 (Prior work decision + C-006, uosc pinning C-007 to C-009; FR-018 moved to the spec 007 section)
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [ ] Success criteria are technology-agnostic (no implementation details) — see Notes 2
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [ ] No implementation details leak into specification — see Notes 1

## Notes

1. Accepted deviation, not a defect to fix. The maintainer's request fixes
   technical constraints: the uosc patch rules, the uosc pin and release check,
   and the spec 004 measurement. These are kept out of the user story and
   collected under "Constraints" and "uosc pinning", where the plan must honour
   them. The Deployment requirements FR-023 and FR-024 name `mpv-config update`,
   `deploy/deployer.py`, `deploy/transaction.py` and the two uosc files, because
   the maintainer defined them in those terms.
2. SC-003 names the spec 004 frame counters. SC-008 names `mpv-config update`
   and uosc, and SC-009 names the release check and its fixture. All three are
   how the maintainer verifies the outcome and are kept on purpose.
3. Validation run 1 (2026-11-20): all other items pass; three clarifications open.
4. Validation run 2 (2026-11-20): the maintainer answered all three questions:
   - Stream thumbnails: YouTube items by video ID, other items only if known from
     playback, never yt-dlp per row.
   - The old patcher: replace it, keep the move buttons, and retire it afterwards.
   - uosc: pin it to 5.13.0, with a scheduled release check and manual bumps.

   No markers remain. Open EGM review findings are in `.egm/`.
5. Validation run 3 (2026-11-20), after the EGM Stage 8 decisions:
   - Thumbnails were split out into "Deferred to spec 007". That section holds
     the request, FR-018, C-003, C-004, the edge cases, the former SC-005 and
     SC-006, and three open questions. The removed IDs are not reused.
   - The pin is now concrete: the registry stores tags as upstream writes them,
     so uosc's pin is `"5.13.0"` without a `v` prefix.
   - C-008 names its release source (the GitHub releases API, then `uosc.zip`).
   - SC-009 is testable with a fixture that has one anchor broken.
   - FR-023 and FR-024 were added; FR-024 records that `deploy/transaction.py`
     does not provide all-or-nothing patching.

   Results: "Scope is clearly bounded" now holds for one story. FR-023 and
   FR-024 are testable: FR-023 by running the update twice, FR-024 and SC-008
   by breaking one anchor in one file. No new markers. The three unchecked items
   are the accepted deviations in Notes 1 and 2.
