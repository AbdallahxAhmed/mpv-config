# Design Spec: Toolbar Monograms, Uniform Spacing, Stable Volume & Subtitles Filtering

**Date**: 2026-09-07  
**Status**: Pending Review  
**Target Platform**: MPV on Windows (1080p 27-inch display)

---

## 1. Overview & Goals

This refinement addresses interface aesthetics, button alignment, and subtitle functionality:
1. **Centered Monograms for Audio & Quality**: Replace clunky, uncentered corner badges (`[AR]`, `[1080p]`) with sleek, centered typography monograms (`AR`/`EN` for audio, `HD`/`4K` for quality) matching YouTube and Netflix player aesthetics.
2. **Uniform Toolbar Spacing & Sizing**: Remove all irregular gaps in `controls`, enforcing a constant `controls_spacing=10` and `controls_size=32` for razor-sharp vector rendering without sub-pixel blur on 1080p 27" monitors.
3. **Intuitive Stable Volume**: Switch icon to `graphic_eq` (sound equalizer bars) representing audio dynamic range compression/leveling, verifying the `dynaudnorm+alimiter` audio filter toggle.
4. **Subtitles Focused on Arabic & English**: Filter out all 153+ irrelevant auto-translated languages so only Arabic (`ar`) and English (`en`) appear under auto-generated and auto-translated menus. Fix the `Could not load captions` (HTTP 429) error by routing subtitle downloads with `yt-dlp`'s session headers / subprocess fetch.

---

## 2. Component Design & Changes

### 2.1 Toolbar Monograms (`scripts/player-toolbar.lua`)

#### Audio Button (`button:audio-tracks`)
- **Visual Display**: Renders a clean, centered 2-letter uppercase monogram directly inside the button box (e.g., `AR` when playing Arabic, `EN` when playing English, `JA` for Japanese).
- **Fallback**: If language is undetermined or local media without language metadata, displays the centered `headphones` icon.
- **Badge**: `badge` property is set to `nil` (completely removing the offset bottom-right corner pill).
- **Tooltip**: `Audio: <Clean Language Name>` (e.g. `Audio: Arabic`).
- **Menu**: Clicking opens the deduplicated audio menu, with only clean language names and active `Current` indicator.

#### Video Quality Button (`<stream>button:stream-quality`)
- **Visual Display**: Renders a centered quality badge matching the audio monogram aesthetic:
  - Resolution >= 2160p: **`4K`**
  - 720p <= Resolution < 2160p: **`HD`**
  - Resolution < 720p: **`SD`**
- **Badge**: `badge` property is set to `nil` (no overlapping offset corner pill).
- **Tooltip**: `Video quality: <Resolution>p` (e.g. `Video quality: 1080p60`).
- **Menu**: Clicking opens the actual available video stream resolutions list (`1080p60`, `720p`, etc.) with `Current` checkmark.

#### Stable Volume Button (`button:stable-volume`)
- **Visual Display**: Icon is changed to **`graphic_eq`** (Material Icons audio equalizer bars).
- **State**: When active, highlights with the active foreground color. Tooltip reflects `Stable volume: On` vs `Stable volume: Off`.
- **Filter Graph**: Toggles `dynaudnorm=f=500:g=15:p=0.95:m=10,alimiter=limit=0.9:level=false` with label `mpv_config_stable_volume`.

---

### 2.2 Uniform Spacing & Layout (`config/script-opts/uosc.conf`)

- **Controls Layout**:
  ```ini
  controls=menu,command:content_paste:script-binding smart_paste/paste-to-open?Paste link,command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles and captions,button:audio-tracks,<stream>button:stream-quality,button:stable-volume,space,fullscreen
  ```
  - Removed all irregular `gap` entries between buttons.
  - Constant spacing is managed uniformly by `controls_spacing`.
  - `space` anchors `fullscreen` cleanly to the far right.
- **Dimensions**:
  - `controls_size=32`: Clean integer scaling for 1080p 27-inch display (96 DPI), eliminating pixelation.
  - `controls_spacing=10`: Uniform, balanced spacing between all buttons.
  - `controls_margin=8`: Clean border margin.

---

### 2.3 Subtitle Filtering & Fix for HTTP 429 (`stream_policy.lua` & `ytdl-sub-menu.lua`)

#### Filtering to Arabic & English Only
- In `scripts/modules/stream_policy.lua`:
  - When parsing `automatic_captions`, allow ONLY languages matching `ar` (Arabic) and `en` (English) or their regional variants (`en-orig`, `en-US`, `ar-EG`).
  - Creator-provided manual subtitles (`subtitles` group) remain accessible if provided by the creator.
  - The auto-translated submenu drops from 155 entries to just Arabic and English, making navigation instant and relevant.

#### Eliminating `Could not load captions` (HTTP 429)
- In `scripts/ytdl-sub-menu.lua`:
  - YouTube's `timedtext` translation endpoints reject direct unauthenticated HTTP GET requests with `HTTP 429: Too Many Requests`.
  - Instead of passing raw timedtext URLs directly to `sub-add` without headers:
    - For YouTube streams, download the selected caption (`.vtt`) using an async `yt-dlp` invocation:
      `yt-dlp --skip-download --write-auto-subs --sub-langs <lang> --sub-format vtt -o <temp_path> <url>`
      or fetch the URL with yt-dlp's extracted HTTP headers / cookies.
    - Load the downloaded local file via `sub-add <temp_path> select <title> <lang>`.
    - This completely resolves the 429 error and loads the captions reliably.

---

## 3. Migration & Upgrader Integration

- **`tools/apply_youtube_gui.py`**:
  - Update `NEW_CONTROLS` to the clean uniform layout without gaps.
  - Add previous layouts into `ACCEPTED_CONTROLS`.
  - Ensure `--apply` synchronizes updated scripts and `uosc.conf` into `%APPDATA%\mpv`.

---

## 4. Verification Plan

1. **Lua Unit Tests**:
   - `test_player_toolbar.lua`: Verify audio button publishes `AR`/`EN` centered monogram with `badge = nil`.
   - `test_player_toolbar.lua`: Verify quality button publishes `HD`/`4K` centered monogram with `badge = nil`.
   - `test_player_toolbar.lua`: Verify stable volume uses `graphic_eq`.
   - `test_stream_policy.lua`: Verify auto-translated subtitles filter to `ar` and `en` only.
   - `test_caption_menu.lua`: Verify caption loading works without 429 error.
2. **Python Unit Tests**:
   - `test_youtube_gui_upgrade.py`: Verify upgrade detection and application of uniform `controls` and 32px size.
   - `test_config.py`: Verify template configuration assertions.
3. **Live Verification**:
   - Run `python tools/apply_youtube_gui.py --config-dir "$env:APPDATA\mpv" --apply`.
   - Verify in mpv that badges are centered, spacing is uniform, Stable Volume displays `graphic_eq`, and subtitles list only Arabic and English without loading errors.
