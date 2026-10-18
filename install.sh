#!/usr/bin/env bash
# Bootstrap mpv-config on Linux/macOS: fetch the repository, install the CLI into a private
# virtual environment (never into the system Python, which PEP 668 distributions and Homebrew
# protect, including against `pip install --user`), then run `mpv-config install`.
# Extra arguments are passed through, e.g.: curl -fsSL .../install.sh | bash -s -- --dry-run
set -euo pipefail

REPO_URL="https://github.com/AbdallahxAhmed/mpv-config.git"
TARGET_DIR="${HOME}/.mpv-config-deploy"
DATA_DIR="${XDG_DATA_HOME:-${HOME}/.local/share}/mpv-config"
VENV_DIR="${DATA_DIR}/venv"
BIN_DIR="${HOME}/.local/bin"

die() {
    echo "error: $*" >&2
    exit 1
}

ensure_git() {
    command -v git >/dev/null 2>&1 && return 0
    echo "git not found — installing it automatically..."
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get install -y git
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y git
    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -S --noconfirm --needed git
    elif command -v brew >/dev/null 2>&1; then
        brew install git
    else
        return 1
    fi
}

if [ -f "pyproject.toml" ] && [ -d "src/mpv_config" ]; then
    TARGET_DIR="$(pwd)"
else
    ensure_git || die "git is required to fetch the repository, and installing it automatically failed."
    if [ -d "${TARGET_DIR}/.git" ]; then
        echo "Updating existing repository at ${TARGET_DIR}..."
        git -C "${TARGET_DIR}" pull --ff-only --quiet
    else
        echo "Cloning repository to ${TARGET_DIR}..."
        git clone --quiet "${REPO_URL}" "${TARGET_DIR}"
    fi
fi

cd "${TARGET_DIR}"

PYTHON_BIN=""
for candidate in python3 python; do
    if command -v "${candidate}" >/dev/null 2>&1; then
        PYTHON_BIN="${candidate}"
        break
    fi
done
[ -n "${PYTHON_BIN}" ] || die "Python 3.10 or newer is required, but neither python3 nor python is on PATH."
"${PYTHON_BIN}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' ||
    die "Python 3.10 or newer is required (found: $("${PYTHON_BIN}" --version 2>&1))."

echo "Bootstrapping mpv-config..."
VENV_PYTHON="${VENV_DIR}/bin/python"
USE_UV=""
# Debian/Ubuntu ship Python without ensurepip unless python3-venv is
# installed (PEP 668). uv can create the venv without it, so fall back to
# uv (installed automatically via its official installer) before dying.
if ! "${PYTHON_BIN}" -m ensurepip --version >/dev/null 2>&1; then
    echo "ensurepip unavailable (Debian/Ubuntu: python3-venv missing) — falling back to uv..."
    if command -v uv >/dev/null 2>&1; then
        USE_UV=1
    elif /bin/sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'; then
        case ":${PATH}:" in
            *":${HOME}/.local/bin:"*) ;;
            *) PATH="${HOME}/.local/bin:${PATH}"; export PATH ;;
        esac
        USE_UV=1
    fi
fi

if [ ! -x "${VENV_PYTHON}" ]; then
    echo "Creating virtual environment at ${VENV_DIR}..."
    rm -rf "${VENV_DIR}"
    mkdir -p "${DATA_DIR}"
    if [ -n "${USE_UV}" ]; then
        uv venv --python "${PYTHON_BIN}" "${VENV_DIR}" || {
            rm -rf "${VENV_DIR}"
            die "uv could not create the virtual environment."
        }
    else
        "${PYTHON_BIN}" -m venv "${VENV_DIR}" || {
            echo "venv creation failed — trying Debian/Ubuntu python3-venv..."
            if command -v apt-get >/dev/null 2>&1 && sudo apt-get install -y python3-venv; then
                rm -rf "${VENV_DIR}"
                "${PYTHON_BIN}" -m venv "${VENV_DIR}"
            else
                rm -rf "${VENV_DIR}"
                die "could not create a virtual environment. On Debian/Ubuntu: sudo apt install python3-venv"
            fi
        }
    fi
fi

# Editable, so the CLI can always find this checkout: deploy/ and config/ are not packaged.
if [ -n "${USE_UV}" ]; then
    # uv-created venvs have no pip module — install through uv instead.
    uv pip install --python "${VENV_PYTHON}" --quiet --editable "${TARGET_DIR}"
else
    "${VENV_PYTHON}" -m pip install --quiet --editable "${TARGET_DIR}"
fi

# Put `mpv-config` on PATH without touching an unrelated file that is already there.
mkdir -p "${BIN_DIR}"
if [ -L "${BIN_DIR}/mpv-config" ] || [ ! -e "${BIN_DIR}/mpv-config" ]; then
    ln -sfn "${VENV_DIR}/bin/mpv-config" "${BIN_DIR}/mpv-config"
else
    echo "note: ${BIN_DIR}/mpv-config already exists and is not a symlink; left unchanged." >&2
fi
case ":${PATH}:" in
    *":${BIN_DIR}:"*) ;;
    *) echo "note: ${BIN_DIR} is not on your PATH; add it to run 'mpv-config' directly." >&2 ;;
esac

exec "${VENV_PYTHON}" -m mpv_config install "$@"
