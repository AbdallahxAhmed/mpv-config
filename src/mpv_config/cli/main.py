"""
mpv_config CLI entry point.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from rich.console import Console

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


def cmd_install(args: argparse.Namespace) -> int:
    print("Executing: install...")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    print("Executing: verify...")
    return 0


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
    sub_install = subparsers.add_parser("install", help="Install and deploy MPV configuration")
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
    args = parser.parse_args(argv)

    if not args.subcommand:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
