#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/AbdallahxAhmed/mpv-config.git"
TARGET_DIR="${HOME}/.mpv-config-deploy"

if [ -f "pyproject.toml" ] && [ -d "src/mpv_config" ]; then
    TARGET_DIR="$(pwd)"
elif [ -d "${TARGET_DIR}/.git" ]; then
    echo "Updating existing repository at ${TARGET_DIR}..."
    git -C "${TARGET_DIR}" pull --quiet
else
    echo "Cloning repository to ${TARGET_DIR}..."
    git clone --quiet "${REPO_URL}" "${TARGET_DIR}"
fi

cd "${TARGET_DIR}"

PYTHON_BIN="python3"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    PYTHON_BIN="python"
fi

echo "Bootstrapping mpv-config..."
"${PYTHON_BIN}" -m pip install --user .
"${PYTHON_BIN}" -m mpv_config install "$@"
