# Design Spec: Toolbar Monograms, Uniform Spacing, Stable Volume & Subtitles Refinement

**Date**: 2026-09-07  
**Status**: Revised Specification (Incorporating Technical Review Feedback)  
**Target Platform**: MPV on Windows (1080p 27-inch display, 96 DPI)

---

## 1. Overview & Objectives

This specification refines MPV/uosc toolbar aesthetics, alignment, and subtitle fetching to deliver a clean, broadcast-grade interface on a 1080p 27" display without performance bottlenecks or visual artifacts:

1. **Centered Typography Monograms**: Replace clunky corner badges (`[AR]`, `[1080p]`) with centered 2-letter monograms (`AR`/`EN` for audio, `HD`/`4K` for quality) using explicit ASS typography and baseline optical alignment.
2. **ISO-639-2 Language Code Normalization**: Map 3-letter codes (`ara` $\to$ `AR`, `eng` $\to$ `EN`, `jpn` $\to$ `JA`) to guaranteed 2-character monograms, preventing horizontal text overflow inside 32px buttons.
3. **Widescreen & Aspect Ratio Detection**: Classify quality based on `(w >= 3840 or h >= 2160)` for `4K` and `(w >= 1280 or h >= 720)` for `HD`, ensuring 2.39:1 widescreen and ultrawide media (e.g. 1920x800, 3840x1600) are never miscategorized as SD.
4. **Uniform Toolbar Spacing & Sizing**: Enforce `controls_size=32`, `controls_spacing=10`, and eliminate all ad-hoc `gap` spacers to guarantee sub-pixel sharpness and uniform button margins.
5. **Intuitive Stable Volume**: Use `graphic_eq` (sound equalizer bars) representing audio dynamic range compression/leveling, verifying seamless live-stream filter graph reloads.
6. **Ultra-Fast, Authenticated Subtitle Fetching**:
   - Filter auto-generated and auto-translated lists down to **Arabic (`ar`)** and **English (`en`)** by default, with an expandable `"More languages..."` entry for full access.
   - Replace slow `yt-dlp` re-scraping passes with lightweight, asynchronous `curl.exe` requests passing mpv's active session headers (`User-Agent`, `Cookie`, `http-header-fields`), dropping fetch latency from 2–6s to under 300ms and eliminating HTTP 429 errors.
   - Enforce rigorous temp file lifecycle management on `end-file`, `shutdown`, and session language switches to prevent orphaned files in `%TEMP%`.

---

## 2. Detailed Technical Architecture

### 2.1 Toolbar Monograms & ASS Typography (`scripts/player-toolbar.lua`)

#### Button Bounding Box & Sizing Metrics
- At `controls_size=32`, each button box is exactly 32×32px.
- uosc computes default font size as `round(32 * 0.7) = 22px`.
- For standard icon glyphs (e.g. `headphones`, `graphic_eq`, `settings`), `MaterialIconsRound-Regular` glyphs are centered at em/2.
- For uppercase text monograms (`AR`, `EN`, `4K`, `HD`), capital letters occupy ~70% of the em square above the baseline with 0% descenders. Vertical centering with `\an5` leaves characters sitting ~1–2px lower than icon glyph centers.
- **ASS Styling & Font Stack**:
  - Text monograms are styled with the clean system UI font: `{\fnSegoe UI\b1\fs15\fscx95\fscy95}` or uosc's configured UI font.
  - Optical baseline compensation: apply a 1px upward offset (`{\pos(x, y - 1)}` or explicit ASS tags) so that the visual optical center of `AR` or `HD` aligns perfectly with surrounding vector icons.
  - Character bounding box verification: 2 uppercase characters at `\fs15` occupy ~18–20px width, leaving 6–7px of breathing room on each side within the 32px box.

#### Audio Button (`button:audio-tracks`)
- **Display Logic**:
  - Active audio track language is normalized to a 2-letter uppercase monogram (`AR`, `EN`, `JA`, etc.).
  - Fallback: If language is undetermined or local file has no language tags, display the centered `headphones` icon glyph.
  - Corner badge is set to `nil` (`badge = nil`), eliminating overlapping bottom-right corner pills.
- **Tooltip**: `Audio: <Language Name>` (e.g. `Audio: Arabic`, `Audio: English`).
- **Menu**: Deduplicated audio menu with clean language names, eliminating DASH audio representation clones and showing `Current` checkmark.

