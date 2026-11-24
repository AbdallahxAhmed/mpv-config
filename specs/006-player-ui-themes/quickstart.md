# Quickstart: manual checks for spec 006

Run on KDE Wayland (143.98 Hz) and on Windows after `mpv-config update`. Use a
local 23.976 fps file with chapters, and one YouTube URL.

1. **Default look (US1-1, US1-2, SC-006).** Note the hash of every file under `scripts/uosc/`
   (`sha256sum` on Linux, `Get-FileHash` on Windows). Delete `script-opts/ui_appearance.conf`,
   run `mpv-config update`: the file is back with the defaults, and every uosc hash is unchanged.
   Open the local file. Move the pointer to the bottom:
   prev, round play/pause, next at the left; speed, subtitles, audio, playlist,
   More, fullscreen at the right; amber icons on no box. Move away: a 3 px line
   stays. Move back near: the timeline grows and shows both times.
2. **Every value (US2-2, SC-001).** More > Appearance: pick each style, each
   background, each accent, each size. Each change shows within 1 s; the
   Appearance menu stays open and marks the new value; the video does not pause.
   Bar: leave the window with the pointer, the controls stay, each on a box.
   Focus: play/pause is centred; only playlist, More, fullscreen at the right.
3. **Restart (US2-3, SC-003).** Pick bar / slate / teal / compact, quit, start
   mpv with the file: that look. Repeat the restart 10 times, with `mpv-config update`
   run before the 5th and the 10th: the look holds every time. Start `mpv` with no file (idle): note whether
   the old toolbar flashes before the theme applies (R10).
4. **Update (US2-4).** Run `mpv-config update`, start mpv: the look from step 3.
5. **Bad file (US2-5).** Write `style=huge` into `ui_appearance.conf`, start
   mpv: calm with the other three settings kept; the log (`--msg-level=ui_appearance=warn`)
   shows one warning naming `style`.
6. **Save failure (FR-014).** Make `ui_appearance.conf` read-only, pick a value:
   it applies, and an on-screen message says it was not saved. Restore the file.
7. **More menu (US3).** On the local file, open every row and compare with its
   key or today's button (Subtitles = the CC button / `Ctrl+C`, Audio = the audio-tracks
   button, Paste = `Ctrl+V`, All shortcuts = `F9`, Anime4K mode = `Ctrl+1`…, Stable volume =
   the stable-volume button). Stream quality and Download
   video are absent. On the URL they are present. Full uosc menu shows chapters,
   screenshot, aspect ratio, audio devices, Quit.
8. **Narrow window (Edge Cases).** Resize to 480 px wide in each style: no
   overlap; More and fullscreen visible.
9. **Size and stream quality (FR-008).** On the URL, switch Size: the stream-quality
   label redraws at the new size.
10. **Playback (SC-002).** With the spec 004 command line, play 60 s and make 20
    picks (every value at least once), showing and hiding the controls in
    between. KDE Wayland: delayed 0, dropped 0, vsync ratio 6 ± 0.05, mistimed
    not growing, avsync within ±5 ms. Windows: run once with picks and once
    without, same file: the run with picks is no worse on every counter.
