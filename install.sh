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

if [ -f "pyproject.toml" ] && [ -d "src/mpv_config" ]; then
    TARGET_DIR="$(pwd)"
else
    command -v git >/dev/null 2>&1 || die "git is required to fetch the repository."
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
if [ ! -x "${VENV_PYTHON}" ]; then
    echo "Creating virtual environment at ${VENV_DIR}..."
    rm -rf "${VENV_DIR}"
    mkdir -p "${DATA_DIR}"
    "${PYTHON_BIN}" -m venv "${VENV_DIR}" || {
        rm -rf "${VENV_DIR}"
        die "could not create a virtual environment. On Debian/Ubuntu: sudo apt install python3-venv"
    }
fi

# Editable, so the CLI can always find this checkout: deploy/ and config/ are not packaged.
"${VENV_PYTHON}" -m pip install --quiet --editable "${TARGET_DIR}"

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
