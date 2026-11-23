# Specification Quality Checklist: Player UI Styles and Themes

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-23
**Feature**: [spec.md](../spec.md)

## Content Quality

- [ ] No implementation details (languages, frameworks, APIs) — see Notes 1
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain — resolved 2026-11-23, see Notes 3
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [ ] Success criteria are technology-agnostic (no implementation details) — see Notes 1
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

1. Accepted deviation, as in spec 005. The maintainer defined the feature in uosc
   terms (uosc options, no uosc patch, the spec 004 measurement), so the spec
   names uosc keys, `script-opts`, the deployer and `mpv-config update`. They are
   kept in Constraints, Research, FR-011, FR-012, FR-015 to FR-017.
2. Validation run 1 (2026-11-23): two markers (US1 visuals without a patch; one
   background colour per surface). EGM review round 1 (`.egm/006/`) consolidated
   about 90 findings into 4 blockers, 9 majors and nits.
3. Validation run 2 (2026-11-23), after the maintainer accepted every recommended
   option and kept both dark and black:
   - B1: options-only styles; the patch-only visuals and capsule moved to "Not in
     this spec". B2: the accent is uosc's `foreground`. B3: the choice lives in
     `script-opts/ui_appearance.conf`. B4: the theme script builds the More menu.
   - M1 to M9 applied: "Today → after" table, existing installs move to the
     default look, owned keys (FR-011), no runtime fallback (FR-016), one options
     update per pick, real-opacity contrast (FR-023), sizes 44/36, Windows
     relative pass rule (SC-002), US4 removed.
   - Q2: one colour per background, dark `#0E0F12`. Q3: this spec keeps 006;
     spec 005's thumbnail section is now "Deferred to spec 007".
   - New, from the real-opacity contrast check: text on the accent is `#000000`
     (`#141414` gave 4.49:1 for violet on black); hints on highlighted rows are
     exempt (uosc draws them at a fixed 0.5 opacity) and the theme's menus put
     no hint on a row they mark active.
4. Contrast with uosc's real opacities (menu 0.95 over black or white video,
   hover row 0.15, active row 0.8, hints 0.5), worst pair of the 15:
   title on menu 12.07; hint on menu 4.24; title on hover row 7.72; hint on hover
   row 3.25; `#000000` title on active row 5.12; accent icon on a bar box (0.92)
   4.51; Background icon on an active button 5.74; accent icon on menu 4.96.
