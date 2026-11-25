# Feature Specification: Player UI Styles and Themes

**Feature Branch**: `006-player-ui-themes` (directory name only: no branch was created; the maintainer commits to `main`)
**Created**: 2026-11-23
**Revised**: 2026-11-23, after EGM review round 1 (reports in `.egm/006/`; all recommended options accepted, dark and black both kept)
**Status**: Ready for planning
**Input**: User description: "Player UI styles and themes in uosc, switchable from inside mpv. Three styles (calm, bar, focus) from uosc options only, no uosc patch; an Appearance menu (Style, Background, Accent, Size) applied while playing and kept across restarts and `mpv-config update`; a grouped More menu; an optional patched 'capsule' style later. Playback must not be affected (spec 004 method); KDE Wayland and Windows; text contrast at least 4.5:1."

## Vocabulary

- **Style**: the layout of the bottom controls and timeline: `calm`, `bar` or `focus`.
- **Background**: the colour of UI surfaces (menus, button boxes, tooltips): `dark`, `black` or `slate`.
- **Accent**: the colour of every control icon, the timeline fill, the volume and speed fills and the highlighted menu row: `amber`, `teal`, `violet`, `rose` or `white`. uosc has one colour for all of these (its `foreground`), so the accent cannot be limited to one button.
- **Size**: `comfortable` or `compact`.
- **Look**: one value of each of the four settings. Default look: calm, dark, amber, comfortable.
- **More menu**: the menu opened by the More button in the controls. Today that button opens uosc's built-in default menu.
- **Theme script**: the new first-party mpv script that owns the looks, applies them, saves the choice and builds the More menu.
- **US*n*-*m***: User Story *n*, acceptance scenario *m*.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Three built-in styles (Priority: P1)

The user opens a video and sees a calm, modern layout instead of today's row
of about 17 buttons. A few controls sit at the left and right, the timeline
is a thin line until the pointer comes near, and every icon uses one accent
colour. Two other styles exist for other tastes.

| Style | Left / centre | Right | Timeline | Button boxes |
|---|---|---|---|---|
| **calm** (default) | prev, play/pause (round icon), next, on the left | speed, subtitles, audio, conditional controls, playlist, More, fullscreen | a 3 px line when the controls are hidden; grows to full size when the pointer comes near | none |
| **bar** | as calm | as calm | as calm | every button sits on a filled box (opacity 0.92); in windowed mode the controls stay visible |
| **focus** | prev, play/pause, next, centred exactly in the window | playlist, More, fullscreen | as calm | none |

"Conditional controls" are stream quality and download (streams only), video
track (several video tracks) and editions (several editions), with today's
conditions. In focus they, and subtitles, audio and speed, are reached from
the More menu (US3). The times stay at the two ends of the timeline in every
style. The volume control stays at the right edge.

