# Feature Specification: MPV Playback Keys & Config Tuning

**Feature Branch**: `002-mpv-playback-keys`  
**Created**: 2026-04-19  
**Status**: Draft  
**Input**: User description: "حل تعارض الاختصارات بين memo و sponsorblock، ضبط لقطات الشاشة بأعلى جودة، وتحسين تجربة يوتيوب مع cache/seeking سريع جداً"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Resolve Keybinding Conflicts (Priority: P1)

The user presses a keyboard shortcut during playback and expects exactly one action to fire. Currently, both the **memo** script and the **sponsorblock** script register default keybindings that overlap:

| Key | memo (current) | sponsorblock (current) |
|-----|----------------|------------------------|
| `h` | `memo-history` — open watch history | `upvote_segment` — upvote a SponsorBlock segment |
| `H` | *(unused)* | `downvote_segment` — downvote a SponsorBlock segment |
| `g` | *(unused)* | `set_segment` — mark segment start/end |
| `G` | *(unused)* | `submit_segment` — submit marked segment |

The conflict on `h` means pressing it may trigger the wrong action or only one of the two scripts wins unpredictably depending on load order.

**Why this priority**: A keybinding conflict can cause the user to accidentally submit data to the SponsorBlock API or lose their watch history entry. Fixing this is the highest priority because it directly affects control reliability.

**Independent Test**: Press each re-mapped key during video playback and verify that only the intended action fires. Confirm that no key triggers two scripts simultaneously.

**Acceptance Scenarios**:

1. **Given** a video is playing with both memo and sponsorblock loaded, **When** the user presses the memo history key, **Then** only the memo watch history panel opens — no SponsorBlock action fires.
2. **Given** a video is playing with both scripts loaded, **When** the user presses the SponsorBlock upvote key, **Then** only the SponsorBlock upvote action fires — memo is unaffected.
3. **Given** the user has never customized keybindings, **When** the deployer runs, **Then** all keybindings are set automatically with no conflicts between any installed scripts.
4. **Given** a fresh install, **When** the user lists all active keybindings (`--input-test`), **Then** no key appears bound to more than one action.

---

### User Story 2 — Lossless Screenshot Capture (Priority: P2)

The user takes a screenshot during playback and expects it to be saved as a lossless, high-quality image in a predictable location with a descriptive filename.

Currently, screenshots are saved as JPEG (lossy) and land in the current working directory (which may vary depending on how mpv was launched), making them hard to find.

**Why this priority**: Screenshots are a common user action. Saving them in an organized, high-quality format improves daily usability significantly.

**Independent Test**: Press the screenshot key, then navigate to the screenshot directory and confirm the file is lossless (PNG), named descriptively, and in the expected folder.

**Acceptance Scenarios**:

1. **Given** a video is playing, **When** the user presses the screenshot key (video-only), **Then** a PNG file is saved to a dedicated screenshot directory.
2. **Given** a video is playing, **When** the user presses the screenshot-with-subs key, **Then** a PNG file including rendered subtitles is saved to the same directory.
3. **Given** a screenshot is taken, **When** the user checks the filename, **Then** it contains the video name and the timestamp of the captured frame (e.g., `Dr.Stone_S04E25_00-07-32.png`).
4. **Given** the screenshot directory does not yet exist, **When** the user takes their first screenshot, **Then** mpv creates the directory automatically.

---

### User Story 3 — YouTube Playback Optimization (Priority: P2)

The user opens a YouTube link in mpv and expects:
- Video quality defaults to 1080p with the highest available bitrate for both audio and video.
- Seeking (jumping forward/backward) is near-instantaneous, matching or exceeding the experience of the native YouTube player in a web browser.
- The video begins playing within a few seconds without excessive buffering.

Currently, the default `ytdl-format` limits to 1080p but does not prioritize bitrate, and the cache/demuxer settings are not tuned for streaming.

**Why this priority**: YouTube is one of the most common use cases for mpv. A laggy seeking experience or low bitrate selection makes the user fall back to the browser, defeating the purpose of using mpv.

