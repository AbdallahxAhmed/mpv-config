# mpv-config

[![CI](https://github.com/AbdallahxAhmed/mpv-config/actions/workflows/test.yml/badge.svg)](https://github.com/AbdallahxAhmed/mpv-config/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> Unified MPV configuration, deployment, and media download toolkit.

`mpv-config` transforms [mpv](https://mpv.io) into an out-of-the-box, high-fidelity media player with curated Lua scripts, Anime4K upscaling shaders, platform-aware hardware decoding, and an integrated high-speed media downloader.

---

## ✨ Features

- 🎨 **Anime4K & Upscaling:** Automated setup of Anime4K shader chains and high-quality EWA scalers for crisp playback.
- ⚡ **Cross-Platform Auto-Detection:** Automatically tunes video outputs, hardware decoders (`d3d11va`, `nvdec`, `vaapi`), and display sync across Windows, Linux (Wayland/X11), and macOS.
- 🚀 **Plugin-Based Downloader:** Direct in-process `yt-dlp` media extraction and download engine with FFmpeg remuxing and quality caps.
- 📋 **Real-Time Clipboard Watcher:** Seamless background monitoring (`--watch`) that detects and downloads video links copied to your clipboard.
- 🛡️ **Zero-Drift Architecture:** Fully verified deployment with rollback safety and automated system health checks.

---

## 📦 Installation

`mpv-config` deploys from a checkout of this repository (`deploy/`, `config/` and `scripts/` are not
part of the installed package), so install it **editable** from a clone. The command can then find
the checkout from any directory:

```bash
git clone https://github.com/AbdallahxAhmed/mpv-config.git
cd mpv-config

# Isolated global CLI install via pipx (recommended)
pipx install --editable .

# Or, inside a virtual environment
pip install --editable .
```

A regular (non-editable) install only works while you run it from inside the clone, or with
`MPV_CONFIG_REPO` pointing at the clone.

### Quick Bootstrap

<!-- Repository URL: https://github.com/AbdallahxAhmed/mpv-config -->
#### Windows (PowerShell)
```powershell
irm https://raw.githubusercontent.com/AbdallahxAhmed/mpv-config/main/install.ps1 | iex
```

#### Linux / macOS
```bash
curl -fsSL https://raw.githubusercontent.com/AbdallahxAhmed/mpv-config/main/install.sh | bash
```

The script installs the CLI into its own virtual environment (`~/.local/share/mpv-config/venv`) and
links `mpv-config` into `~/.local/bin`, so it also works on distributions that refuse
`pip install --user` (PEP 668, e.g. Ubuntu 24.04). It needs Python 3.10+ (on Debian/Ubuntu also
`python3-venv`). Pass options through with `... | bash -s -- --dry-run`.

---

## 🚀 Usage

`mpv-config` provides a unified command-line interface:

### 1. Install & Deploy Configuration
Deploy curated configurations, scripts, and shaders to your local MPV setup:
```bash
mpv-config install
```

Preview first with `mpv-config install --dry-run`: nothing is downloaded, installed or replaced.
Options such as `--anime-preset`, `--scaler-tier`, `--mpv-profile`, `--display-mode`,
`--dither-depth` and `--mpv-version` are passed straight to the deployer; run
`python -m deploy.deployer --help` inside the repository for the full list.

`mpv-config install` runs the deployer from the repository checkout (`deploy/` and `config/` are
not part of the installed package). It looks for the checkout in `$MPV_CONFIG_REPO`, then the
current directory, then the checkout the package was installed from (editable installs), then
`~/.mpv-config-deploy` (where the bootstrap scripts clone). It exits with the deployer's status.

### 2. Verify Installation
Run comprehensive self-diagnostic checks to verify binaries, shaders, and configs:
```bash
mpv-config verify
```

### 3. Download Media
Download streams directly with automatic format selection and FFmpeg merging:
```bash
# Download a video (defaults to ~/Downloads at up to 1080p)
mpv-config download "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Specify custom destination and quality ceiling
mpv-config download "https://example.com/video" -o ~/Videos -q 720
```

### 4. Background Clipboard Watcher
Automatically capture and download media links copied in your browser:
```bash
mpv-config download --watch
```

---

## 🛠️ Development

### Setup Development Environment
```bash
# Clone the repository
git clone https://github.com/AbdallahxAhmed/mpv-config.git
cd mpv-config

# Install in editable mode with development dependencies
pip install -e .
pip install -r requirements-dev.txt

# Install pre-commit git hooks
pre-commit install
```

### Running Tests & Quality Checks
```bash
# Run unit test suite
python -m unittest discover -s tests

# Run linter and code formatting
ruff check .
ruff format .
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
