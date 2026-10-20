# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Faster YouTube opens: single yt-dlp client + automatic fallback**: `mpv.conf.template` pins `youtube:player_client=tv_samsung` — each extra client in yt-dlp's list adds a sequential player API round-trip, and interleaved sampling on the shipping binary measured ~4.0–4.2 s for the full default list vs ~2.8–3.7 s pinned (with an immovable ~1.1 s launch floor just for starting the yt-dlp binary). Because a single client speed must not cost reliability, `scripts/ytdl_hook.lua` now retries extraction once **without** the override when the pinned run fails, keeping yt-dlp's own multi-client behavior as the safety net. Cold opens land around ~3.5 s total; combined with the fast quality switch the second and later switches are ~1.2 s (measured end-to-end in a headless probe of the real player).
- **Quality menu shows what the video really offers**: every standard row the current stream doesn't list is labeled with `○` and hint *cap only · not in stream*; offered rows show `●`. Picking an `○` row still works — it sets the same `height<=?` ceiling, so playback gets the best the video actually has — but a 4K row on a 1080-max video no longer masquerades as an available quality.
- **Fast quality switches keep the extraction cache**: the hook's end-of-file cleanup used to wipe the cached extraction right when the replaced load ended, so the *next* switch fell back to the slow full reload (~4–6 s) and the quality menu degraded to the static guess-list (the source of phantom 4K rows on a 1080-max video). The toolbar now snapshots the parsed extraction before the fast load and restores it when the new stream settles; the stale-URL heal path still clears it when a switch genuinely fails.

### Added
- **Live download progress in the installer**: binary dependency downloads (`yt-dlp.exe`, mpv `.7z`, ffmpeg zips, alass, and the `sync-deps` yt-dlp refresh) now stream in chunks with an in-place progress line — `> yt-dlp.exe   94% |######################..|  17.7 MB/18.7 MB  24.2 MB/s  ETA 0s` — remaining silent when output is piped (`curl | bash`, CI logs). Previously the step relied on a bare `urlretrieve` and printed nothing, so a slow link read as a frozen installer. The connect phase (DNS/TLS/CDN, where no bytes flow yet) shows `> yt-dlp.exe  connecting 12s` ticks until the first byte arrives, and a 60 s socket timeout guarantees the step ends with an error instead of hanging forever.
- **`install.ps1` bootstrap is quiet and self-updating in place**: the editable pip install runs with `--quiet` (the ~25 `Requirement already satisfied` lines are gone; captured output is reprinted verbatim only when pip fails), and running the script from inside an existing checkout — including `~/.mpv-config-deploy` — now fast-forwards `git pull --ff-only` before installing, instead of silently reinstalling whatever stale commit was checked out (which is exactly how a "stuck" downloader that was already fixed could keep running).
- **Configurable default streaming quality (no more hardcoded 1080)**: the streaming ceiling is chosen in one place — `script-opts/stream_quality.conf` (`default_quality=1080`). `scripts/ytdl_hook.lua` builds `ytdl-format` from it for streams (an explicit `ytdl-format` in `mpv.conf.user` still wins; `0`/`--stream-quality best` = no cap). The player's Quality menu gives each resolution row a submenu — *Set as default* (persists to `stream_quality.conf` and re-drives the playing stream, two clicks) and *Just this video* (session-only) — plus *Apply default now* and *Default: any resolution*; changes persist with no redeploy. Quality switches no longer re-run yt-dlp: the toolbar reuses the signed stream URLs from the last extraction and loads the new resolution + audio track directly (fallback to the full reload path when the URLs have expired), cutting a switch from ~4–6 s to ~1 s. Quality OSD messages now name the rescale when the source doesn't match the window (e.g. *720p (upscale: 1920x1080 display)*), so stats-for-nerds' *Display: Resolution* line — which is just the window size — isn't mistaken for stream quality. The installer seeds fresh deployments via `--stream-quality` (`best`/`144`…`4320`, default `1080`); existing files are personal and never rewritten, existing mpv.conf pins are migrated by the deployer's repair pass.
- `mpv-config update`, `rollback`, `status`, `sync-deps` and `uninstall` (also `python -m deploy.deployer --update`, `--rollback`, `--status`, `--sync-deps`, `--uninstall`), ported from the pre-1.0 `setup.py`.