#### Video Quality Button (`<stream>button:stream-quality`)
- **Widescreen & Aspect Ratio Detection**:
  ```lua
  local function quality_monogram(w, h)
      local width = tonumber(w) or 0
      local height = tonumber(h) or 0
      if width <= 0 and height <= 0 then return nil end
      if width >= 3840 or height >= 2160 then return '4K' end
      if width >= 1280 or height >= 720 then return 'HD' end
      return 'SD'
  end
  ```
  - Correctly categorizes 2.39:1 widescreen 1080p (e.g. 1920x800) as `HD`, and 4K cinema (3840x1600) as `4K`.
- **Corner Badge**: `badge = nil`.
- **Tooltip**: `Video quality: <Monogram>` (or `Video quality: 1080p60`).
- **Menu**: Lists available video streams (`1080p60`, `720p`, etc.) with `Current` marker.

#### Stable Volume Button (`button:stable-volume`)
- **Visual Display**: Icon is **`graphic_eq`** (Material Icons equalizer bars).
- **Filter Graph**: Toggles `dynaudnorm=f=500:g=15:p=0.95:m=10,alimiter=limit=0.9:level=false` with label `mpv_config_stable_volume`.
- **Live Stream Safety**: Toggle applies filter reconfiguration using `mp.set_property_native('af', ...)` without dropping audio frames or causing playback stalls.

---

### 2.2 ISO-639 Language Normalization (`stream_policy.lua`)

To ensure text monograms never exceed 2 characters, `stream_policy.lua` provides a normalization mapping:

```lua
local iso_3_to_2 = {
    ara = 'AR', eng = 'EN', jpn = 'JA', spa = 'ES',
    fra = 'FR', fre = 'FR', deu = 'DE', ger = 'DE',
    ita = 'IT', por = 'PT', rus = 'RU', zho = 'ZH',
    chi = 'ZH', kor = 'KO', hin = 'HI', tur = 'TR',
    ind = 'ID', pol = 'PL', ukr = 'UK', nld = 'NL',
    dut = 'NL', swe = 'SV', vie = 'VI', tha = 'TH',
    fas = 'FA', per = 'FA', heb = 'HE', ell = 'EL',
    gre = 'EL', ces = 'CS', cze = 'CS', ron = 'RO',
    rum = 'RO', hun = 'HU', dan = 'DA', fin = 'FI',
    nor = 'NO', slk = 'SK', slo = 'SK', msa = 'MS',
    may = 'MS', ben = 'BN', urd = 'UR', tam = 'TA',
    tel = 'TE', mar = 'MR',
}

function M.monogram(lang_code, title)
    if type(lang_code) == 'string' and #lang_code > 0 then
        local clean = lang_code:lower():gsub('_', '-'):gsub('%-orig$', ''):match('^[a-z]+')
        if clean then
            if iso_3_to_2[clean] then return iso_3_to_2[clean] end
            if #clean >= 2 then return clean:sub(1, 2):upper() end
        end
    end
    -- Fallback to title substring lookup
    return nil
end
```

---

### 2.3 Uniform Toolbar Layout (`uosc.conf`)

- **Controls String**:
  ```ini
  controls=menu,command:content_paste:script-binding smart_paste/paste-to-open?Paste link,command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles and captions,button:audio-tracks,<stream>button:stream-quality,button:stable-volume,space,fullscreen
  ```
  - All ad-hoc `gap` entries removed.
  - Symmetrical spacing between all buttons governed by `controls_spacing`.
  - `space` anchors `fullscreen` cleanly to the right edge.
