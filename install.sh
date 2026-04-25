#!/usr/bin/env bash
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
BRANCH="${MPV_BRANCH:-main}"
INSTALL_DIR="${HOME}/.mpv-deploy"
LAUNCHER_DIR="${HOME}/.local/bin"
LAUNCHER_PATH="${LAUNCHER_DIR}/mpv-config"

GUM_AVAILABLE=false

_install_gum() {
    if command -v gum &>/dev/null; then
        GUM_AVAILABLE=true
        return 0
    fi
    
    echo "  → Installing gum for better UI..."
    if command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm gum 2>/dev/null || true
    elif command -v apt &>/dev/null; then
        sudo mkdir -p /etc/apt/keyrings
        curl -fsSL https://repo.charm.sh/apt/gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/charm.gpg 2>/dev/null || true
        echo "deb [signed-by=/etc/apt/keyrings/charm.gpg] https://repo.charm.sh/apt/ * *" | sudo tee /etc/apt/sources.list.d/charm.list > /dev/null
        sudo apt update -qq 2>/dev/null
        sudo apt install -y -qq gum 2>/dev/null || true
    elif command -v brew &>/dev/null; then
        brew install gum 2>/dev/null || true
    fi

    if command -v gum &>/dev/null; then
        GUM_AVAILABLE=true
    fi
}

_gum_available() {
    if [ "$GUM_AVAILABLE" = "true" ]; then
        return 0
    else
        return 1
    fi
}

_styled_echo() {
    local color=$1
    local text=$2
    if _gum_available; then
        gum style --foreground "$color" "$text"
    else
        local ansi="0"
        case "$color" in
            cyan) ansi="36" ;;
            green) ansi="32" ;;
            yellow) ansi="33" ;;
            red) ansi="31" ;;
            white) ansi="37" ;;
            dim|gray) ansi="90" ;;
        esac
        echo -e "\033[${ansi}m${text}\033[0m"
    fi
}

_confirm() {
    local prompt=$1
    if _gum_available; then
        if [ -r /dev/tty ]; then
            gum confirm "$prompt" < /dev/tty
        else
            gum confirm "$prompt"
        fi
    else
        local reply
        if [ -r /dev/tty ]; then
            read -p "$prompt [Y/n] " reply < /dev/tty
        else
            read -p "$prompt [Y/n] " reply
        fi
        [[ -z "$reply" || "$reply" == [Yy]* ]]
    fi
}

_gum_spin() {
    local title=$1
    shift
    if _gum_available; then
        gum spin --spinner dot --title "$title" -- "$@"
    else
        _styled_echo "dim" "  → $title"
        "$@"
    fi
}

_install_gum

_styled_echo "cyan" ""
_styled_echo "cyan" "╔══════════════════════════════════════════════╗"
_styled_echo "cyan" "║       MPV Auto-Deploy — Bootstrap            ║"
_styled_echo "cyan" "╚══════════════════════════════════════════════╝"
_styled_echo "cyan" ""

# ─── Step 1: Check prerequisites ─────────────────────────────────
_styled_echo "white" "[1/4] Checking prerequisites..."

# Python 3
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    _styled_echo "red" "ERROR: Python 3 is required but not found."
    _styled_echo "white" ""
    _styled_echo "white" "Install it with:"
    if command -v pacman &>/dev/null; then
        _styled_echo "dim" "  sudo pacman -S python"
    elif command -v apt &>/dev/null; then
        _styled_echo "dim" "  sudo apt install python3"
    elif command -v brew &>/dev/null; then
        _styled_echo "dim" "  brew install python@3"
    fi
    exit 1
fi

PY_VERSION=$($PYTHON --version 2>&1)
_styled_echo "green" "  ✓ $PY_VERSION"

# Git (preferred) or curl (fallback)
USE_GIT=false
if command -v git &>/dev/null; then
    USE_GIT=true
    _styled_echo "green" "  ✓ git found"
elif command -v curl &>/dev/null; then
    _styled_echo "green" "  ✓ curl found (will download zip)"
else
    _styled_echo "red" "ERROR: Neither git nor curl found. Install one of them."
    exit 1
fi

# ─── Step 2: Download the repo ────────────────────────────────────
_styled_echo "white" ""
_styled_echo "white" "[2/4] Downloading mpv-config..."

if [ -e "$INSTALL_DIR" ]; then
    _styled_echo "dim" "  → Removing old install dir..."
    rm -rf "$INSTALL_DIR"
fi

if $USE_GIT; then
    if ! _gum_spin "Cloning repository..." git clone --depth=1 -b "$BRANCH" "https://github.com/${REPO}.git" "$INSTALL_DIR" >/tmp/mpv-deploy-git.log 2>&1 < /dev/null; then
        _styled_echo "red" "  ✗ Failed to clone repository. Error log:"
        cat /tmp/mpv-deploy-git.log
        exit 1
    fi
    _styled_echo "green" "  ✓ Cloned successfully"