### Fixed
- **`install` froze forever inside `Downloading yt-dlp.exe…` on a non-elevated Windows shell**: the yt-dlp refresh targets `C:\Program Files\mpv\yt-dlp`, and CPython's `tempfile.mkstemp` retries `PermissionError` effectively forever when the Windows ACL denies file creation but `os.access()` misreports the directory as writable — silent, no temp file, no error, and nothing before it in the flow renders. The installer now creates the tmp file itself with a bounded loop and fails in milliseconds with an actionable message ("…Re-run the installer from an elevated (Administrator) PowerShell to install into C:\Program Files\mpv"). This is also why no run after 2026-08-23 (the last elevated one) ever refreshed yt-dlp.
- **`rollback <path>` accepted any directory** and copied it over the live configuration. It now restores only one of the configuration's own `mpv.backup.*` folders (full path or bare name) and lists the available ones otherwise.
- **`uninstall` could delete an unrelated `~/.local/bin/mpv-config`** and ignored the private virtual environment `install.sh` creates. It now removes only a symlink into that environment, and `--remove-install-dir` also removes the environment (last, because the command runs from it).
- **`uninstall --purge-config` left `.audit-log.json` behind**, recreating the config directory. The purge is now complete.
- **Windows shortcuts could target `mpv.com`**: `shutil.which("mpv")` returns the console wrapper first because `.COM` leads `PATHEXT`. Shortcuts now target `mpv.exe`.
- `tools/register_extension.py` isolates the unpacked extension, CRX, and private signing key into user data (`%LOCALAPPDATA%/mpv-config/extension` or `~/.local/share/mpv-config/extension`) outside the repository, and `install.ps1` bootstraps via `--editable` and `--ff-only` git pulls.
- **`mpv-config install` / `verify` did nothing**: both subcommands were placeholders that printed `Executing: ...` and returned success. They now run `python -m deploy.deployer --install` / `--verify` in a subprocess (no shell, `PYTHONPATH` pinned to the checkout) and return its exit code. Unknown options such as `--dry-run` are forwarded to the deployer.
- **`python -m deploy.deployer` was silent**: the module had no entry point, so `--install` exited 0 without doing anything. It now has `main()` with argparse (`--install`, `--verify`, `--dry-run`, `--mpv-profile`, `--anime-preset`, `--scaler-tier`, `--display-mode`, `--dither-depth`, `--mpv-version`), fail-closed ordering (fetch, dependencies, transactional deploy, verification) and exit codes 0 / 1 / 2 / 130. Option defaults come from `deploy()`'s own signature.
- **`install.sh` failed on externally managed Pythons (PEP 668)**: `pip install --user .` is refused there (reproduced on Ubuntu 24.04), so the bootstrap stopped before reaching the CLI. It now installs the CLI editable into a private virtual environment (`~/.local/share/mpv-config/venv`), links `mpv-config` into `~/.local/bin` without overwriting an unrelated file, checks for Python 3.10+, and updates an existing clone with `git pull --ff-only`.
- **Tests no longer write into real locations**: tests that saved cookies or probed install directories used `%APPDATA%`, `%ProgramFiles%`, `~/Desktop/mpv-config`, the repository root or the working directory; they now use scratch directories.

### Security
- `.gitignore` now also covers `.env`, `*.p12` and `*.pfx`.
- Removed hard-coded personal paths from tracked files (the obsolete one-off `create-clean-repo.ps1` and absolute `file:///` links in `specs/`).
- Added `tests/test_repo_hygiene.py`, which fails if key material, private-key blocks or personal paths become tracked.

## [1.0.0] - 2026-10-07

### Changed
- **Packaging & Build System**: Migrated to modern `pyproject.toml` using `hatchling` as the build backend.
- **Unified CLI (`mpv-config`)**: Introduced a consolidated, class-based CLI entry point supporting `install`, `verify`, and `download` subcommands.
- **Plugin-Based Downloader Framework**: Re-architected media streaming and downloading into an extensible plugin architecture (`BaseDownloader`, `MediaItem`, `GenericDownloader`) backed by native `yt-dlp` and FFmpeg.
- **Clipboard Monitoring**: Added real-time `--watch` clipboard monitoring with per-URL exception recovery to prevent background daemon crashes.
- **CI/CD Pipelines**: Added GitHub Actions workflows for multi-OS/multi-Python test matrices (`test.yml`) with caching and automated trusted publishing to PyPI (`release.yml`).
- **Developer Experience**: Added `.pre-commit-config.yaml` with Ruff linter, Ruff formatter, and standard hooks, alongside `requirements-dev.txt`.
- **Documentation**: Rewrote `README.md` to provide a clean, modern, and professional overview of configuration deployment, usage, and development guidelines.

### Removed
- **Adult Content Systems**: Permanently removed all adult content extractors, search engines, and scrapers across all languages.
- **Rust TUI Residue**: Completely eliminated `tools/media-tui/` and related batch launchers to maintain a unified, single-language Python architecture.
- **Legacy Bootstrappers & Scripts**: Purged legacy `setup.py` and standalone `tools/mpvdl.py` in favor of the unified CLI and modern packaging.
- **Installer Bloat**: Streamlined `install.sh` and `install.ps1` into thin, minimal bootstrapping wrappers delegating directly to `mpv-config`.

### Fixed
- **Cross-Platform Compatibility**: Resolved POSIX/Windows pathing and binary lookup differences across Linux (Wayland & X11), macOS, and Windows.
- **Display Frame Pacing**: Fixed mpv profile condition drifts (Wayland 144Hz profile, linear tscale filtering, and timing offset).
- **Test Suite Stability**: Restored and expanded full unit test coverage to 194 passing tests with 0 failures and 0 errors.
