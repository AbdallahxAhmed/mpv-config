"""
mpv_config CLI entry point.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from rich.console import Console
from rich.markup import escape

from mpv_config.downloaders import get_downloader

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _get_default_download_dir() -> str:
    """Find user's Downloads folder."""
    if sys.platform == "win32":
        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            d = os.path.join(userprofile, "Downloads")
            if os.path.isdir(d):
                return d
    home = Path.home()
    d = home / "Downloads"
    if d.is_dir():
        return str(d)
    return str(Path.cwd())


REPO_ENV_VAR = "MPV_CONFIG_REPO"
BOOTSTRAP_DIR_NAME = ".mpv-config-deploy"

# Subcommands whose extra options are handed to the deployer unchanged.
_FORWARDING_COMMANDS = ("install", "verify")


class RepositoryNotFoundError(RuntimeError):
    """The mpv-config repository checkout could not be located."""


def _is_repo_root(path: Path) -> bool:
    """A checkout has the deployer plus the config templates it deploys."""
    return (path / "deploy" / "deployer.py").is_file() and (path / "config").is_dir()


def find_repo_root(
    cwd: Optional[Path] = None,
    package_file: Optional[Path] = None,
    home: Optional[Path] = None,
) -> Path:
    """Locate the repository checkout that holds deploy/, config/ and the scripts.

    The wheel only ships ``mpv_config``: ``deploy/`` and the templates are never
    installed into site-packages, so the deployer always runs from a checkout.
    Search order:

    1. ``$MPV_CONFIG_REPO`` (explicit; an invalid value is an error, not a fallback)
    2. the current directory (what install.sh / install.ps1 rely on)
    3. the checkout this package was imported from (editable / source runs)
    4. ``~/.mpv-config-deploy`` (where the bootstrap scripts clone)
    """
    override = os.environ.get(REPO_ENV_VAR)
    if override:
        candidate = Path(override).expanduser()
        if _is_repo_root(candidate):
            return candidate.resolve()
        raise RepositoryNotFoundError(
            f"{REPO_ENV_VAR}={override} is not an mpv-config checkout "
            "(expected deploy/deployer.py and config/)."
        )

    if cwd is None:
        try:
            cwd = Path.cwd()
        except OSError:  # the current directory was deleted
            cwd = None
    if home is None:
        try:
            home = Path.home()
        except RuntimeError:  # no resolvable home directory
            home = None
    package_file = Path(__file__) if package_file is None else package_file

    candidates = []
    if cwd is not None:
        candidates.append(cwd)
    candidates.extend(package_file.resolve().parents)
    if home is not None:
        candidates.append(home / BOOTSTRAP_DIR_NAME)
    for candidate in candidates:
        if _is_repo_root(candidate):
            return candidate.resolve()
    raise RepositoryNotFoundError(
        "Could not find an mpv-config checkout (deploy/deployer.py and config/). "
        f"Run from inside the repository, set {REPO_ENV_VAR}=<path>, "
        "or re-run the install.sh / install.ps1 bootstrap."
    )


def _run_deployer(action: str, extra_args: Sequence[str]) -> int:
    """Run ``python -m deploy.deployer <action> ...`` from the repository checkout.

    A subprocess (never a shell) keeps the deployer independent of how mpv_config
    itself was installed; PYTHONPATH is pinned to the checkout so the ``deploy``
    and ``tools`` packages resolve there. The deployer's exit code is returned.
    """
    console = Console()
    err_console = Console(stderr=True)
    try:
        repo_root = find_repo_root()
    except RepositoryNotFoundError as exc:
        err_console.print(f"[bold red][!] {escape(str(exc))}[/bold red]")
        return 1

    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join([str(repo_root), existing]) if existing else str(repo_root)
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")

    command = [sys.executable, "-m", "deploy.deployer", action, *extra_args]
    console.print(f"[dim]Using repository: {escape(str(repo_root))}[/dim]")
    try:
        completed = subprocess.run(command, cwd=str(repo_root), env=env, shell=False, check=False)
    except KeyboardInterrupt:
        return 130
    except OSError as exc:
        err_console.print(
            f"[bold red][!] Could not start the deployer:[/bold red] {escape(str(exc))}"
        )
        return 1
    return completed.returncode


def cmd_install(args: argparse.Namespace) -> int:
    """Delegate to ``python -m deploy.deployer --install``."""
    return _run_deployer("--install", getattr(args, "deployer_args", ()))


def cmd_verify(args: argparse.Namespace) -> int:
    """Delegate to ``python -m deploy.deployer --verify``."""
    return _run_deployer("--verify", getattr(args, "deployer_args", ()))