Built from uosc options only; the parts that need a uosc patch are listed
under [Not in this spec](#not-in-this-spec).

**Why this priority**: The look is the feature.

**Independent Test**: Deploy with the default look, open a local video, and
compare the controls with the calm row. Set each other style and compare
again. Check that the uosc files are byte-identical to a deploy from the
commit before this feature (SC-006).

**Acceptance Scenarios**:

1. **Given** a fresh install, **When** a video plays and the pointer moves to the bottom, **Then** the calm layout is shown, with icons in amber on no box.
2. **Given** calm, **When** the controls hide, **Then** a 3 px progress line stays at the bottom; **When** the pointer comes near the bottom, **Then** the timeline grows and shows the times at both ends.
3. **Given** bar in a window, **When** the pointer leaves the window, **Then** the controls stay visible, each button on its filled box.
4. **Given** focus, **When** the controls are shown, **Then** only prev, play/pause, next, playlist, More and fullscreen are visible, and the play/pause centre is within 1 px of the window centre.
5. **Given** any style and a stream, **When** the controls are shown, **Then** stream quality and download appear (calm, bar) or are listed in the More menu (focus).
6. **Given** any style, **When** mpv is idle with no file, **Then** the controls stay visible, as today.

---

### User Story 2 - Change the look from inside mpv (Priority: P1)

The user opens More > Appearance and picks a style, background, accent or
size. The change shows at once while the video keeps playing. After
restarting mpv, and after `mpv-config update`, the same look is there.

**Why this priority**: Without it, changing the look means editing a config
file, which this project avoids.

**Independent Test**: With a video playing, pick every value of every setting.
Each is visible within 1 second, with no pause, seek or reload. Restart mpv,
run `mpv-config update`, restart again: the last choice is applied.

**Acceptance Scenarios**:

1. **Given** a video is playing, **When** the user opens More > Appearance, **Then** Style, Background, Accent and Size are listed, each submenu marking the current value.
2. **Given** the Appearance menu is open, **When** the user picks a value, **Then** the look changes within 1 second, playback continues, and the value is marked current.
3. **Given** a look was chosen, **When** mpv restarts, **Then** the chosen look is applied; a re-layout before the controls or timeline are first shown is acceptable.
4. **Given** a look was chosen, **When** `mpv-config update` runs, **Then** the choice is kept.
5. **Given** the saved choice is missing, unreadable or holds an unknown value, **When** mpv starts, **Then** each bad setting falls back to its default, playback starts normally, and one log warning lists the settings that fell back.

---

### User Story 3 - A grouped More menu (Priority: P2)

The More menu is a short, grouped list, so the user finds an action without
knowing its key, and focus has a mouse path to everything it hides.

```
Appearance       > Style · Background · Accent · Size
Subtitles
Audio
Stream quality                      (streams only)
Playback         > Shuffle · Loop playlist · Loop file · Speed
Picture & sound  > Anime4K mode · Stable volume · Video track · Editions
Open             > Paste link  Ctrl+V · Open file · Download video (streams only)
Full uosc menu
All shortcuts    F9
```

Rows that toggle something (shuffle, loops, stable volume) and rows that pick
a value (Anime4K mode, speed, the Appearance values) mark the current state.
Appearance is at the top level so a style change takes 4 clicks (SC-001).

**Why this priority**: Appearance (US2) lives here, and focus needs it. The
Appearance part ships with US2; the rest of the regrouping is P2.

**Independent Test**: Open More on a local file and on a stream, activate every
row, and compare each with its key or today's button.

**Acceptance Scenarios**:

1. **Given** More is open on a local file, **Then** the top level shows the rows above except Stream quality.
2. **Given** any row, **When** it is activated, **Then** it does what its key or today's button does (the "Today → after" table).
3. **Given** a local file, **When** Open is shown, **Then** Download video is not listed; on a stream it is.
4. **Given** a file with one video track and no editions, **When** Picture & sound is shown, **Then** Video track and Editions are not listed.
5. **Given** Full uosc menu is activated, **Then** uosc's built-in menu opens, with all of today's entries (chapters, screenshot, aspect ratio, audio devices, Quit and the rest).
6. **Given** All shortcuts is activated, **Then** the cheat sheet opens, as F9 does.

---

### Today → after

Where each of today's controls goes. "More" means a row of the new More menu;
"Full uosc menu" means it stays reachable through that row.

| Today | calm / bar | focus |
|---|---|---|
| Menu button (uosc default menu) | More button (new menu) | More button |
| Paste link | More > Open | More > Open |
| CC (captions / subtitles) | Subtitles button | More > Subtitles |
| Audio tracks | Audio button | More > Audio |
| Video track (several tracks) | button | More > Picture & sound |
| Editions (several editions) | button | More > Picture & sound |
| Stream quality (streams) | button | More > Stream quality |
| Download video (streams) | button | More > Open |
| Stable volume | More > Picture & sound | More > Picture & sound |
| Speed | speed slider | More > Playback |
| Shuffle, loop playlist, loop file | More > Playback | More > Playback |
| Prev, next | buttons | buttons |
| Playlist (items) | button | button |
| Fullscreen | button | button |
| (none) play/pause | new button | new button |
| uosc default-menu entries | Full uosc menu | Full uosc menu |

### Edge Cases

- **Narrow window.** uosc hides controls starting from the middle of the row
  and moving outwards. Each style places the controls that must stay (More,
  fullscreen, play/pause) at the ends or in the centred group. At 480 px wide
  and scale 1 no control overlaps another, and More and fullscreen stay visible.
- **Fullscreen.** Same look; uosc's `scale_fullscreen` still applies.
- **Menu open during a change.** The Appearance menu stays open, takes the new
  colours and size, and marks the new value.
- **Fast picks.** Each pick is applied and saved as one step, so the controls
  never show a mix of two looks, and the last pick wins.
- **Two mpv windows.** A change applies to the window it was made in; both
  save to the same file, so the last pick wins at the next start.
- **Hand-edited `uosc.conf`.** The keys the theme owns (FR-011) are replaced at
  runtime, so hand edits to them have no effect; every other key works as before.
- **The save fails** (read-only file, full disk). The change still applies to the
  running player, and one short on-screen message says it was not saved.
- **uosc missing or fails to load.** The theme script loads without errors and
  does nothing.
- **A uosc pin bump.** Covered by FR-016.

## Requirements *(mandatory)*

### Functional Requirements

**Styles and palette (US1)**

- **FR-001**: The system MUST provide calm, bar and focus as in the US1 table.
- **FR-002**: Every look MUST be made from uosc options only. uosc code MUST NOT change (C-001).
- **FR-003**: Background MUST offer dark `#0E0F12`, black `#000000` and slate `#1C2430`. One colour per background is used for every UI surface, including menus.
- **FR-004**: Accent MUST offer amber `#F2B544`, teal `#5EEAD4`, violet `#A78BFA`, rose `#FB7185` and white `#F2F2F3`. Text on a highlighted (accent-filled) menu row MUST use `#000000` (decided 2026-11-23: `#141414` reaches only 4.49:1 for violet on black with uosc's real row opacity). The icon on an active button is drawn by uosc in the Background colour.
- **FR-005**: These values MUST be the same in every look: text `#F2F2F3`, openings and endings timeline ranges `#7CC4FA`, error `#F87171`, success `#34D399`, menu row height 40 px, corner radius 10 px. Muted text is uosc's text colour at its built-in reduced opacity (uosc has no separate muted colour); `#A1A1AA` is the reference used for the contrast check of muted text.
- **FR-006**: The conditional controls MUST keep today's conditions (US1 table).
- **FR-007**: Size MUST set the uosc button box (its click area): 44 px comfortable, 36 px compact, which draws icons of about 31 and 25 px. The plan lists the spacing, margin, timeline and progress values for each size. Menu rows stay 40 px in both sizes.
- **FR-008**: The stream-quality button, which sizes its label from the uosc button size, MUST redraw at the new size when Size changes.

**Switching and saving (US2)**

- **FR-009**: The More menu MUST contain Appearance with Style, Background, Accent and Size, each marking the current value.
- **FR-010**: A pick MUST be saved first and then applied to the running player as one options update, within 1 second, without pausing, seeking or reloading. uosc 5.13.0 applies runtime option changes (see Research).
- **FR-011**: The theme MUST own these uosc keys and write each as a complete value: `controls`, `color` (all sub-keys, including the non-theme ones shipped today such as `curtain` and `match`), `opacity` (all sub-keys), `controls_size`, `controls_spacing`, `controls_margin`, `controls_persistency`, `timeline_size`, `progress`, `progress_size`, `menu_item_height`. The fixed startup-only keys `border_radius` and `chapter_ranges` MUST be set before uosc starts (they are not re-read at runtime). The theme MUST NOT change `proximity_out`, `destination_time` or `top_bar_controls` at runtime.
- **FR-012**: The choice MUST be saved in `script-opts/ui_appearance.conf` as four `key=value` lines, written in place (as `profile_picker.lua` writes `anime4k.conf`), and applied when the theme script loads.
- **FR-013**: A missing, unreadable or invalid saved choice MUST fall back to the default per setting, with one log warning per start listing the settings that fell back, and MUST NOT block startup or playback.
- **FR-014**: A failed save MUST NOT undo the change in the running player; it MUST show one short on-screen message.

**Deployment**

- **FR-015**: A fresh install MUST get the default look. `mpv-config update` MUST keep an existing `ui_appearance.conf`. An existing install without one MUST move to the default look on its first update. `uosc.conf` and `input.conf` MUST NOT be edited by the deployer for this feature. A plain `mpv-config uninstall` removes `ui_appearance.conf` with the rest of `script-opts/`, as it does for the other saved player choices.
- **FR-016**: A test MUST check, against a committed facts file extracted from the pinned uosc 5.13.0 (option names and defaults, colour and opacity sub-keys, binding names, the SHA-256 of `main.lua`; no copy of `main.lua` is committed, decided 2026-11-24), that every uosc option and sub-key a look sets exists and that uosc still registers its runtime option handler. The weekly uosc release check (spec 005, C-008) MUST regenerate those facts from the downloaded release and run the same check, and a pin bump MUST NOT land unless it passes.

**More menu (US3)**

- **FR-017**: The theme script MUST build the More menu and open it through uosc's menu interface; the More button in `controls` MUST open it. `input.conf` gets no `#!` lines.
- **FR-018**: Every More row MUST run the same command as its existing key or button. Only Appearance is new behaviour.
- **FR-019**: Rows that do not apply to the current file (Stream quality and Download video on local files, Video track with one video track, Editions with one edition) MUST NOT be listed.
- **FR-020**: The More menu MUST end with "Full uosc menu", which opens uosc's built-in menu, and "All shortcuts" with the hint F9.

**Playback, platforms, contrast**

- **FR-021**: Showing, hiding and switching looks MUST NOT affect playback (C-003, SC-002).
- **FR-022**: The feature MUST work on Linux KDE Wayland and Windows (C-002).
- **FR-023**: Contrast, computed with the opacity uosc really draws at over the selected Background, MUST be at least 4.5:1 for titles and icons and at least 3:1 for hints and muted text, for all 15 background × accent pairs. This covers: text on Background, accent icons on Background, `#000000` on the accent, and Background on the accent (active button icons). Exception (decided 2026-11-23): hints on a highlighted row reach only 2.2 to 3.1:1, because uosc draws hints at a fixed 0.5 opacity that no option changes; the More and Appearance menus put no hint on a row they mark active, and uosc's own menus are exempt. No ratio is claimed for text drawn over video (calm and focus); uosc's text outline keeps it readable.

### Constraints *(stakeholder-mandated)*

- **C-001 (no uosc patch)**: uosc stays as deployed today: upstream 5.13.0 plus the existing patches (spec 005 reorder, timeline thumbnail, top bar).
- **C-002 (cross-platform parity)**: the same looks on Windows and Linux ([constitution II](../../.specify/memory/constitution.md)).
- **C-003 (measurement)**: frames are measured with the [spec 004 Verification Method](../004-playback-performance/spec.md#verification-method).
- **C-004 (repo rules)**: Python uses `pathlib`, never `shell=True`; no secrets or personal paths; both test suites stay green.

### Research: uosc 5.13.0 (2026-11-23, read from source)

- **Runtime options.** `opt.read_options(options, 'uosc', handle_options)` registers an update handler. When `script-opts` changes `uosc-` keys, it re-runs `update_config()` (colours, opacity, persistency) and calls `on_options` on every element: Controls rebuilds its list, Timeline, Volume, Speed, TopBar and Menu recompute their sizes. Read from source only; the plan includes a live check on mpv 0.40 or newer.
- **Not live.** `border_radius` becomes `state.radius` only when the display size changes. `chapter_ranges` is parsed once into `config` at startup. `proximity_out`, `destination_time` and `top_bar_controls` are normalised only at startup.
- **One colour for icons.** A control's icon colour is `foreground`; no control kind takes its own colour. An active button fills its box with `foreground` and draws its icon in `background`.
- **Layout.** All `command`, `cycle` and `button` controls have the same size; only `speed` takes a scale. Exactly two `space` items centre the middle group absolutely. The timeline is always below the controls, and no control draws text.
- **Menus.** Any `#!` line in `input.conf` replaces uosc's whole default menu, and those rows are built once and cached. Menus sent by a script with `open-menu` can mark rows `active` and are rebuilt every time they open; `player-toolbar.lua` already uses this.
- **Round play/pause.** The `pause_circle` and `play_circle` icons exist in uosc's icon font.

### Key Entities

- **Look**: style, background, accent, size. Saved by the theme script; shipped with defaults.
- **Style definition**: the uosc option values one style sets (FR-011). Fixed in the theme script.
- **Palette**: the fixed colours (FR-005) plus the chosen background and accent.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From a playing video, a style change takes at most 4 clicks (More, Appearance, Style, value) and shows within 1 second.
- **SC-002**: In a 60-second session with a 23.976 fps file, during which the look is changed 20 times (every value of every setting at least once) and the controls are shown and hidden repeatedly, spec 004's full pass table holds (delayed, dropped, mistimed, vsync ratio, A/V sync within ±5 ms). On KDE Wayland at 143.98 Hz the delayed and dropped counts are 0. On Windows, where spec 004 has not yet passed, the run with switching is no worse than a run without switching, same file and machine.
- **SC-003**: After 10 restarts and 2 `mpv-config update` runs, the last chosen look is applied every time.
- **SC-004**: An automated test computes the FR-023 pairs with uosc's real opacity values and passes for all 15 background × accent pairs.
- **SC-005**: An automated test checks that every More row's command equals an existing binding, button command or uosc binding (FR-018), and that conditional rows follow FR-019.
- **SC-006**: Every uosc file is byte-identical to a deploy from the commit before this feature.
- **SC-007**: An automated test generates the options of every look and checks each against the US1 table and FR-011 (owned keys only, complete `color` and `opacity` values).
- **SC-008**: An automated test of the deployer shows: a fresh install gets `ui_appearance.conf` with the defaults; an update keeps a changed one; an update of an install without one adds the defaults (FR-015; `mpv-config update` needs a seeding migration for this, plan).
- **SC-009**: Both test suites pass.

## Not in this spec

- The bar band behind the controls, a timeline at the top of the band, "elapsed / total" text among the controls, a larger play/pause, and a "capsule" style: they need a uosc drawing patch and may follow in their own spec under spec 005's patch rules.
- A separate menu shade per background (uosc has one background colour).
- A higher opacity for hints on highlighted menu rows (needs the same uosc patch).
- A "classic" style that keeps today's look.

## Assumptions

- uosc stays pinned at 5.13.0 (spec 005, C-007). mpv 0.40 or newer.
- Existing installs move to the default look on update; the CHANGELOG and README say so.
- Branch: the speckit `before_specify` hook was not run; the maintainer commits to `main`, and `pwsh` is not installed.
- Numbering: this feature keeps 006, as the maintainer asked. Spec 005's "Deferred to spec 006" thumbnail section becomes "Deferred to spec 007" in the same commit as this spec.
