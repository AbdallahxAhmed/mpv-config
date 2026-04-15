#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  MPV Auto-Deploy — Linux/macOS One-Liner Installer
#
#  Usage:
#    curl -fsSL https://raw.githubusercontent.com/AbdallahxAhmed/mpv-config/main/install.sh | bash
#
#  Or with git:
#    git clone https://github.com/AbdallahxAhmed/mpv-config.git && cd mpv-config && python3 setup.py
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

REPO="AbdallahxAhmed/mpv-config"
BRANCH="main"
INSTALL_DIR="${HOME}/.mpv-deploy"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║       MPV Auto-Deploy — Bootstrap            ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ─── Step 1: Check prerequisites ─────────────────────────────────
echo "[1/4] Checking prerequisites..."

# Python 3
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "ERROR: Python 3 is required but not found."
    echo ""
    echo "Install it with:"
    if command -v pacman &>/dev/null; then
        echo "  sudo pacman -S python"
    elif command -v apt &>/dev/null; then
        echo "  sudo apt install python3"
    elif command -v brew &>/dev/null; then
        echo "  brew install python@3"
    fi
    exit 1
fi

PY_VERSION=$($PYTHON --version 2>&1)
echo "  ✓ $PY_VERSION"

# Git (preferred) or curl (fallback)
USE_GIT=false
if command -v git &>/dev/null; then
    USE_GIT=true
    echo "  ✓ git found"
elif command -v curl &>/dev/null; then
    echo "  ✓ curl found (will download zip)"
else
    echo "ERROR: Neither git nor curl found. Install one of them."
    exit 1
fi

# ─── Step 2: Download the repo ────────────────────────────────────
echo ""
echo "[2/4] Downloading mpv-config..."

if [ -d "$INSTALL_DIR" ]; then
    echo "  → Removing old install dir..."
    rm -rf "$INSTALL_DIR"
fi

if $USE_GIT; then
    git clone --depth=1 "https://github.com/${REPO}.git" "$INSTALL_DIR" 2>/dev/null
    echo "  ✓ Cloned successfully"
else
    ZIPURL="https://github.com/${REPO}/archive/refs/heads/${BRANCH}.zip"
    TMPZIP=$(mktemp /tmp/mpv-config-XXXX.zip)
    curl -fsSL "$ZIPURL" -o "$TMPZIP"
    mkdir -p "$INSTALL_DIR"

    if command -v unzip &>/dev/null; then
        unzip -q "$TMPZIP" -d /tmp/mpv-config-extract
    elif $PYTHON -c "import zipfile" 2>/dev/null; then
        $PYTHON -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall('/tmp/mpv-config-extract')" "$TMPZIP"
    fi

    # Move extracted contents (strip top-level dir)
    mv /tmp/mpv-config-extract/mpv-config-${BRANCH}/* "$INSTALL_DIR/"
    rm -rf /tmp/mpv-config-extract "$TMPZIP"
    echo "  ✓ Downloaded and extracted"
fi

# ─── Step 3: Install build dependencies for ffsubsync ─────────────
echo ""
echo "[3/4] Ensuring build dependencies..."

# ffsubsync needs C compiler + Python headers
if command -v pacman &>/dev/null; then
    # Arch-based
    echo "  → Arch detected: ensuring base-devel + python headers..."
    sudo pacman -S --noconfirm --needed base-devel python 2>/dev/null || true
elif command -v apt &>/dev/null; then
    # Debian/Ubuntu
    echo "  → Debian/Ubuntu detected: ensuring build-essential + python3-dev..."
    sudo apt update -qq 2>/dev/null
    sudo apt install -y -qq build-essential python3-dev python3-venv 2>/dev/null || true
elif command -v brew &>/dev/null; then
    # macOS — Xcode CLI tools should be enough
    echo "  → macOS detected: checking Xcode CLI tools..."
    xcode-select --install 2>/dev/null || true
fi

# Pin setuptools for ffsubsync compatibility
echo "  → Ensuring compatible pip/setuptools..."
$PYTHON -m pip install --quiet --upgrade "pip>=23.0" "setuptools<74.0" wheel 2>/dev/null || true

# ─── Step 4: Run the deployer ─────────────────────────────────────
echo ""
echo "[4/4] Running MPV Auto-Deploy..."
echo ""

cd "$INSTALL_DIR"
$PYTHON setup.py

echo ""
echo "─────────────────────────────────────────────────"
echo "  Cleanup: install dir kept at $INSTALL_DIR"
echo "  Re-run:  cd $INSTALL_DIR && $PYTHON setup.py"
echo "  Update:  cd $INSTALL_DIR && $PYTHON setup.py --update"
echo "─────────────────────────────────────────────────"
