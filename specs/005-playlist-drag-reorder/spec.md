# Feature Specification: Playlist Drag-to-Reorder

**Feature Branch**: `005-playlist-drag-reorder` (directory name only: no branch was created; the maintainer commits to `main`)
**Created**: 2026-11-20
**Status**: Draft
**Input**: User description: "A YouTube Music-style playlist menu in uosc. User Story 1 (P1): drag to reorder with a drag handle, held-item highlight, drop indicator, edge auto-scroll, playlist-move on release without interrupting playback, Esc to cancel, existing keyboard reordering and move buttons kept. User Story 2 (P2): a small square thumbnail next to every visible item (cover art, video frame, yt-dlp thumbnail, or a generic icon), drawn as mpv overlays that follow the menu, generated asynchronously and cached on disk. Playlist menu only; uosc changes only as an idempotent, reversible patch; playback must not be affected; Linux Wayland and Windows."
**Scope (decided 2026-11-20)**: this spec covers drag-to-reorder (User Story 1) only. Thumbnails (User Story 2) are moved to spec 007; see [Deferred to spec 007](#deferred-to-spec-007-playlist-item-thumbnails).

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
- The menu is closed during a drag (Esc, the menu key, or any other close): the
  drag is cancelled without a move.
- The window loses focus during a drag: mpv releases the held button first
  (measured: release-all sends the button-up), so the drag ends like a release
  and commits at the visible drop line, under the usual outside-the-menu rule
  (accepted 2026-11-22). If the `focused` change happens to be processed before
  that commit (it waits one event-loop turn), the drag is cancelled instead; both
  outcomes are accepted. When the video output does not report `focused`, only the
  release rule applies.
- The menu's search/filter is active: dragging is disabled, because positions
  in a filtered view do not map one-to-one to playlist positions; keyboard and
  button reordering keep their current behaviour.
- A one-item or empty playlist: no drag handle is shown.
- The pointer leaves the menu but stays inside the mpv window while dragging:
  the drop line goes to the first or last gap and the list auto-scrolls toward
  that end.
- The pointer leaves the mpv window while dragging (pointer left, or its
  coordinates are outside the window while the button is held): the drag
  continues, the drop line freezes at its last in-window position, and nothing
  auto-scrolls. Release there commits to that frozen position when `focused` is
  reported; when it is not reported, release outside the menu cancels without a
  move. Esc still cancels (decided 2026-11-21 and 2026-11-22).
- Esc, or any other menu key, while the button is still held: mpv sends the
  button-up before the key, so the release's commit waits one event-loop turn;
  the key (like a menu close or a list update) arrives within it and cancels
  without a move, and the key itself does nothing else (decided 2026-11-22).
- A non-menu key (for example Space) while the button is held: mpv sends the
  button-up first, so the drag commits at the visible drop line, then the key
  acts as usual. If the playlist changed in between, no move is made.
- The button release is never reported to mpv (for example, outside the window
  on some platform): the drag continues and the drop line stays visible, following
  the pointer back into the window; the next click drops the item there (accepted
  2026-11-22). If mpv saw the release but uosc did not, the next press cancels the
  drag instead and acts as a normal click.
- The playing item is the one being dragged: it keeps playing throughout.
- An anchor of the patch no longer matches after a uosc change: `Menu.lua` is
  not modified (FR-024).

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

FR-010 to FR-019 (thumbnails) moved to [Deferred to spec 007](#deferred-to-spec-007-playlist-item-thumbnails); the
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
- **FR-024**: Patching MUST be all-or-nothing. The patch changes one uosc file,
  `elements/Menu.lua`. `lib/menus.lua` is left untouched, because the drag handle
  is drawn by `Menu.lua` and is not an item action (decided 2026-11-21; see
  plan.md). All hunks are applied in memory, and the file is written only when
  every hunk succeeds, in one atomic replace. If any hunk fails (for example an
  anchor does not match), or the file does not hash to the pinned upstream
  bytes, the file MUST stay untouched and `mpv-config update` MUST print one
  warning naming the skipped patch and exit 0. `deploy/transaction.py` does not
  provide this, so the patch must implement it itself. That module's `replace_items` swaps whole top-level paths
  (`scripts/`, `fonts/`, ...) one rename at a time. Its docstring says a
  multi-path update is not globally atomic. The reorder patch therefore runs on
  the staged (prepared) uosc copy before `replace_items`, so the patched file
  is swapped in with the rest of `scripts/` and the existing rollback covers
  it. This also holds when nothing new was staged and the prepared copy is the
  installed one. Today's Timeline and TopBar patchers still run after
  `replace_items` has committed and write the deployed files directly; this
  spec does not change them (decided 2026-11-20, see [plan.md](plan.md#design)).

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

C-003 and C-004 (thumbnail overlays and cache) moved to [Deferred to spec 007](#deferred-to-spec-007-playlist-item-thumbnails).

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
- **SC-008**: When `elements/Menu.lua` does not hash to the pinned upstream
  bytes, or any of the patch's anchors does not match, `mpv-config update`
  completes with exit code 0. The skipped patch appears once, in the summary's
  Warnings block (not under failures). `elements/Menu.lua` is byte-identical to
  the fetched file.
- **SC-009**: The release check is tested against a fixture copy of the uosc
  5.13.0 files with one anchor deliberately broken: it fails and its message
  names the uosc version and the broken anchor. Against the unmodified 5.13.0
  files it passes.

SC-005 and SC-006 (thumbnails) moved to [Deferred to spec 007](#deferred-to-spec-007-playlist-item-thumbnails); the
numbers are not reused.

## Alternatives Considered

| Alternative | Trade-off | Outcome |
|---|---|---|
| **Do nothing**: keep Ctrl+Up/Down/PgUp/PgDn/Home/End and the move buttons | No uosc patch and no new risk. But moving an item ten places still takes ten clicks or presses, and there is no pointer-only way to move an item far (SC-001) | Rejected: the request exists because of this cost |
| **Wire the old patcher as it is** (`tools/patch_uosc_playlist_drag.py`) into the deployer | Least new code. But it breaks C-001 (unpatch is not byte-exact), FR-008 (it replaces the move buttons), FR-003 (no drop line) and FR-006 (the held-row style hides the playing highlight). It is also 684 lines and adds 200 lines to `Menu.lua` (C-002) | Rejected |
| **Rework the old patcher** to fix those four defects | Keeps its tests. But each fix touches most of its hunks: its unpatch uses whitespace-tolerant regexes, its action block replaces the buttons, and its live row swapping has to become a drop line. The result is a rewrite that keeps the old size | Rejected in favour of a new, smaller patch (decided 2026-11-20, see Prior work) |
| **Standalone playlist menu** in a separate mpv script, with no uosc patch | No dependency on uosc anchors. But it duplicates uosc's menu rendering, theming, search and keyboard handling, and leaves two different playlist menus in the player | Rejected: much more code, and an inconsistent UI |
| **Fork uosc** | Full control. But every upstream release has to be merged by hand, which is a far larger maintenance cost than one pinned patch | Rejected |
| **Upstream the feature to uosc** | Best long-term outcome, with no patch to maintain. But its timing and acceptance are outside this project's control | Not rejected: it can be pursued in parallel, and the patch is retired if upstream ships it |
| **Whole-row drag** (the 2026-09-09 design's free drag) | No handle to aim at. But uosc already uses press-and-drag on a row to scroll the menu, so one gesture would mean two things (FR-002, acceptance 3) | Rejected: drag only from the handle |
| **Live reordering while dragging** (rows swap as the pointer moves, as in the old patcher) | Direct feedback. But it needs either one `playlist-move` per swap, which breaks FR-005's single move and churns the playlist observers, or a local reorder that has to be undone on cancel and re-synced if the playlist changes | Rejected: the list stays still, and a drop line shows the target (FR-003) |
| **Patch after `replace_items`**, the way the Timeline and TopBar patchers do | Matches existing code. But it writes live files with no rollback, and leaves the manifest hashes describing unpatched bytes | Rejected (FR-024) |
| **uosc unpinned**, or **pinned without a release check** | Covered under "uosc pinning" | Rejected there |

Thumbnail alternatives (overlays versus ASS, disk versus memory cache, stream
thumbnail sources) belong to spec 007.

## Risks and Mitigations

| Risk | Impact | Mitigation | Ids |
|---|---|---|---|
| A new uosc release changes an anchor | The patch cannot apply after a pin bump | uosc is pinned. The weekly release check names the version and the broken anchor. The pin is only bumped after that check passes | C-007, C-008, C-009, SC-009 |
| Upstream re-publishes the pinned tag with different bytes | The patch may land on code it was not written for | Before patching, the deploy checks the SHA-256 of `elements/Menu.lua` against the pinned 5.13.0 value (see Security and Privacy). A mismatch skips the patch with one warning and leaves the file as downloaded | C-001, FR-024, SC-008 |
| A partial write of the patched file | uosc is left half-patched and may error at startup | The patch changes one file. It is written to a temporary file in the same directory and then swapped in with one atomic replace. A failed write leaves the original untouched and becomes one warning | FR-024 |
| A failure during `replace_items` | Live `scripts/` mixes old and new files | The patched file travels inside the `scripts/` swap, so the existing recovery restores the old directory | FR-024 |
| A Windows checkout converts line endings (`core.autocrlf`) | The fixtures and the inserted Lua become CRLF. Anchors stop matching, or the patched file gets mixed line endings | `.gitattributes` marks the fixtures `-text` and the payload `eol=lf`. The patcher reads and writes bytes only. A test fails on any `\r` | C-001, FR-022 |
| The drag code hides the playing marker | The user loses track of the playing item | No hunk touches the highlight code. The held style is drawn on top. Python and Lua tests guard both | FR-006 |
| Press-and-drag on a row conflicts with drag-to-scroll | Accidental reorders | Drag starts only from the handle, past a 4 px threshold. Elsewhere, rows scroll as today | FR-002 |
| The button release is lost outside the window, or focus is lost | A drag stays half-held, and a later click commits a move the user never made | When the platform reports the button-up, the session's `cursor:on('primary_up')` handler receives it wherever it happens; the commit waits one event-loop turn so Esc, a close or a list update can cancel it. Outside the menu it commits only when `focused` is reported. If mpv never gets the release, the drag stays visibly active and the next click drops at the visible drop line (accepted). Focus loss while held commits at the visible drop line (accepted). To be checked by hand on KDE Wayland and Windows (quickstart §4 step 6) | FR-007 |
| The playlist changes mid-drag | A move to a stale index | Any list update cancels the drag with no move | FR-007 |
| Auto-scroll rendering costs frames | Delayed or dropped frames | Per-frame work happens only while the pointer is in an edge zone during a drag, and SC-003 measures it on both OSes | FR-020, SC-003 |
| The scheduled release check stops running (GitHub disables scheduled workflows in public repos with no activity for 60 days) or hits the API rate limit | Breakage goes unnoticed until a manual bump | The job also has `workflow_dispatch`, and C-009 requires a passing run before any bump. It sends `GITHUB_TOKEN` to the API | C-008, C-009 |
| The CI download hangs or trickles | The job burns minutes and reports nothing useful | One 120 s monotonic deadline across all reads, headers included (a socket timeout set to the remaining time before each read, plus a watchdog that closes the socket at the deadline), with step and job timeouts as a backstop. Exit 2 with a message naming the seconds and the URL | C-008 |
| Someone edits a fixture to make a test pass | The tests stop proving anything about real uosc | A test pins the fixture SHA-256 to the upstream values | SC-009 |
| The old patcher is left installed | Two drag implementations or conflicting markers | C-006 removes it. A uosc copy carrying any unknown marker is skipped with a warning, not patched over | C-006 |

## Security and Privacy

**Spec 005 (this feature)**

- **Downloaded uosc release, checked before patching.** uosc comes from
  `api.github.com` and GitHub release downloads over HTTPS, pinned to tag `5.13.0`
  (C-007). The fetcher's existing archive limits apply: size, member count, and
  safe member names. Before the patch writes anything, the deploy checks:
  (1) the SHA-256 of `elements/Menu.lua`, the only file the patch changes,
  matches the value recorded for upstream 5.13.0
  (`0cbc42afbe72f3f76f069995744de1e772d706445ed7987d1bffaafed50f2f49`); for an
  already patched copy, the check runs on the unpatched form; and (2) every anchor
  matches exactly once. If either check fails, the patch is skipped with one
  warning and the files are left as downloaded (SC-008). On a pin bump (C-009),
  the maintainer records the new hashes together with the fixture refresh.
- **Release check in CI.** It runs with `permissions: contents: read`. It sends
  `GITHUB_TOKEN` (or `GH_TOKEN`) only to `api.github.com`. It keeps the zip in
  memory, reads only `elements/Menu.lua`, and never writes, imports or executes
  anything from it. One 120 s deadline covers all of its downloads.
- **Untrusted playlist entries.** The drag code passes only integer indices to
  mpv (`playlist-move`). Titles, paths and URLs are never put into a command,
  file name or subprocess. No network access is added.
- **No new data at rest.** The only bytes written are the patched uosc file and
  the file hashes in the existing `.deploy.lock.json`.

**Spec 007 (thumbnails): requirements carried forward.** These are recorded here
because the original request included thumbnails. Spec 007 MUST meet them or
replace them with stronger ones:

- **Requests to YouTube's image servers.** Each YouTube item that needs a
  thumbnail costs one HTTPS request to YouTube's image host, keyed by the video
  ID. That request shows Google the user's IP address and the IDs in the
  playlist, including items the user never plays. Spec 007 MUST:
  - fetch only for rows that are visible;
  - fetch each video ID at most once, then serve it from the disk cache;
  - send no cookies and no referrer, and a generic user agent;
  - fetch only from the fixed thumbnail host, never from a URL taken from the
    playlist;
  - provide an option to turn YouTube thumbnail fetching off, so items fall back
    to the generic icon.

  Items from other sites never cause a request (FR-018).
- **The cache shows watch history.** Cached pictures and their file names show
  what was in the user's playlists. Spec 007 MUST:
  - keep the cache under mpv's cache directory (`~~cache/`, C-004) in its own
    subfolder, and state the resolved path for Linux and Windows;
  - name files by a hash of the source, not by title or path;
  - enforce a size limit, removing the least recently used first (the working
    number is 100 MB);
  - write files atomically, so two mpv instances cannot leave partial images;
  - document how to clear the cache. Deleting the subfolder is always safe, and
    `mpv-config uninstall` removes it.
- **Local frame grabs.** Paths from the playlist reach the frame extractor
  (`ffmpeg` or `mpv`) only as list arguments, never through a shell.

## Assumptions

- The drag threshold is 4 pixels of pointer movement; the auto-scroll edge zone is
  one row high at each end of the menu.
- Dragging with a touch screen or pen is out of scope for this version; it works
  only if mpv reports it as a mouse drag.
- uosc 5.13.0 (installed 2026-11-20) is the baseline the patch is designed against.
- mpv 0.40 or newer (the template's existing floor) is assumed.
- Branch: the speckit `before_specify` hook would create a feature branch; it was
  not run, because the maintainer commits directly to `main`.

## Deferred to spec 007: playlist item thumbnails

(Renumbered 2026-11-23: this was "spec 006" until spec 006 became player UI styles and themes.)

Decided 2026-11-20: thumbnails (the former User Story 2, P2) are not part of
spec 005. Spec 007 starts from what is recorded here and must answer the open
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
   spec 007 commits to overlays.