- **Sizing Parameters**:
  - `controls_size=32`: Sharp vector rendering at 96 DPI (1080p 27").
  - `controls_spacing=10`: Uniform 10px spacing between all button centers and edges.
  - `controls_margin=8`: 8px margin from bottom and screen edges.

---

### 2.4 High-Performance Subtitle Fetching & Lifecycle (`ytdl-sub-menu.lua`)

#### The Problem with Fresh `yt-dlp` Invocations
Running `yt-dlp --skip-download ... <url>` initiates a full remote metadata extraction pass, incurring a 2–6 second delay and redundant HTTP handshakes. Conversely, passing YouTube `timedtext` URLs directly to mpv's `sub-add` fails with `HTTP 429 Too Many Requests` because mpv lacks YouTube's browser session headers and cookies.

#### The Lightweight `curl` Fetch Strategy
1. **Header & Session Extraction**:
   - Extract `User-Agent`: `mp.get_property('file-local-options/user-agent')` or yt-dlp extracted user-agent.
   - Extract headers: `mp.get_property_native('file-local-options/http-header-fields')` and headers from `user-data/mpv/ytdl/json-subprocess-result`.
   - Extract cookies: pass session cookies or cookie files if present in `options/ytdl-raw-options`.
2. **Lightweight Async HTTP GET**:
   - Use Windows-native `curl.exe` (found at `C:\Windows\System32\curl.exe`):
     ```pwsh
     curl.exe -s -L --compressed --max-time 15 -H "User-Agent: <ua>" -H "Accept: text/vtt,*/*" "<timedtext_url>" -o "<temp_sub_file>"
     ```
   - Performance: ~150–300ms total execution time (over 10× faster than a full yt-dlp pass).
   - Direct to disk: Downloads directly to a designated temporary `.vtt` file.
3. **Temp File Lifecycle & Cleanup**:
   - File naming: `%TEMP%/mpv_sub_<pid>_<epoch>.vtt`.
   - Single active tracker: `local current_temp_file = nil`.
   - On language switch: Unlink/delete previous temp file before or immediately after loading new track.
   - On exit: Register `end-file` and `shutdown` events in mpv to delete any lingering temp files:
     ```lua
     local function cleanup_temp_file()
         if current_temp_file and utils.file_info(current_temp_file) then
             os.remove(current_temp_file)
             current_temp_file = nil
         end
     end
     mp.register_event('end-file', cleanup_temp_file)
     mp.register_event('shutdown', cleanup_temp_file)
     ```
4. **Concurrency & Race Condition Guard**:
   - If user clicks multiple subtitle tracks rapidly:
     - Previous async command is immediately aborted via `mp.abort_async_command(job.id)`.
     - `epoch` is incremented.
     - Outdated responses are discarded, preventing stale subtitle files from loading.

#### Subtitle Filtering: Arabic & English with "More languages..." Fallback
- In `stream_policy.captions()`:
  - **Creator Subtitles (`manual`)**: Always retained in full.
  - **Auto-Generated & Auto-Translated (`automatic`, `translated`)**:
    - Filtered to Arabic (`ar`) and English (`en`) as primary items.
    - Non-ar/en auto-translated entries are grouped under an expandable `"More languages..."` submenu.
    - Keeps the primary menu clean (3–4 entries instead of 155), while preserving 100% foreign language accessibility when needed.

---

## 3. Migration & Upgrader Integration (`tools/apply_youtube_gui.py`)

- **Configuration Sync**:
  - `NEW_CONTROLS`: `menu,command:content_paste:script-binding smart_paste/paste-to-open?Paste link,command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles and captions,button:audio-tracks,<stream>button:stream-quality,button:stable-volume,space,fullscreen`
  - `DEFAULTS`: `controls_size=32`, `controls_spacing=10`.
  - `REQUIRED_SCRIPTS`: Copies updated `player-toolbar.lua`, `ytdl-sub-menu.lua`, `stream_policy.lua` into `%APPDATA%\mpv\scripts\`.
  - Upgrader validates existing `uosc.conf`, creates timestamped atomic backup, and updates cleanly.

---

## 4. Verification Plan

### Automated Tests
1. **Lua Unit Tests** (`python tests/run_lua_tests.py`):
   - `test_stream_policy.lua`:
     - Test 3-letter to 2-letter ISO normalization (`ara` $\to$ `AR`, `eng` $\to$ `EN`, `jpn` $\to$ `JA`).
     - Test widescreen resolution check: 1920x800 returns `HD`, 3840x1600 returns `4K`, 640x360 returns `SD`.
     - Test auto-translated caption filtering: primary list has `ar` and `en`, remainder placed under `"More languages..."`.
   - `test_player_toolbar.lua`:
     - Test toolbar button publishing: audio monogram is max 2 chars, badge is nil.
     - Test stable volume uses `graphic_eq` icon.
2. **Python Unit Tests** (`python -m unittest discover -s tests -v`):
   - `test_youtube_gui_upgrade.py`: Test migration to gap-free `controls` layout and `controls_spacing=10`.
   - `test_config.py` & `test_audit_patches.py`: Verify config assertions pass without regressions.

### Manual Live Verification
1. Run `python tools/apply_youtube_gui.py --config-dir "$env:APPDATA\mpv" --apply`.
2. Launch MPV with a YouTube video featuring multi-audio dubs and auto-translated captions.
3. Verify toolbar appearance:
   - Audio button displays sharp, centered `AR` or `EN` monogram (no corner badge).
   - Quality button displays sharp, centered `HD` or `4K` monogram (no corner badge).
   - Stable volume displays `graphic_eq` bars.
   - Spacing between buttons is uniform (10px).
4. Verify subtitle menu:
   - Subtitle list shows clean Arabic and English options, plus `"More languages..."`.
   - Selecting Arabic or English downloads in <300ms without 429 error.
   - Closing video deletes temp file from `%TEMP%`.
