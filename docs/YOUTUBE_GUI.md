# Mouse-first MPV controls, captions and dubs

## Player UI styles and controls — no keyboard required

Move the pointer towards the bottom of the player to reveal the controls. The player includes three switchable styles configured via **More > Appearance > Style**:

### 1. calm (default)
Clean, minimalist layout with uncluttered controls and no button background boxes. A thin 3 px progress line stays visible at the bottom and expands to full height with timestamps when the pointer comes near.
- **Left**: Previous (`prev`), Play/Pause (`PLAY`, round icon), Next (`next`)
- **Center**: Expanding space
- **Right**: Playback speed slider (`<video,audio>speed`), Subtitles (`SUBS`), Audio tracks (`button:audio-tracks`), conditional controls (`<has_many_video>video`, `<has_many_edition>editions`, `<stream>button:stream-quality`, `<stream>button:download-video`), Playlist (`items`), More menu (`MORE`), Fullscreen (`fullscreen`)

### 2. bar
Same button order and timeline behavior as **calm**, but each button sits on a translucent filled box (opacity 0.93) and the controls remain visible in windowed mode as well as when idle.

### 3. focus
Centered playback controls focused on essential navigation, keeping the interface distraction-free. Secondary controls (subtitles, audio, speed, quality, download) are accessed through the **More** menu.
- **Left / Center**: Expanding space, Previous (`prev`), Play/Pause (`PLAY`), Next (`next`), Expanding space
- **Right**: Playlist (`items`), More menu (`MORE`), Fullscreen (`fullscreen`)

### Button order reference

| Style | Controls order |
| --- | --- |
| **calm** / **bar** | `prev,PLAY,next,space,<video,audio>speed,SUBS,button:audio-tracks,COND,items,MORE,fullscreen` |
| **focus** | `space,prev,PLAY,next,space,items,MORE,fullscreen` |

Where `PLAY` is the round play/pause cycle button, `SUBS` opens subtitles, `COND` provides contextual video track, editions, stream quality, and download buttons, and `MORE` opens the grouped More menu.

### Control sizes

Configured via **More > Appearance > Size**:
- **comfortable** (default): 44 px buttons with 4 px spacing and 8 px margin; 40 px timeline size.
- **compact**: 36 px buttons with 2 px spacing and 6 px margin; 32 px timeline size.

Both sizes feature a 3 px slim progress line when hidden and 40 px menu item height.

### Grouped More menu

The **More** button (`MORE`, hamburger icon) opens a structured in-player menu:

```text
Appearance       > Style (calm · bar · focus)
                   Background (dark · black · slate)
                   Accent (amber · teal · violet · rose · white)
                   Size (comfortable · compact)
Subtitles        (opens caption / subtitle menu)
Audio            (opens audio tracks & dubs menu)
Stream quality   (streams only; opens quality menu)
Playback         > Shuffle (toggle, marked when ON)
                   Loop playlist (toggle, marked when active)
                   Loop file (toggle, marked when active)
                   Speed (0.5× · 0.75× · 1× · 1.25× · 1.5× · 1.75× · 2×)
Picture & sound  > Anime4K mode (off · fast · A · B · C · A+A · B+B · C+A)
                   Stable volume (toggle, marked when ON)
                   Video track (listed when file has multiple video tracks)
                   Editions (listed when file has multiple editions)
Open             > Paste link (Ctrl+V hint, opens clipboard URL/path)
                   Open file (file picker)
                   Download video (streams only)
Full uosc menu   (opens uosc's full built-in menu)
All shortcuts    (F9 / ? cheat sheet overlay)
```

Active values across Appearance, Playback, and Picture & sound are dynamically marked. Appearance adjustments switch live within 1 second while playing without reloading, and persist in `script-opts/ui_appearance.conf`.