def cmd_download(args: argparse.Namespace) -> int:
    console = Console()
    err_console = Console(stderr=True)
    output_dir = getattr(args, "output", None) or _get_default_download_dir()

    if getattr(args, "watch", False):
        try:
            from tools.core.clipboard import ClipboardService
        except ImportError:
            ClipboardService = None

        if not ClipboardService:
            err_console.print(
                "[bold red][!] ClipboardService not available for watch mode.[/bold red]"
            )
            return 1

        os.makedirs(output_dir, exist_ok=True)
        console.print(
            "[bold cyan][*] Clipboard Watcher Active.[/bold cyan] Copy media links in browser to download. Press Ctrl+C to exit."
        )
        seen_urls = set()
        import time

        while True:
            try:
                clip = ClipboardService.get_text().strip()
                if ClipboardService.is_url(clip) and clip not in seen_urls:
                    seen_urls.add(clip)
                    console.print(
                        f"\n[bold cyan][+][/bold cyan] New link copied: [yellow]{clip}[/yellow]"
                    )
                    try:
                        dl = get_downloader(clip)
                        items = dl.extract(clip)
                        if not items:
                            console.print(
                                f"[bold yellow][!] No media items found for link:[/bold yellow] {clip}"
                            )
                        for item in items:
                            if getattr(args, "quality", None) and not item.quality:
                                item.quality = str(args.quality)
                            out_path = dl.download(item, output_dir)
                            console.print(
                                f"[bold green][OK][/bold green] Saved to: [underline]{out_path}[/underline]"
                            )
                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        err_console.print(
                            f"[bold red][!] Download failed for {clip}:[/bold red] {e}"
                        )
                time.sleep(1.0)
            except KeyboardInterrupt:
                console.print("\n[bold yellow][*] Watcher stopped by user.[/bold yellow]")
                break
        return 0

    url = args.url
    if not url:
        err_console.print(
            "[bold red][!] Error: Media URL is required (or run with --watch)[/bold red]"
        )
        return 1

    downloader = get_downloader(url)
    console.print(
        f"[bold cyan][+][/bold cyan] Selected downloader: [green]{downloader.name}[/green]"
    )
    console.print(f"[bold cyan][+][/bold cyan] Extracting metadata for: [yellow]{url}[/yellow]")

    try:
        with console.status("[bold green]Extracting media info...[/bold green]"):
            items = downloader.extract(url)
    except Exception as e:
        err_console.print(f"[bold red][!] Extraction failed:[/bold red] {e}")
        return 1

    if not items:
        console.print(f"[bold yellow][!] No media items found for URL:[/bold yellow] {url}")
        return 1

    console.print(
        f"[bold green][OK][/bold green] Found {len(items)} media item(s). "
        f"Output directory: [italic]{output_dir}[/italic]"
    )

    success_count = 0
    for idx, item in enumerate(items, 1):
        if getattr(args, "quality", None) and not item.quality:
            item.quality = str(args.quality)
        console.print(
            f"\n[bold cyan][{idx}/{len(items)}][/bold cyan] Downloading: [bold]{item.title}[/bold]"
        )
        console.print(
            f"    Quality: {item.quality or 'best'} | Subtitles: {item.subtitles or 'None'}"
        )
        try:
            with console.status(f"[bold green]Downloading {item.title}...[/bold green]"):
                out_path = downloader.download(item, output_dir)
            console.print(
                f"[bold green][OK][/bold green] Saved to: [underline]{out_path}[/underline]"
            )
            success_count += 1
        except Exception as e:
            err_console.print(f"[bold red][!] Download failed for {item.title}:[/bold red] {e}")

    if success_count == 0:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mpv-config",
        description="Unified MPV Configuration & Management CLI",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # install
    sub_install = subparsers.add_parser(
        "install",
        help="Install and deploy MPV configuration",
        epilog=(
            "Options not listed here are passed to the deployer unchanged, e.g. --dry-run, "
            "--anime-preset, --scaler-tier, --mpv-profile. Run "
            "'python -m deploy.deployer --help' inside the repository for the full list."
        ),
    )
    sub_install.set_defaults(func=cmd_install)

    # verify
    sub_verify = subparsers.add_parser("verify", help="Verify MPV configuration deployment")
    sub_verify.set_defaults(func=cmd_verify)

    # download
    sub_download = subparsers.add_parser("download", help="Download media stream from URL")
    sub_download.add_argument("url", nargs="?", default=None, help="Media URL to download")
    sub_download.add_argument(
        "--watch",
        action="store_true",
        help="Watch clipboard in real-time and auto-download copied links",
    )
    sub_download.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output directory (default: ~/Downloads)",
    )
    sub_download.add_argument(
        "-q",
        "--quality",
        default=None,
        help="Max resolution quality ceiling (e.g. 1080)",
    )
    sub_download.set_defaults(func=cmd_download)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)

    forwarding = args.subcommand in _FORWARDING_COMMANDS
    if extra and not forwarding:
        parser.error(f"unrecognized arguments: {' '.join(extra)}")

    if not args.subcommand:
        parser.print_help()
        return 0

    args.deployer_args = extra if forwarding else []
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
