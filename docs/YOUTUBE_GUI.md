# Mouse-first MPV controls, captions and dubs

## Use the icons — no keyboard required

Move the pointer towards the bottom of the player to reveal the toolbar. Its groups are:

```text
Prev · Play · Next  |  Speed  |  CC · Audio · Video · Quality · Items · More · Fullscreen
```

| Icon / Control | Mouse action |
| --- | --- |
| Prev | Previous file in playlist. |
| Play/Pause | Play or pause playback. |
| Next | Next file in playlist. |
| Speed | Playback speed slider, centered between two expanding spaces. |
| CC | Open subtitles and captions. On YouTube, choose creator, auto-generated or auto-translated captions. For local media, use the normal subtitle menu. |
| Audio tracks | Open audio tracks and choose the available dub/language. |
| Video | Open video tracks menu (displayed only when the file has multiple video tracks). |
| Quality | Dynamic resolution badge (e.g. 1080p, 720p, 4K) for network streams. Click to open the actual available qualities for the current video with a selection indicator. Rows marked **●** are formats the stream really offers; rows marked **○** are ceiling-only choices the stream doesn't list (hint *cap only · not in stream*) — picking one caps the extractor, so playback falls to the best the video actually has. This keeps, say, a 4K row visible for a 1080-max video without pretending it exists. When nothing is known about the stream yet (a local file, a non-YouTube source, or a switch that just failed) the rows carry **no marker** at all: the menu never claims a height is missing when it has not actually checked. |
| Items | Open playlist items navigation. |
| More | Open the More menu for secondary controls, toggles, and shortcut reference. |
| Fullscreen | Enter or leave fullscreen, at the far-right edge of the toolbar. |
| Anime detection & Anime4K mode | `scripts/profile_picker.lua` decides per file whether the file is anime (release group, Japanese audio track, episode marker, multi-language tag, or a title from your own `script-opts/anime_series.conf` list) and applies the **anime** profile (Anime4K on the default "A+A (Ultra Sharp)" preset with an on-screen verification badge) or the light **live-action** one. `Ctrl+g` cycles the Anime4K mode, `Ctrl+Shift+t` overrides the detection by hand, and `Ctrl+1`…`Ctrl+6` (`Ctrl+0` for off) pick a mode directly — any shortcut automatically saves the choice as default to `script-opts/anime4k.conf`. The installer asks which preset to ship (`off`, `fast`, `A`, `A+A`, `B`, `B+B`, `C`, `C+A`), where `A+A` is the recommended default. Default preset can also be updated anytime via `deployer --update --anime-preset <MODE>` or by editing `script-opts/anime4k.conf`. |
| Quality menu · Set as default (row submenu) | Each resolution row opens a two-action submenu. *Set as default* persists that resolution as the streaming ceiling (`script-opts/stream_quality.conf`, e.g. *720p ▸ Set as default*) **and** re-drives the playing video at it. Future streams start at it; rows marked *Default* show what is saved. One submenu action — two clicks, no reopen. |
| Quality menu · Just this video (row submenu) | Plays this video at the chosen resolution only — session override, saved default untouched. Switches happen without re-extraction: the last yt-dlp pass already holds signed stream URLs, so a switch loads the chosen video + audio URLs directly (the ~3 s extraction round-trip is skipped); if those URLs have gone stale, the switch automatically falls back to the full reload. The playlist entry keeps the canonical page URL, so replaying the video later re-extracts it instead of replaying an expired link. A height the stream does not offer (a **○** row) caps the extraction instead of demanding a format that isn't there, so it still plays the best the video actually has — the OSD then names the height that is really played, not the unreachable ceiling. After a fast switch the cached extraction is restored, so every later switch in that video stays fast and the menu keeps its real rows. The OSD after any quality change names the rescale (*720p (upscale: 1920x1080 display)*) because stats-for-nerds *Display: Resolution* is the window size, not the stream — the **Video** section shows the real source resolution. |
| Quality menu · Apply default now | Drops any session override and reloads at the saved default. |
| Quality menu · Default: any resolution | Removes the cap entirely — yt-dlp picks the best available source quality. |

CC and audio tracks are separate, always-available buttons, not instructions to press a shortcut. The audio-count badge is omitted to avoid distracting numbers such as `147` on the toolbar; track names and choices remain in the audio menu. The ordinary volume slider is still separate and unchanged.

The layout uses uosc's expanding `space` elements to center the speed slider and align right controls. Controls use 36 pixels with 12-pixel spacing and a 10-pixel margin (`script-opts/uosc.conf`). The toolbar remains accessible while idle. Fullscreen/display scaling still applies; extremely narrow windows or unusually large custom scaling can cause uosc to hide middle controls. Widen the window if a control is missing.

### More menu

Clicking the More button (menu icon) opens a menu built by `scripts/more_menu.lua` for secondary actions and toggles:

| Entry | Visibility | Action |
| --- | --- | --- |
| **Paste link** (hint `Ctrl+V`) | Always | Open the link or file path currently copied to the clipboard (`smart_paste/paste-to-open`). |
| **Download video** | Streams only | Start downloading the playing video via `player_toolbar download-video`. Progress reports through OSD notifications rather than a toolbar badge. |
| **Stable volume** | Always | Toggle dynamic loudness normalization and limiter (`dynaudnorm` + `alimiter`). Displays an active mark when enabled; keeps the menu open. |
| **Shuffle** | Always | Toggle playlist shuffle (`uosc/shuffle`). Displays an active mark when enabled; keeps the menu open. |
| **Loop playlist** | Always | Toggle playlist looping (`cycle-values loop-playlist inf no`). Displays an active mark when enabled; keeps the menu open. |
| **Loop file** | Always | Toggle single-file looping (`cycle-values loop-file inf no`). Displays an active mark when enabled; keeps the menu open. |
| **Editions** | Multiple editions only | Open editions menu (`uosc/editions`). |
| **Full uosc menu** | Always | Open uosc's full blurred menu (`uosc/menu-blurred`). Right-click in this configuration pauses playback (`cycle pause`), so "Full uosc menu" is the mouse route to uosc's own menu. |
| **All shortcuts** (hint `F9`) | Always | Open the ASS vector keybinding and mouse cheat sheet overlay (`help_overlay help`). |

Toggles display a mark and keep the menu open so multiple settings can be adjusted at once. Clicking the More button while the menu is open closes it.

### Turn on generated captions while watching

1. Copy a YouTube link and use **More → Paste link** (or press `Ctrl+V`). Quoted links, `youtu.be`, `watch?v=...` and `shorts/...` fragments are normalized before extraction. Existing local files are not converted into URLs.
2. Once playback starts, click **CC**.
3. Open **Auto-generated** and click the language you want. Creator captions and auto-translations are separate groups when supplied by YouTube/yt-dlp.
4. To turn captions off, click **CC → Subtitles off**. This also cancels an in-flight caption request.
5. To change the dub, click **audio tracks**, then the desired audio track. No keyboard action is needed for either menu.

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

## Stable Volume in the More menu

Stable Volume uses the existing normalization/limiter settings:

```text
dynaudnorm=f=500:g=15:p=0.95:m=10
alimiter=limit=0.9:level=false
```

It does not change audio filters at startup. Selecting it in the More menu toggles this named preset while retaining unrelated filters. It also recognizes the exact adjacent, unlabelled pair from the shipped F8 preset, so toggling an already-active legacy preset turns it off rather than adding another copy. Differently labelled user filters are left alone; a conflicting reserved filter name is not overwritten.

The toggle state in the More menu reflects actual filter changes with a live active mark and keeps the menu open when clicked. The F8 shortcut itself is unchanged and still has its original whole-filter-list behavior; use the More menu toggle when preserving custom filters matters.

## Updates and toolbar migration

Running `install` over an existing configuration or running `update` replaces only the `controls=` line of `script-opts/uosc.conf` with the shipped control bar. Every other line, comment, and custom setting in `uosc.conf` is preserved byte for byte. Even if the `controls=` line was previously hand-edited, it is replaced with the shipped line. The previous configuration file is preserved in that run's backup snapshot (`mpv.backup.*`), and running `--dry-run` lists the change without writing any files.

### Standalone opt-in migration (`tools/apply_youtube_gui.py`)

If you update your configuration files outside the deployer (for example, by manually pulling files or managing a portable directory), you can preview and apply the toolbar update using `tools/apply_youtube_gui.py`.

The helper requires the GUI scripts (`scripts/ytdl_hook.lua`, `scripts/ytdl-sub-menu.lua`, `scripts/smart-paste.lua`, `scripts/modules/stream_policy.lua`, `scripts/player-toolbar.lua`, `scripts/more_menu.lua`, and `tools/vtt_translate.py`).

From the checkout, preview the toolbar migration:

```console
python tools/apply_youtube_gui.py --config-dir "<active mpv config directory>"
```

Replace the placeholder with the directory containing your active `mpv.conf` and `script-opts` folder. A portable installation may use a different directory from the normal user configuration. After reviewing the preview, apply it with mpv closed:

```console
python tools/apply_youtube_gui.py --config-dir "<active mpv config directory>" --apply
```

The helper:

- Recognizes earlier stock toolbar layouts and upgrades them to the new cleaner control bar.
- Checks that the required GUI scripts exist before activating new controls; it does not install those scripts or verify their version.
- Changes only recognized stock toolbar/spacing values in `uosc.conf`, retaining other custom values, comments and line endings.
- Makes a unique `uosc.conf.pre-youtube-*.bak` backup before replacing the file.
- Refuses custom/duplicate toolbar definitions and symlinked targets instead of overwriting them.
- Does not touch `mpv.conf`, `input.conf`, shaders or language preferences.

Restart mpv after applying. To undo the layout change, close mpv and restore the printed backup.

Use a uosc release that supports managed buttons (the API was checked against uosc 5.13.0 source), and keep its bundled fonts installed with it. Boxes or literal icon names usually indicate missing or mismatched fonts; check the configuration's `fonts` directory and restart mpv.

### Custom toolbar: merge deliberately

If you maintain a custom layout, back up `uosc.conf` and merge the following entries into its **single** `controls=` line. The shipped reference layout is:

```ini
controls=prev,play-pause,next,space,<video,audio>speed,space,command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles and captions,button:audio-tracks,<has_many_video>video,<stream>button:stream-quality,items,command:menu:script-message-to more_menu open?More,fullscreen
```

Retain your other custom controls and settings as needed. Do not paste a second `controls=` line.

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