| Icon / Button | Mouse action |
| --- | --- |
| Prev / Next | Previous or next playlist entry / chapter. |
| Play / Pause | Play or pause video (round icon). |
| Speed slider | Adjust playback speed interactively (`calm` and `bar`; in `focus`, reached via **More > Playback > Speed**). |
| Subtitles | Open subtitles and captions. On YouTube, choose creator, auto-generated or auto-translated captions. For local media, opens the subtitle menu (in `focus`, reached via **More > Subtitles**). |
| Audio tracks | Open audio tracks and choose the available dub/language (in `focus`, reached via **More > Audio**). |
| Video track | Contextual: appears when the file has multiple video tracks (in `focus`, reached via **More > Picture & sound > Video track**). |
| Editions | Contextual: appears when the file has multiple editions (in `focus`, reached via **More > Picture & sound > Editions**). |
| Quality | Contextual: appears on network streams. Dynamic resolution badge (e.g. 1080p, 720p, 4K). Click to open the stream quality menu with *Set as default* and *Just this video* submenus (in `focus`, reached via **More > Stream quality**). Rows marked **●** are formats the stream really offers; rows marked **○** are ceiling-only choices the stream doesn't list (hint *cap only · not in stream*) — picking one caps the extractor, so playback falls to the best the video actually has. |
| Download | Contextual: appears on network streams. Download the playing video directly using yt-dlp (in `focus`, reached via **More > Open > Download video**). |
| Playlist (`items`) | Open the playlist / file items menu with drag-and-drop reordering. |
| Anime detection & Anime4K mode (More > Picture & sound > Anime4K mode) | `scripts/profile_picker.lua` decides per file whether the file is anime (release group, Japanese audio track, episode marker, multi-language tag, or a title from your own `script-opts/anime_series.conf` list) and applies the **anime** profile (Anime4K on the default "A+A (Ultra Sharp)" preset with an on-screen verification badge) or the light **live-action** one. `Ctrl+g` cycles the Anime4K mode, `Ctrl+Shift+t` overrides the detection by hand, and `Ctrl+1`…`Ctrl+6` (`Ctrl+0` for off) pick a mode directly — any shortcut automatically saves the choice as default to `script-opts/anime4k.conf`. The installer asks which preset to ship (`off`, `fast`, `A`, `A+A`, `B`, `B+B`, `C`, `C+A`), where `A+A` is the recommended default. Default preset can also be updated anytime via `deployer --update --anime-preset <MODE>` or by editing `script-opts/anime4k.conf`. |
| Stable volume (More > Picture & sound) | Toggle Stable Volume. The row is marked while the preset is on. |
| More | Open the grouped More menu (Appearance, Subtitles, Audio, Stream quality, Playback, Picture & sound, Open, Full uosc menu, All shortcuts). |
| Fullscreen | Enter or leave fullscreen, at the far-right edge of the toolbar. |
| Quality menu · Set as default (row submenu) | Each resolution row opens a two-action submenu. *Set as default* persists that resolution as the streaming ceiling (`script-opts/stream_quality.conf`, e.g. *720p ▸ Set as default*) **and** re-drives the playing video at it. Future streams start at it; rows marked *Default* show what is saved. One submenu action — two clicks, no reopen. |
| Quality menu · Just this video (row submenu) | Plays this video at the chosen resolution only — session override, saved default untouched. Switches happen without re-extraction: the last yt-dlp pass already holds signed stream URLs, so a switch loads the chosen video + audio URLs directly (the ~3 s extraction round-trip is skipped); if those URLs have gone stale, the switch automatically falls back to the full reload. The playlist entry keeps the canonical page URL, so replaying the video later re-extracts it instead of replaying an expired link. A height the stream does not offer (a **○** row) caps the extraction instead of demanding a format that isn't there, so it still plays the best the video actually has — the OSD then names the height that is really played, not the unreachable ceiling. After a fast switch the cached extraction is restored, so every later switch in that video stays fast and the menu keeps its real rows. The OSD after any quality change names the rescale (*720p (upscale: 1920x1080 display)*) because stats-for-nerds *Display: Resolution* is the window size, not the stream — the **Video** section shows the real source resolution. |
| Quality menu · Apply default now | Drops any session override and reloads at the saved default. |
| Quality menu · Default: any resolution | Removes the cap entirely — yt-dlp picks the best available source quality. |

The toolbar remains accessible while idle. Fullscreen/display scaling still applies; extremely narrow windows or unusually large custom scaling can cause uosc to hide middle controls. Widen the window if a control is missing.

### Turn on generated captions while watching

1. Copy a YouTube link and open it via **More > Open > Paste link** (or press `Ctrl+V`). Quoted links, `youtu.be`, `watch?v=...` and `shorts/...` fragments are normalized before extraction. Existing local files are not converted into URLs.
2. Once playback starts, click **Subtitles** (or **More > Subtitles** in `focus`).
3. Open **Auto-generated** and click the language you want. Creator captions and auto-translations are separate groups when supplied by YouTube/yt-dlp.
4. To turn captions off, click **Subtitles → Subtitles off** (or **More > Subtitles → Subtitles off**). This also cancels an in-flight caption request.
5. To change the dub, click **Audio** (or **More > Audio** in `focus`), then the desired audio track. No keyboard action is needed for either menu.

Only captions actually returned by YouTube/yt-dlp are listed. This does not generate missing captions using a separate speech-recognition service. Caption selection is per playback session; reopening a video may require selecting an on-demand caption again.

Existing keyboard shortcuts, including Arabic-layout bindings, remain optional and unchanged. They are not required to use these controls.

## Quiet link-opening feedback

Opening a pasted link shows **Opening link…**. The message clears when loading completes or fails; errors use short, actionable wording. There is no ticking elapsed-time counter, animated spinner, raw URL on screen or success-time toast. Repeated clicks on the same pending link do not deliberately restart the request.

Feedback is driven by loading events, not a periodic timer. The toolbar controller observes audio-filter changes, not every playback frame. Neither change performs another extraction or network probe. This removes recurring status-update work; it is not a measured claim that YouTube's network response becomes faster.

## How captions work

