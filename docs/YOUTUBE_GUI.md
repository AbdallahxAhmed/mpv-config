# YouTube controls, captions and smart audio tracks

## Quick use

1. Paste a link with **Ctrl+V** or the clipboard toolbar button. Quoted links, `youtu.be`, `watch?v=...` and `shorts/...` fragments are normalized before the extractor hook. Existing local files are not converted into URLs.
2. Once playback starts, click **CC / YouTube captions** or press **Ctrl+C** (Arabic-layout **Ctrl+ؤ**).
3. Choose a language under **Creator captions**, **Auto-generated**, or **Auto-translated**. Only tracks actually returned by YouTube/yt-dlp are listed. This does not generate missing captions with a separate speech-recognition service.
4. Select **Subtitles off** to turn captions off and cancel an in-flight caption request. The regular subtitle button / **c** still manages already-loaded and local subtitles.
5. Use the **audio** button / **a** to switch dubs. Arabic-layout shortcuts and the F8 Stable Volume action are unchanged.

The familiar playback controls remain together. Clipboard and YouTube CC actions form a separate group, with tooltips and stock Material icons. The CC button is conditional on a YouTube source; the toolbar stays accessible while idle. Default button/menu targets are larger and more spaced out, without enabling additional rendering refinement or animations.

## How captions work

- Opening a video does not start a caption process, metadata parse, timer or translation job in the caption menu script.
- Opening the menu reuses the playback hook's existing metadata and parses it once per video.
- Selecting a caption loads its URL asynchronously with mpv. Selecting an already-loaded caption reuses the track instead of downloading it again. Playback is not reloaded.
- Switching files, choosing Off, closing mpv or reaching the bounded timeout cancels pending work. Old menu actions cannot act on the next video.
- **Refresh available captions** is an explicit metadata-only yt-dlp request, useful when captions appear later or signed URLs expire. Merely opening the menu does not trigger this refresh.
- Refresh preserves allowlisted networking/authentication raw options, not output or execution flags. Keep your normal yt-dlp authentication setup for restricted videos; no credentials should be pasted into issues or logs.

Caption selection is per playback session. Reopening a video may require choosing an on-demand caption again. Availability, translation coverage and accuracy remain controlled by YouTube and yt-dlp.

## How dub filtering works

The playback hook filters its already-extracted format list before building mpv's delayed-open tracks. It keeps the highest reported audio bitrate for each distinguishable language/track/role combination. Default selection follows the winning rendition of the same dub, rather than accidentally disabling audio.

- Preserve distinct metadata for original/dubbed tracks, regional language variants, descriptive audio, DRC and named commentary.
- Prefer audio bitrate (`abr`), then audio-only total bitrate, then a size/duration estimate. Equal rates retain yt-dlp's preference order.
- Preserve video and muxed formats. Leave live streams, non-YouTube extractors, audio-only sources and unknown language/bitrate metadata unpruned.
- Explicit command-line `--ytdl-format` choices and numeric `aid` selections, including saved selections, bypass pruning to avoid silently reinterpreting track IDs.
- Numeric `sid` selections and explicit raw subtitle options retain the previous subtitle-enumeration path.

This is conservative metadata-based filtering, not a second extraction or a background probe of every dub. Ambiguous formats may remain duplicated. Higher bitrate is not a universal guarantee of better perceived quality across different codecs.

## Performance and preserved settings

There is no additional pre-playback extractor call for these menus. Default YouTube playback no longer asks the hook to enumerate every requested subtitle track. Audio filtering is two linear passes over existing metadata; it reduces duplicate EDL streams without mutating the shared JSON used by other scripts. The temporary resolving spinner updates at 4 Hz instead of 10 Hz and stops when loading finishes.

Video quality/resolution defaults, `alang`/`slang`, GPU/hardware decoding, Anime4K chains, cache sizes, display synchronization, VRR behavior and audio filters are not changed. No measured live-YouTube startup speedup is claimed; network conditions and the installed downloader still dominate many opens.

## Existing installations: safe activation

Normal updates intentionally preserve your personal `script-opts/uosc.conf`. Updating scripts alone therefore does not replace your toolbar.

With mpv closed, back up and update these files together from the same reviewed revision, retaining their paths under your active mpv configuration directory:

- `scripts/ytdl_hook.lua`
- `scripts/ytdl-sub-menu.lua`
- `scripts/smart-paste.lua`
- `scripts/modules/stream_policy.lua`

Use normal configuration loading. `--no-config` also disables discovery of this configuration's helper module. Keep the uosc release and its bundled fonts installed together. If icons appear as boxes or icon-name text, check the uosc fonts in your configuration's `fonts` directory and restart mpv.

From the repository checkout, preview the toolbar upgrade:

```console
python tools/apply_youtube_gui.py --config-dir "<active mpv config directory>"
```

Replace the placeholder with the directory containing your active `mpv.conf` and `script-opts` folder, which may be a portable configuration rather than the normal user directory. After reviewing the preview, apply it with mpv closed:

```console
python tools/apply_youtube_gui.py --config-dir "<active mpv config directory>" --apply
```

The helper changes only recognized stock toolbar/spacing values in `uosc.conf`, preserves custom values and line endings, and makes a unique `uosc.conf.pre-youtube-*.bak` backup before replacing the file. It refuses custom or duplicate toolbar definitions and symlinked targets rather than overwriting them. It does not install scripts or touch `mpv.conf`, `input.conf`, shaders or your language preferences. To undo its change, close mpv and restore the printed backup.

For a custom toolbar, manually add these two items, comma-separated, to your single existing `controls=` line instead of replacing your layout:

```text
command:content_paste:script-binding smart_paste/paste-to-open?Paste link (Ctrl+V)
<user-data/mpv/ytdl/is-youtube>command:closed_caption:script-binding ytdl_sub_menu/open?YouTube captions (Ctrl+C)
```

New installations receive the updated defaults. Existing keyboard shortcuts already reach the new caption menu once the scripts are updated, even before changing the toolbar.

## Opt-outs

Add either setting to your active `script-opts/ytdl_hook.conf` if you want the previous behavior:

```ini
# Keep every audio rendition:
best_audio_per_language=no
# Restore the implicit subtitle-enumeration path:
youtube_subs_on_demand=no
```

To adjust caption-request timeout, set `timeout=30` in `script-opts/ytdl_sub_menu.conf`. The supported range is 5–120 seconds.

## Validation and remaining manual checks

The dedicated YouTube GUI workflow runs four offline Lua suites (policy, caption lifecycle, actual-hook integration and paste safety), nine GUI-upgrade safety tests, LuaJIT syntax checks, and two required native headless-mpv checks for loading/reusing generated captions and cancelling across file changes. Native fixtures use a generated image and localhost VTT, not YouTube, a GPU or a user's configuration. Consult the PR's latest checks for actual outcomes.

The existing installer dry-run test failure is separate and has not been disabled by these changes. See [the project audit](AUDIT.md).

Before promoting this to your main installation, check the actual toolbar at your display scale, Arabic/English dubs and captions on a multi-dub YouTube video, rapid video switching, and cold/warm link-opening times. Desktop appearance, Windows/macOS playback, private/live YouTube access, and end-to-end startup performance still require real-device validation.
