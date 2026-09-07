# Mouse-first MPV controls, captions and dubs

## Use the icons — no keyboard required

Move the pointer towards the bottom of the player to reveal the toolbar. Its groups are:

```text
Menu · Paste  |  CC · Headphones · Quality  |  Stable Volume          Fullscreen
```

| Icon | Mouse action |
| --- | --- |
| Menu | Open the normal uosc menu. |
| Clipboard | Open the link or file path currently copied to the clipboard. |
| CC | Open subtitles and captions. On YouTube, choose creator, auto-generated or auto-translated captions. For local media, use the normal subtitle menu. |
| Headphones | Open audio tracks and choose the available dub/language. This does not toggle Stable Volume. |
| Quality | Dynamic resolution badge (e.g. 1080p, 720p, 4K). Click to open the actual available qualities for the current video with a selection indicator. |
| Compress / inward arrows | Toggle Stable Volume. The active styling, **ON** badge and hover text reflect the actual preset state. No badge is shown while Off. |
| Fullscreen | Enter or leave fullscreen, at the far-right edge of the toolbar. |

CC and headphones are separate, always-available buttons, not instructions to press a shortcut. Stable Volume no longer shares the audio-track waveform icon. The audio-count badge is omitted to avoid distracting numbers such as `147` on the toolbar; track names and choices remain in the audio menu. The ordinary volume slider is still separate and unchanged.

The layout uses uosc's expanding `space` element for right alignment, not an oversized fixed gap. Default buttons remain 44 pixels with 4-pixel spacing and an 8-pixel margin. The toolbar remains accessible while idle. Fullscreen/display scaling still applies; extremely narrow windows or unusually large custom scaling can cause uosc to hide middle controls. Widen the window if a control is missing.

### Turn on generated captions while watching

1. Copy a YouTube link and click the **clipboard icon**. Quoted links, `youtu.be`, `watch?v=...` and `shorts/...` fragments are normalized before extraction. Existing local files are not converted into URLs.
2. Once playback starts, click **CC**.
3. Open **Auto-generated** and click the language you want. Creator captions and auto-translations are separate groups when supplied by YouTube/yt-dlp.
4. To turn captions off, click **CC → Subtitles off**. This also cancels an in-flight caption request.
5. To change the dub, click **headphones**, then the desired audio track. No keyboard action is needed for either menu.

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

## Stable Volume without the icon confusion

The new button uses the existing normalization/limiter settings:

```text
dynaudnorm=f=500:g=15:p=0.95:m=10
alimiter=limit=0.9:level=false
```

It does not change audio filters at startup. Clicking it adds or removes its named preset while retaining unrelated filters. It also recognizes the exact adjacent, unlabelled pair from the shipped F8 preset, so clicking an already-active legacy preset turns it off rather than adding another copy. Differently labelled user filters are left alone; a conflicting reserved filter name is not overwritten.

The icon state follows actual filter changes and is republished when uosc starts. It does not emulate F8. The old F8 shortcut itself is unchanged and still has its original whole-filter-list behavior; use the new button when preserving custom filters matters.

## Existing installations: update scripts, then activate the layout

**Normal updates intentionally preserve your personal `script-opts/uosc.conf`. Updating the repository or scripts alone does not replace your installed toolbar.**

With mpv closed, back up and update these five files together from the same reviewed revision, keeping their paths under your active mpv configuration directory:

- `scripts/ytdl_hook.lua`
- `scripts/ytdl-sub-menu.lua`
- `scripts/smart-paste.lua`
- `scripts/modules/stream_policy.lua`
- `scripts/player-toolbar.lua`

Use your normal asset update process, or copy these files manually. Use a uosc release that supports managed buttons (the API was checked against uosc 5.13.0 source), and keep its bundled fonts installed with it. Boxes or literal icon names usually indicate missing/mismatched fonts; check the configuration's `fonts` directory and restart mpv. Use normal configuration loading: `--no-config` also disables discovery of this configuration's caption helper module.

From the checkout containing this update, preview the toolbar migration:

```console
python tools/apply_youtube_gui.py --config-dir "<active mpv config directory>"
```

Replace the placeholder with the directory containing your active `mpv.conf` and `script-opts` folder. A portable installation may use a different directory from the normal user configuration. After reviewing the preview, apply it with mpv closed:

```console
python tools/apply_youtube_gui.py --config-dir "<active mpv config directory>" --apply
```

The helper:

- Recognizes both earlier stock toolbar layouts and upgrades them to the icon-first layout.
- Checks that the five GUI scripts exist before activating new controls; it does not install those scripts or verify their version.
- Changes only recognized stock toolbar/spacing values in `uosc.conf`, retaining other custom values, comments and line endings.
- Makes a unique `uosc.conf.pre-youtube-*.bak` backup before replacing the file.
- Refuses custom/duplicate toolbar definitions and symlinked targets instead of overwriting them.
- Does not touch `mpv.conf`, `input.conf`, shaders or language preferences.

Restart mpv after applying. Confirm that headphones and the compress icon are distinct and fullscreen is at the right. To undo the layout change, close mpv and restore the printed backup.

### Custom toolbar: merge deliberately

If you maintain a custom layout, back up `uosc.conf` and merge the following entries into its **single** `controls=` line. Replace the old subtitle/audio/Stable Volume entries rather than appending duplicates; move fullscreen to the end after `space`. A complete reference layout is:

```ini
controls=menu,command:content_paste:script-binding smart_paste/paste-to-open?Paste link,gap,command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles and captions,gap,button:audio-tracks,gap,<stream>button:stream-quality,gap,button:stable-volume,space,fullscreen
```

Retain your other custom controls and settings as needed. Do not paste a second `controls=` line. New installations receive this default automatically; existing installations require the explicit activation above.

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
