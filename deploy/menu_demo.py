"""menu_demo.py — try the install-time preset menu without deploying.

python -m deploy.menu_demo

Interactive TTY: arrow keys, Enter, digits 1-8, Esc. Piped stdin line
fallback: Enter / a number / the preset name. ``deploy.install`` runs the
same menu for real; nothing here touches the configuration.
"""

from deploy import ui
from deploy.registry import ANIME4K_PRESETS


def main():
    chosen = ui.menu_select("Anime4K mode", list(ANIME4K_PRESETS))
    print(f"Chosen: {chosen}")


if __name__ == "__main__":
    main()
