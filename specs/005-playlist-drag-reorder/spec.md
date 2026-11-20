# Feature Specification: Playlist Drag-to-Reorder

**Feature Branch**: `005-playlist-drag-reorder` (directory name only: no branch was created; the maintainer commits to `main`)
**Created**: 2026-11-20
**Status**: Draft
**Input**: User description: "A YouTube Music-style playlist menu in uosc. User Story 1 (P1): drag to reorder with a drag handle, held-item highlight, drop indicator, edge auto-scroll, playlist-move on release without interrupting playback, Esc to cancel, existing keyboard reordering and move buttons kept. User Story 2 (P2): a small square thumbnail next to every visible item (cover art, video frame, yt-dlp thumbnail, or a generic icon), drawn as mpv overlays that follow the menu, generated asynchronously and cached on disk. Playlist menu only; uosc changes only as an idempotent, reversible patch; playback must not be affected; Linux Wayland and Windows."
**Scope (decided 2026-11-20)**: this spec covers drag-to-reorder (User Story 1) only. Thumbnails (User Story 2) are moved to spec 006; see [Deferred to spec 006](#deferred-to-spec-006-playlist-item-thumbnails).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Drag a playlist item to a new position (Priority: P1)

The user opens the playlist menu and wants episode 7 to play next. They hover
over episode 7, grab the drag handle (≡) that appears on that row, drag it
up, and see a line showing where it will land. Near the top edge of the menu
the list scrolls by itself so they can reach positions that were off-screen.
They release, and the item now sits where the line was. The video that was
playing keeps playing without a pause or a reload, and the "playing" marker is
still on it. If they change their mind mid-drag, Esc puts everything back.

Dragging anywhere other than the handle still scrolls the menu, exactly as
today, and the existing keyboard shortcuts and move-up/move-down buttons keep
working.

**Why this priority**: Reordering is the core of the request and is useful on
its own. Today, moving an item ten places means ten clicks on a small arrow or
ten key presses.

**Independent Test**: With a 30-item local playlist playing item 5, drag item
20 to position 2 and confirm the new order, uninterrupted playback of item 5,
and the playing marker on item 5.

**Acceptance Scenarios**:

1. **Given** the playlist menu is open, **When** the pointer hovers a row,
   **Then** a drag handle (≡) is shown on that row only.
2. **Given** a row's drag handle is pressed and the pointer moves, **When** the
   pointer moves up or down, **Then** the held row is highlighted and a
   drop-indicator line marks the gap where it will land.
3. **Given** the pointer is pressed on a row outside the handle, **When** it
   moves vertically, **Then** the menu scrolls as it does today and no reorder
   starts.
4. **Given** a drag is in progress, **When** the pointer enters the top or
   bottom edge zone of the menu, **Then** the list scrolls toward that edge,
   faster the deeper the pointer is in the zone, and stops at the first or
   last item.
5. **Given** a drag is in progress, **When** the button is released, **Then**
   the item is moved to the indicated position in mpv's playlist with a
   single move, and the menu shows the new order.
6. **Given** the item being played is moved, or other items are moved around
   it, **When** the move completes, **Then** playback continues without a
   pause, seek or reload, and the playing marker stays on the same item.
7. **Given** a drag is in progress, **When** Esc is pressed, **Then** the menu
   shows the original order and the playlist is not changed.
8. **Given** the playlist menu is open, **When** the user presses Ctrl+Up/Down,
   Ctrl+Home/End or Ctrl+PgUp/PgDn, or clicks the move-up/move-down buttons,
   **Then** items move exactly as they do today.

---

### Edge Cases

- A drag is released on the item's own position, or the pointer barely moves:
  nothing is moved (a press shorter than the drag threshold is a click, not a
  drag).
- The playlist changes while a drag is in progress (a file ends and the next
  one starts, an item is added or removed by another script, the playlist is
  shuffled): the drag is cancelled without a move and the menu refreshes.
- The menu is closed during a drag (Esc, the menu key, or the window losing
  focus): the drag is cancelled without a move.
- The menu's search/filter is active: dragging is disabled, because positions
  in a filtered view do not map one-to-one to playlist positions; keyboard and
  button reordering keep their current behaviour.
- A one-item or empty playlist: no drag handle is shown.
- The pointer leaves the mpv window while dragging: the drag continues while
  the button is held and ends (commits) on release, as other drags in mpv do.
- The playing item is the one being dragged: it keeps playing throughout.
- Only one of the two patched uosc files still matches its anchors after a uosc
  change: neither file is modified (FR-024).

## Requirements *(mandatory)*

### Functional Requirements

**Drag to reorder**

- **FR-001**: Each row of the playlist menu MUST show a drag handle (≡) while the
  pointer hovers that row, and only that row.
- **FR-002**: Pressing the drag handle and moving the pointer more than the drag
  threshold MUST start a drag; pressing anywhere else on a row MUST keep the
  current behaviour (click to activate, drag to scroll).
- **FR-003**: While dragging, the held row MUST be highlighted and a drop-indicator
  line MUST mark the gap where the row will land; the indicator MUST move only in
  whole-row steps.
- **FR-004**: While dragging, holding the pointer in the top or bottom edge zone of
  the menu MUST scroll the list toward that edge at a speed that grows with how
  deep the pointer is in the zone, stopping at the first or last item.
- **FR-005**: On release, the system MUST move the item to the indicated position
  with exactly one playlist move, and MUST NOT move anything when the indicated
  position is the item's own.
- **FR-006**: Moving items MUST NOT pause, seek, reload or restart the item that is
  playing, and the playing marker MUST stay on that item.
- **FR-007**: Esc during a drag MUST cancel it: the menu returns to the order it had
  when the drag started and the playlist is not changed. A drag MUST also be
  cancelled, without a move, when the menu closes or the playlist changes during
  the drag.
- **FR-008**: The existing reordering controls MUST keep working unchanged:
  Ctrl+Up/Down, Ctrl+Home/End, Ctrl+PgUp/PgDn, and the move-up and move-down
  buttons.
- **FR-009**: Dragging MUST be unavailable while the menu's search/filter is
  active.

FR-010 to FR-019 (thumbnails) moved to [Deferred to spec 006](#deferred-to-spec-006-playlist-item-thumbnails); the
numbers are not reused.

**Playback and scope**

- **FR-020**: Playback MUST NOT be affected: during drags, the counts of delayed
  and dropped video frames MUST stay at 0, measured as in spec 004 (see Success
  Criteria).
- **FR-021**: The feature MUST apply to the playlist menu only; every other uosc
  menu MUST behave exactly as before.
- **FR-022**: The feature MUST work on Linux (Wayland) and Windows.

**Deployment**

- **FR-023**: `mpv-config update` MUST apply the new uosc patch to the deployed
  uosc every time it runs, including after it has installed or updated uosc, and
  a second run on an already patched uosc MUST change nothing. Today
  `deploy/deployer.py` imports and runs only `tools/patch_uosc_timeline_thumb.py`
  and `tools/patch_uosc_topbar.py`, so the new patch must be added there.
- **FR-024**: Patching MUST be all-or-nothing. The patch MUST patch both uosc
  files it changes (`elements/Menu.lua` and `lib/menus.lua`) in memory and write
  them only when both succeed. If either fails (for example an anchor does not
  match), both files MUST stay untouched and `mpv-config update` MUST print one
  warning naming the skipped patch. This goes beyond the pattern of
  `tools/patch_uosc_timeline_thumb.py`, which changes one file.
  `deploy/transaction.py` does not provide this, so the patch must implement it
  itself. That module's `replace_items` swaps whole top-level paths
  (`scripts/`, `fonts/`, ...) one rename at a time. Its docstring says a
  multi-path update is not globally atomic. The uosc patchers run after
  `replace_items` has committed and write each deployed file directly.

### Constraints *(stakeholder-mandated; they bound the plan, not the user value)*

- **C-001 (uosc is upstream)**: uosc is fetched from its upstream release
  (`deploy/registry.py`; pinned to 5.13.0, see "uosc pinning"). Any change to uosc MUST be an idempotent
  patch with a marker, with patch and unpatch functions (unpatch restores the
  original bytes exactly) and tests, following `tools/patch_uosc_timeline_thumb.py`.
  If the patch's anchors no longer match, the deploy MUST skip it with a warning
  and leave uosc byte-identical to upstream (see FR-024).
- **C-002 (small patch)**: The uosc patch MUST be as small as possible.
- **C-005 (measurement)**: Frame counts are measured with the spec 004 method
  ([spec 004 — Verification Method](../004-playback-performance/spec.md#verification-method)).

C-003 and C-004 (thumbnail overlays and cache) moved to [Deferred to spec 006](#deferred-to-spec-006-playlist-item-thumbnails).

### Prior work

- A design for drag reordering already exists:
  [2026-09-09 design](../../docs/superpowers/specs/2026-09-09-uosc-playlist-drag-drop-design.md),
  its [plan](../../docs/superpowers/plans/2026-09-09-uosc-playlist-drag-drop.md),
  and [`tools/patch_uosc_playlist_drag.py`](../../tools/patch_uosc_playlist_drag.py)
  with [tests](../../tests/test_patch_uosc_playlist_drag.py). Checked on
  2026-11-20 against the installed uosc 5.13.0: its anchors still match and
  patching is idempotent, but (a) the deployer never applies it, (b) unpatching
  does not restore the original files byte for byte (violates C-001), (c) applied
  to uosc 5.13.0, it makes `elements/Menu.lua` 192 lines longer (200 lines added,
  8 replaced) and `lib/menus.lua` 6 lines longer (conflicts with C-002; the
  patcher script itself is 684 lines), (d) it replaces the move-up/move-down
  buttons with the drag handle (conflicts with FR-008), and (e) it has no
  drop-indicator line (the held row itself swaps places with its neighbours as
  the pointer moves; FR-003), and while the playing item is held, the held-row
  style replaces its playing highlight, so the marker is not shown during that
  drag (FR-006).
- **Decision (2026-11-20)**: replace it. A new, smaller patch implements User
  Story 1 and keeps the move-up/move-down buttons (FR-008).
- **C-006 (retire the old patcher)**: once the new patch passes its tests and
  this spec's success criteria, `tools/patch_uosc_playlist_drag.py` and
  `tests/test_patch_uosc_playlist_drag.py` MUST be removed, and the 2026-09-09
  design and plan MUST be marked superseded by this spec.

### uosc pinning (decided 2026-11-20)

The patch depends on uosc internals (menu rendering, cursor handling, row
geometry), so a new uosc release can break its anchors.

`deploy/registry.py` stores each repo's tag exactly as that repo writes it.
uosc tags have no `v` prefix: the latest upstream tag is `5.13.0` (checked with
`git ls-remote` on 2026-11-20). The `"v0.40.0"` pins in the registry belong to
`mpv-player/mpv` entries, not to uosc.

- **C-007 (pin)**: uosc MUST be pinned to 5.13.0 in `deploy/registry.py`. Its
  entry has `"pin": None` today, so this means changing it to `"pin": "5.13.0"`.
- **C-008 (release check)**: a scheduled CI job MUST read the latest release tag
  of `tomasklaen/uosc` from the GitHub releases API, download that release's
  `uosc.zip`, and run the patcher against the uosc files in it. It MUST fail with
  a message that names the uosc version and the anchor that no longer matches,
  and it MUST pass when every anchor matches.
- **C-009 (manual bump)**: the maintainer bumps the pin by hand, only after that
  job passes for the new release.

C-001's "skip with a warning" stays as a safety net (for example a pinned
release re-published upstream); with the pin in place it is not the expected
path. Rejected alternatives: keeping `pin: None` (the feature would drop out,
with a warning, whenever upstream changes an anchor) and pinning without a
release check (breakage would only surface at the next manual bump).

### Key Entities

- **Playlist item**: one entry of mpv's playlist; has a position, a source
  (local file, URL), a title, and whether it is the item playing.
- **Drag session**: a drag in progress; the held item, its starting position,
  the indicated target position, and the order to restore on cancel.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a 30-item playlist, a user moves item 20 to position 2 with one
  drag in under 5 seconds, without using the keyboard.
- **SC-002**: In 50 consecutive drags, the order after release matches the
  position shown by the drop indicator 50 times out of 50.
- **SC-003**: In a 60-second session at the maintainer's display rate (143.98 Hz)
  with a 23.976 fps file playing, during which 20 drags are made in a 200-item
  playlist (including dragging the playing item and drags that auto-scroll from
  one end of the menu to the other), the delayed-frame and dropped-frame counts
  both stay at 0 and audio/video sync stays within ±5 ms (spec 004 method), on
  Linux Wayland and on Windows.
- **SC-004**: Moving the playing item causes no audible or visible interruption:
  its playback position keeps advancing monotonically through the move, and
  mpv reports no file reload.
- **SC-007**: All existing reordering tests (keyboard and buttons) pass unchanged,
  and no menu other than the playlist changes appearance or behaviour.
- **SC-008**: When any of the uosc patch's anchors does not match, in either
  file, `mpv-config update` completes successfully, prints one warning naming
  the skipped patch, and the deployed uosc files are byte-identical to upstream.
- **SC-009**: The release check is tested against a fixture copy of the uosc
  5.13.0 files with one anchor deliberately broken: it fails and its message
  names the uosc version and the broken anchor. Against the unmodified 5.13.0
  files it passes.

SC-005 and SC-006 (thumbnails) moved to [Deferred to spec 006](#deferred-to-spec-006-playlist-item-thumbnails); the
numbers are not reused.

## Assumptions

- The drag threshold is 4 pixels of pointer movement; the auto-scroll edge zone is
  one row high at each end of the menu.
- Dragging with a touch screen or pen is out of scope for this version; it works
  only if mpv reports it as a mouse drag.
- uosc 5.13.0 (installed 2026-11-20) is the baseline the patch is designed against.
- mpv 0.40 or newer (the template's existing floor) is assumed.
- Branch: the speckit `before_specify` hook would create a feature branch; it was
  not run, because the maintainer commits directly to `main`.

## Deferred to spec 006: playlist item thumbnails

Decided 2026-11-20: thumbnails (the former User Story 2, P2) are not part of
spec 005. Spec 006 starts from what is recorded here and must answer the open
questions before it is planned.

**The request**: each visible playlist row shows a small square picture on its
left, with the row text to its right. The picture is cover art for audio files,
a frame from inside a local video (not its first frame), a stream thumbnail as
FR-018 allows, and otherwise a generic icon, which is also shown while a picture
is being prepared. The menu opens without waiting; pictures are prepared in the
background, a few at a time. Prepared pictures are cached on disk under a size
limit, least recently used removed first, and reused after mpv restarts.
Pictures follow their rows through scrolling, dragging and the open/close
animation and are never drawn outside the menu. None remain after the menu
closes or mpv quits. A failed picture keeps the generic icon and is not retried
on every open.

**Decided — FR-018 (stream thumbnails)**: Stream thumbnails MUST NOT run yt-dlp
for any row. A YouTube item MUST get the thumbnail derived from its video ID,
downloaded once and then served from the disk cache. An item from any other site
MUST show a thumbnail only if one is already known from playing that item (from
the metadata obtained when it was played); otherwise it shows the generic icon.

**Constraints carried over**:

- **C-003 (thumbnails are overlays)**: uosc menus draw only ASS text and icons,
  so thumbnails MUST be mpv bitmap overlays (`overlay-add`, BGRA). Overlay ids
  0–63 are shared by all scripts; thumbfast uses id 42, and the thumbnails MUST
  NOT use or remove an id they did not create. Thumbnail logic lives in a separate
  mpv script, not in the uosc patch (C-002).
- **C-004 (cache location)**: the disk cache MUST be under mpv's cache directory
  (`~~cache/`).

**Edge cases to cover**:

- With hundreds of items, only visible rows get pictures, and rows scrolled out
  of view drop their pending work.
- Preparation can fail or time out (corrupt file, no network, private video).
- A stream from a site other than YouTube that was never played shows the
  generic icon, and nothing is fetched for it.
- A cached picture that is deleted or corrupted is regenerated.
- thumbfast's seek-bar preview can be visible at the same time.
- Window scaling can change while the menu is open.

**Success criteria to restate**:

- Former SC-005: a 200-item menu opens within 50 ms of its time without
  thumbnails. Cached pictures appear within 0.2 s and uncached local-video
  frames within 3 s.
- Former SC-006: no captured frame shows a picture outside its row, and none
  remain after the menu has closed.
- SC-003's load gains opening and scrolling a 200-item menu of uncached items.

**Earlier working numbers**: 2 at a time, a 100 MB cache, the frame at 10% of
the duration (at least 1 s in), and slots as tall as a row and square. These are
starting points, not decisions.

**Open questions**:

1. How does the patched uosc menu report row positions (and its scroll offset
   and open/close animation state) to the thumbnail script?
2. Who shifts the row text right to make room for the picture: the uosc patch
   or the thumbnail script? Either answer has to stay within C-002.
3. Do mpv bitmap overlays draw above the uosc menu and clip correctly to it,
   including during scrolling and the fade animation? This needs a test before
   spec 006 commits to overlays.
