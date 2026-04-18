set -euo pipefail
_gum_available() { return 0; }
_gum_spin() {
    local title=$1
    shift
    if _gum_available; then
        gum spin --spinner dot --title "$title" -- "$@"
    else
        echo "  → $title"
        "$@"
    fi
}
_gum_spin "Testing..." sleep 2
echo "Done"