- Opening a video does not start a caption process, metadata parse, timer or translation job in the caption menu script.
- Opening CC reuses the playback hook's existing metadata and parses it once per video.
- Selecting a caption loads its URL asynchronously with mpv. Selecting an already-loaded caption reuses that track instead of downloading it again. Playback is not reloaded.
- Switching files, choosing Off, closing mpv or reaching the bounded timeout cancels pending work. Old menu actions cannot act on the next video.
- **Refresh available captions** explicitly requests fresh metadata from yt-dlp, useful when captions appear later or signed URLs expire. Merely opening CC does not trigger this request.
- Refresh preserves allowlisted networking/authentication raw options, not output or execution flags. Keep your normal authentication setup for restricted videos; do not paste credentials into issues or logs.
- The menu's JSON payload is sent as one command argument, keeping codec status/error return values out of the button's menu-opening command.

Availability, translation coverage and accuracy remain controlled by YouTube and yt-dlp.

## How dub filtering works

The playback hook filters its already-extracted format list before building mpv's delayed-open tracks. It keeps the highest reported audio bitrate for each distinguishable language/track/role combination. Default selection follows the winning rendition of the same dub rather than accidentally disabling audio.

- Preserve distinct metadata for original/dubbed tracks, regional variants, descriptive audio, DRC and named commentary.
- Prefer audio bitrate (`abr`), then audio-only total bitrate, then a size/duration estimate. Equal rates retain yt-dlp's preference order.
- Preserve video and muxed formats. Leave live streams, non-YouTube extractors, audio-only sources and unknown language/bitrate metadata unpruned.
- Explicit command-line `--ytdl-format` choices and numeric `aid` selections, including saved selections, bypass pruning to avoid silently reinterpreting track IDs.
- Numeric `sid` selections and explicit raw subtitle options retain the previous subtitle-enumeration path.

This is conservative metadata-based filtering, not another extraction or a background probe of every dub. Ambiguous formats may remain duplicated. Higher bitrate is not a universal guarantee of better perceived quality across codecs.

## Stable Volume and Picture & sound controls

Stable Volume uses the existing normalization/limiter settings:

```text
dynaudnorm=f=500:g=15:p=0.95:m=10
alimiter=limit=0.9:level=false
```

It is toggled from **More > Picture & sound > Stable volume** (or shortcut `F8`), where its active state is clearly marked. It does not change audio filters at startup. Toggling it adds or removes its named preset while retaining unrelated filters. It also recognizes the exact adjacent, unlabelled pair from the shipped F8 preset, so toggling an already-active legacy preset turns it off rather than adding another copy. Differently labelled user filters are left alone; a conflicting reserved filter name is not overwritten.

Anime4K mode is also selectable and saved from **More > Picture & sound > Anime4K mode** (in addition to `Ctrl+1`..`Ctrl+6`, `Ctrl+0`, `Ctrl+g`).

## Theme management & uosc configuration ownership

The theme script (`scripts/ui_appearance.lua`) dynamically owns and manages the following uosc configuration options:

```text
controls, color, opacity, controls_size, controls_spacing, controls_margin, controls_persistency, timeline_size, progress, progress_size, menu_item_height
```

Because these keys are set dynamically via mpv's runtime `script-opts`, manual edits to them in `uosc.conf` no longer take effect. All appearance customizations (styles, backgrounds, accents, and sizes) are made inside mpv via **More > Appearance** and persist in `script-opts/ui_appearance.conf`.

All other `uosc.conf` options (such as animation durations, fonts, and volume controls) remain fully under user control.

On fresh installs and updates, configurations move to the default look (**calm**, **dark**, **amber**, **comfortable**) automatically.

## Preserved performance settings and opt-outs

The 1080p selector, `alang`/`slang`, GPU/hardware decoding, Anime4K, cache sizes, display synchronization, VRR behavior, interface refinement and animation settings are unchanged by this refinement. Audio processing changes only when you explicitly toggle Stable Volume. No live-YouTube startup speedup or perceptual audio-quality improvement is claimed.

To opt out of the earlier smart-track/on-demand-subtitle policy, add either setting to your active `script-opts/ytdl_hook.conf`:

```ini
# Keep every audio rendition:
best_audio_per_language=no
# Restore implicit subtitle enumeration:
youtube_subs_on_demand=no
```

To adjust caption-request timeout, set `timeout=30` in `script-opts/ytdl_sub_menu.conf`. The supported range is 5–120 seconds.

## Validation boundaries

The dedicated GUI workflow covers five offline Lua suites (policy, caption lifecycle/menu actions, actual-hook integration, paste safety and toolbar state), GUI-upgrade safety on Ubuntu and Windows, LuaJIT syntax, and required native headless-mpv tests. Native cases cover caption loading/reuse, cancellation across files, the CC menu's command path and Stable Volume filter preservation/state.

Native fixtures use a generated image, silent WAV and localhost VTT. A small test-only uosc message receiver checks JSON and click-command transport; it is **not** the real uosc renderer and does not prove the desktop appearance. Consult the PR's latest checks for actual outcomes. Existing installer/audit and repository-wide failures have not been hidden; see [the project audit](AUDIT.md).

Before promoting to your main installation, verify the actual icons at your display scale, English/Arabic captions and dubs on a multi-dub YouTube video, rapid video switching, and cold/warm link-opening times. Desktop appearance, Windows/macOS playback, GPU/HDR behavior, private/live YouTube access, audible filter transitions and end-to-end startup performance still require real-device validation.
