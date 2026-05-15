# Changelog

## Unreleased
### Breaking changes
- Windows default `hwdec` is now `d3d11va` (use `-copy` suffix in `mpv.conf.user` if you rely on CPU `vf=` filters).
- `audio-channels` no longer forced to stereo — surround receivers now receive multichannel output.
- `profile-restore` behavior corrected so Anime4K shaders no longer leak into live-action profiles.
- Cache defaults reduced for local files; streaming users may want higher `cache-secs`.
- VRR mode is now opt-in via `--display-mode vrr` (default is fixed 144Hz).
