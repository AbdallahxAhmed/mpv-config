#!/usr/bin/env python3
"""
hsearch.py — Multi-Site Anime & Hentai Quality Comparison & Streaming TUI.
Searches HentaiMama, Sukebei Nyaa, Hanime, HentaiWorld, and HentaiHaven in parallel,
evaluates resolution, source quality, censorship, subtitles, and speed,
and provides 1-key streaming in MPV or accelerated downloading via aria2c/yt-dlp.
"""

import os
import sys
import shutil
import argparse
import subprocess
import pathlib

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add repo root to sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from rich.console import Console
from rich.panel import Panel
from tools.search.orchestrator import multi_search
from tools.search.ui import run_fzf_selector, run_rich_fallback, render_preview_cli
from tools.search.models import SearchResult

console = Console()


def copy_to_clipboard(text: str) -> bool:
    """Copy text to Windows clipboard."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL

        CF_UNICODETEXT = 13
        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            data_bytes = (text + "\0").encode("utf-16le")
            h_mem = kernel32.GlobalAlloc(0x0042, len(data_bytes))  # GMEM_MOVEABLE | GMEM_ZEROINIT
            if not h_mem:
                return False
            ptr = kernel32.GlobalLock(h_mem)
            if not ptr:
                return False
            try:
                ctypes.memmove(ptr, data_bytes, len(data_bytes))
            finally:
                kernel32.GlobalUnlock(h_mem)
            user32.SetClipboardData(CF_UNICODETEXT, h_mem)
            return True
        finally:
            user32.CloseClipboard()
    except Exception:
        return False


def find_mpv() -> str:
    """Locate MPV executable."""
    which = shutil.which("mpv")
    if which:
        return which
    candidates = [
        r"C:\Program Files\mpv\mpv.exe",
        r"C:\Program Files\mpv\mpv.com",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\mpv.exe"),
        os.path.expandvars(r"%USERPROFILE%\scoop\apps\mpv\current\mpv.exe"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return "mpv"


def play_in_mpv(result: SearchResult):
    """Launch MPV player for the selected stream or magnet."""
    mpv_exe = find_mpv()
    console.print(f"\n[bold green]🎬 Launching MPV Player:[/bold green] [white]{result.title}[/white]")
    console.print(f"[dim]URL: {result.url}[/dim]\n")

    cmd = [
        mpv_exe,
        "--force-window=yes",
        f"--title={result.title}",
        result.url
    ]

    # For web streams, pass referer headers if needed
    if result.provider == "HentaiMama":
        cmd.extend(["--http-header-fields=Referer: https://hentaimama.io/"])
    elif result.provider == "Hanime":
        cmd.extend(["--http-header-fields=Referer: https://hanime.tv/"])

    try:
        subprocess.run(cmd)
    except Exception as e:
        console.print(f"[bold red]Failed to launch MPV:[/bold red] {e}")


def download_item(result: SearchResult):
    """Download item via aria2c or yt-dlp / universal downloader."""
    dl_url = result.download_url or result.url
    console.print(f"\n[bold cyan]⚡ Starting Turbo Download:[/bold cyan] [white]{result.title}[/white]")
    console.print(f"[dim]Source: {result.provider} | URL: {dl_url}[/dim]\n")

    downloads_dir = os.path.join(os.environ.get("USERPROFILE", ""), "Downloads")
    os.makedirs(downloads_dir, exist_ok=True)

    if result.delivery == "Torrent (P2P)" or dl_url.endswith(".torrent") or dl_url.startswith("magnet:"):
        aria2_exe = shutil.which("aria2c")
        if aria2_exe:
            console.print("[green]Using aria2c high-speed BitTorrent engine...[/green]")
            cmd = [
                aria2_exe,
                dl_url,
                f"--dir={downloads_dir}",
                "--seed-time=0",
                "--max-connection-per-server=16",
                "--split=16",
            ]
            subprocess.run(cmd)
            return
        else:
            # Open magnet in default torrent client
            os.startfile(dl_url)
            return

    # Web stream download via universal downloader or yt-dlp
    uni_dl = os.path.join(REPO_ROOT, "tools", "universal_downloader.py")
    if os.path.isfile(uni_dl):
        cmd = [sys.executable, uni_dl, dl_url]
        subprocess.run(cmd, cwd=downloads_dir)
    else:
        cmd = ["yt-dlp", dl_url, "-P", downloads_dir]
        subprocess.run(cmd)


def main():
    parser = argparse.ArgumentParser(description="Multi-Site Anime/Hentai Search & Streaming TUI")
    parser.add_argument("query", nargs="*", help="Title to search")
    parser.add_argument("--fzf-preview", nargs=2, metavar=("JSON_PATH", "INDEX"), help=argparse.SUPPRESS)
    parser.add_argument("--no-fzf", action="store_true", help="Force pure-Rich table selector instead of FZF")

    args = parser.parse_args()

    # Handle internal FZF preview calls
    if args.fzf_preview:
        json_path, idx_str = args.fzf_preview
        try:
            render_preview_cli(json_path, int(idx_str))
        except Exception:
            pass
        return

    # Get search query
    query = " ".join(args.query).strip() if args.query else ""
    if not query:
        console.print(
            Panel(
                "[bold cyan]🔍 Multi-Site Media Search & Quality Comparator[/bold cyan]\n"
                "[dim]Searches HentaiMama, Sukebei Nyaa, Hanime, HentaiWorld & HentaiHaven[/dim]",
                border_style="cyan"
            )
        )
        try:
            query = console.input("[bold yellow]Enter anime/title to search: [/bold yellow]").strip()
        except (KeyboardInterrupt, EOFError):
            return

    if not query:
        console.print("[red]No search query provided.[/red]")
        return

    console.print(f"\n[bold green]Searching across all providers for:[/bold green] [bold white]'{query}'[/bold white]...")
    with console.status("[cyan]Querying HentaiMama, Nyaa, Hanime, HentaiWorld, HentaiHaven...[/cyan]", spinner="dots"):
        results = multi_search(query)

    if not results:
        console.print(f"[bold red]No results found across any provider for '{query}'.[/bold red]")
        return

    console.print(f"[bold green]Found and ranked {len(results)} sources![/bold green]\n")

    # Launch FZF selector or fallback
    if not args.no_fzf and shutil.which("fzf"):
        selected, action = run_fzf_selector(results)
    else:
        selected, action = run_rich_fallback(results)

    if not selected or action == "exit":
        console.print("[yellow]Cancelled.[/yellow]")
        return

    if action == "play":
        play_in_mpv(selected)
    elif action == "download":
        download_item(selected)
    elif action == "copy":
        copy_url = selected.download_url or selected.url
        if copy_to_clipboard(copy_url):
            console.print(f"\n[bold green]✔ Copied to clipboard:[/bold green] [white]{copy_url}[/white]")
        else:
            console.print(f"\n[yellow]Stream URL:[/yellow] {copy_url}")


if __name__ == "__main__":
    main()