**Independent Test**: Open a YouTube URL in mpv, seek back and forth multiple times across the timeline, and measure responsiveness. Compare subjectively against the same video in a browser.

**Acceptance Scenarios**:

1. **Given** the user opens a YouTube URL, **When** mpv selects the format, **Then** it picks 1080p video with the highest available video bitrate and the best available audio codec (opus preferred, then aac).
2. **Given** a YouTube video is playing, **When** the user seeks 30 seconds forward, **Then** playback resumes within 1-2 seconds (no spinning or long pause).
3. **Given** a YouTube video is playing, **When** the user seeks backward to an already-buffered position, **Then** playback resumes instantly (under 0.5 seconds).
4. **Given** the user has a stable internet connection (≥10 Mbps), **When** they start a YouTube video, **Then** playback begins within 3 seconds of pressing Enter.
5. **Given** the user switches from a YouTube video to a local file, **When** the local file plays, **Then** cache settings do not negatively impact local file performance (profile-scoped).

---

### Edge Cases

- What happens when a YouTube video is not available in 1080p? → Fall back to the best available quality below 1080p gracefully.
- What happens when the screenshot directory path contains non-ASCII characters (Arabic folder names)? → The path must be handled safely via mpv's built-in `~~` expansion.
- What happens when multiple scripts register the same key and the user has a custom `input.conf`? → The deployer's `input.conf.template` must be the authoritative source; script-internal defaults are overridden.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST assign unique, non-conflicting keybindings for all installed scripts (memo, sponsorblock, autosubsync, evafast, SmartSkip).
- **FR-002**: The system MUST override script-internal default keybindings via `input.conf` so that no script's built-in defaults can cause a conflict.
- **FR-003**: The system MUST set the screenshot format to lossless PNG.
- **FR-004**: The system MUST define a fixed screenshot output directory (e.g., `~/Pictures/mpv-screenshots/`).
- **FR-005**: The system MUST configure screenshot filenames to include the video title and the frame timestamp.
- **FR-006**: The system MUST set `ytdl-format` to prefer 1080p with the highest video bitrate and best audio quality.
- **FR-007**: The system MUST tune cache and demuxer settings for YouTube/streaming to enable fast seeking (large read-ahead buffer, extended back-buffer).
- **FR-008**: YouTube-specific cache tuning SHOULD be scoped to a conditional profile (e.g., `[protocol.https]`) so it does not affect local file playback.
- **FR-009**: The system MUST document all final keybinding assignments in a human-readable reference (comment block in `input.conf` or separate doc).

### Key Entities

- **Keybinding Map**: A complete mapping of keys → actions across all installed scripts, ensuring uniqueness.
- **Screenshot Config**: Format, directory, and filename template settings in `mpv.conf`.
- **YouTube Profile**: A conditional auto-profile for streaming URLs that tunes cache, demuxer, and format selection.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero keybinding conflicts — no single key triggers more than one action across all installed scripts.
- **SC-002**: Screenshots are saved as lossless PNG files containing the video name and timestamp in the filename.
- **SC-003**: YouTube seeking (forward 30s) resumes playback within 2 seconds on a ≥10 Mbps connection.
- **SC-004**: YouTube backward seeking to a buffered position resumes within 0.5 seconds.
- **SC-005**: YouTube video playback starts within 3 seconds of opening the URL.
- **SC-006**: Local file playback performance is unaffected by YouTube-specific cache tuning.

## Assumptions

- The user has `yt-dlp` installed (handled by the 001-mpv-automation feature).
- The user's internet connection is ≥10 Mbps for YouTube streaming benchmarks.
- The screenshot directory `~/Pictures/mpv-screenshots/` is writable. If it does not exist, mpv will create it automatically.
- The `input.conf.template` managed by the deployer is the single source of truth for keybindings — users who manually edit `input.conf` accept that re-deployment may overwrite their changes.
- The memo and sponsorblock scripts support overriding their default keybindings via `input.conf` (both use `mp.add_key_binding` with named bindings).