else
    ZIPURL="https://github.com/${REPO}/archive/refs/heads/${BRANCH}.zip"
    TMPZIP=$(mktemp /tmp/mpv-config-XXXX.zip)
    _gum_spin "Downloading zip archive..." curl -fsSL "$ZIPURL" -o "$TMPZIP" < /dev/null
    mkdir -p "$INSTALL_DIR"

    if command -v unzip &>/dev/null; then
        _gum_spin "Extracting archive..." unzip -q "$TMPZIP" -d /tmp/mpv-config-extract < /dev/null
    elif $PYTHON -c "import zipfile" 2>/dev/null; then
        _gum_spin "Extracting archive..." $PYTHON -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall('/tmp/mpv-config-extract')" "$TMPZIP" < /dev/null
    fi

    mv /tmp/mpv-config-extract/mpv-config-${BRANCH}/* "$INSTALL_DIR/"
    rm -rf /tmp/mpv-config-extract "$TMPZIP"
    _styled_echo "green" "  ✓ Downloaded and extracted"
fi

# ─── Step 3: Install build dependencies for ffsubsync ─────────────
_styled_echo "white" ""
_styled_echo "white" "[3/4] Ensuring build dependencies..."

if command -v pacman &>/dev/null; then
    _styled_echo "dim" "  → Arch detected: ensuring base-devel + python headers..."
    sudo pacman -S --noconfirm --needed base-devel python 2>/dev/null || true
elif command -v apt &>/dev/null; then
    _styled_echo "dim" "  → Debian/Ubuntu detected: ensuring build-essential + python3-dev..."
    sudo apt update -qq 2>/dev/null
    sudo apt install -y -qq build-essential python3-dev python3-venv 2>/dev/null || true
elif command -v brew &>/dev/null; then
    _styled_echo "dim" "  → macOS detected: checking Xcode CLI tools..."
    xcode-select --install 2>/dev/null || true
fi

# ── Step 3b: Install rich (Category B) ─────────────────────────
# Try system package first, venv fallback handled by setup.py bootstrap
if command -v pacman &>/dev/null; then
    _gum_spin "Installing python-rich via pacman..." \
        sudo pacman -S --noconfirm --needed python-rich 2>/dev/null || true
elif command -v apt &>/dev/null; then
    _gum_spin "Installing python3-rich via apt..." \
        sudo apt install -y -qq python3-rich 2>/dev/null || true
elif command -v brew &>/dev/null; then
    _gum_spin "Installing rich via brew..." \
        brew install python-rich 2>/dev/null || true
fi

# If the above failed, setup.py's bootstrap guard will handle venv fallback
if ! $PYTHON -c "import rich" 2>/dev/null; then
    _styled_echo "dim" "  → rich not available as system package; setup.py will bootstrap via venv"
fi

# ─── Step 4: Run the deployer ─────────────────────────────────────
_styled_echo "white" ""
_styled_echo "white" "[4/4] Running MPV Auto-Deploy..."
_styled_echo "white" ""

cd "$INSTALL_DIR"
if [ -r /dev/tty ]; then
    $PYTHON setup.py < /dev/tty
else
    $PYTHON setup.py
fi

# ─── Optional launcher (run from any path) ─────────────────────────
_styled_echo "white" ""
if _confirm "Create launcher command (mpv-config)?"; then
    _styled_echo "dim" "  [+] Creating launcher command (mpv-config)..."
    mkdir -p "$LAUNCHER_DIR"
    cat > "$LAUNCHER_PATH" <<EOF
#!/usr/bin/env bash
exec $PYTHON "$INSTALL_DIR/setup.py" "\$@"
EOF
    chmod +x "$LAUNCHER_PATH"
    _styled_echo "green" "  ✓ Launcher created: $LAUNCHER_PATH"

    IN_PATH=false
    IFS=':' read -r -a PATH_PARTS <<< "$PATH"
    for part in "${PATH_PARTS[@]}"; do
        if [[ "$part" == "$LAUNCHER_DIR" ]]; then
            IN_PATH=true
            break
        fi
    done

    if ! $IN_PATH; then
        _styled_echo "yellow" "  ! '$LAUNCHER_DIR' is not in PATH."
        _styled_echo "yellow" "    Add this line to your shell profile:"
        _styled_echo "yellow" "    export PATH=\"$LAUNCHER_DIR:\$PATH\""
    fi
else
    _styled_echo "dim" "  Skipped launcher creation."
fi

_styled_echo "cyan" ""
_styled_echo "cyan" "─────────────────────────────────────────────────"
_styled_echo "white" "  Cleanup: install dir kept at $INSTALL_DIR"
_styled_echo "white" "  Re-run:  mpv-config"
_styled_echo "white" "  Update:  mpv-config --update"
_styled_echo "white" "  Remove:  mpv-config --uninstall --purge-config --remove-backups --remove-deps --remove-install-dir"
_styled_echo "cyan" "─────────────────────────────────────────────────"
