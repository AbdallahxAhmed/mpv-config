# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
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
