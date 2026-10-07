# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
