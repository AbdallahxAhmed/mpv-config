"""
ui.py — Interactive TUI powered by FZF and Rich.
Provides fuzzy filtering, live detail preview, and 1-key streaming/downloading.
"""

import sys
import os
import shutil
import subprocess
import tempfile
import json
from typing import List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from .models import SearchResult

console = Console()


def find_chafa() -> Optional[str]:
    """Find installed Chafa graphics engine."""
    which = shutil.which("chafa")
    if which:
        return which
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\hpjansson.Chafa_Microsoft.Winget.Source_8wekyb3d8bbwe\chafa-1.18.3-1-x86_64-win\chafa.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\chafa.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    root = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    if os.path.isdir(root):
        for r, _, files in os.walk(root):
            if "chafa.exe" in [f.lower() for f in files]:
                return os.path.join(r, "chafa.exe")
    return None


def _render_ascii_art_thumbnail(image_url: Optional[str], width: int = 66, height: int = 22) -> str:
    """Download and decode thumbnail image to smooth high-density sub-pixel terminal graphics via Chafa or ffmpeg."""
    if not image_url:
        return ""

    import hashlib
    import urllib.request
    url_hash = hashlib.md5(f"{image_url}_{width}_{height}".encode("utf-8")).hexdigest()
    cache_dir = os.path.join(tempfile.gettempdir(), "mpv-hsearch-thumbs")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{url_hash}_chafa_v3.ansi")

    if os.path.isfile(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass

    # Download image file
    img_temp = os.path.join(cache_dir, f"{url_hash}_raw.webp")
    if not os.path.isfile(img_temp):
        try:
            req = urllib.request.Request(
                image_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=4) as r:
                data = r.read()
            with open(img_temp, "wb") as f:
                f.write(data)
        except Exception:
            return ""

    # 1. Use Chafa if available (MovieBox-TUI grade rendering with sextants & quadrants)
    chafa_exe = find_chafa()
    if chafa_exe and os.path.isfile(img_temp):
        try:
            cmd = [
                chafa_exe,
                f"--size={width}x{height}",
                "--symbols=vhalf+quad+sextant+braille",
                "--color-space=rgb",
                img_temp
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=3)
            if proc.returncode == 0 and proc.stdout.strip():
                ansi_block = proc.stdout
                with open(cache_file, "w", encoding="utf-8") as f:
                    f.write(ansi_block)
                return ansi_block
        except Exception:
            pass

    # 2. Fallback to ffmpeg lanczos + unsharp half-blocks
    ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        candidates = [
            r"C:\Program Files\mpv\ffmpeg\bin\ffmpeg.EXE",
            r"C:\Program Files\mpv\ffmpeg.exe",
        ]
        for c in candidates:
            if os.path.isfile(c):
                ffmpeg_exe = c
                break

    if not ffmpeg_exe or not os.path.isfile(img_temp):
        return ""

    try:
        cmd = [
            ffmpeg_exe,
            "-i", img_temp,
            "-vf", f"scale={width}:{height}:flags=lanczos,unsharp=3:3:1.5",
            "-v", "error",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-"
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=3)
        data = proc.stdout
        if len(data) != width * height * 3:
            return ""

        lines = []
        for y in range(0, height, 2):
            line = ""
            for x in range(width):
                idx_top = (y * width + x) * 3
                idx_bot = ((y + 1) * width + x) * 3 if (y + 1) < height else idx_top
                r1, g1, b1 = data[idx_top], data[idx_top + 1], data[idx_top + 2]
                r2, g2, b2 = data[idx_bot], data[idx_bot + 1], data[idx_bot + 2]
                line += f"\033[38;2;{r1};{g1};{b1};48;2;{r2};{g2};{b2}m▀"
            line += "\033[0m"
            lines.append(line)

        ansi_block = "\n".join(lines) + "\n"
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(ansi_block)
        return ansi_block
    except Exception:
        return ""


def format_preview_text(result: SearchResult) -> str:
    """Generate colorized rich terminal preview for a search item."""
    from io import StringIO
    sio = StringIO()
    p_console = Console(file=sio, color_system="truecolor", width=65, force_terminal=True)

    best_indicator = "🏆 TOP PICK (RECOMMENDED)" if result.is_best else "SEARCH RESULT"
    panel_title = f"[bold cyan]{best_indicator}[/bold cyan]"

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold yellow", justify="right")
    grid.add_column(style="white")

    grid.add_row("Title:", f"[bold white]{result.title}[/bold white]")
    grid.add_row("Provider:", f"[bold magenta]{result.provider}[/bold magenta]")
    grid.add_row("Quality:", f"[bold green]{result.resolution}[/bold green] ({result.quality_type})")
    grid.add_row("Codec:", result.codec)
    grid.add_row("Censorship:", f"[bold red if 'Censored' in result.censorship else green]{result.censorship}[/]")
    grid.add_row("Audio:", f"[bold cyan]{result.audio}[/bold cyan]")
    grid.add_row("Subtitles:", f"[bold blue]{result.subtitles}[/bold blue]")
    grid.add_row("Delivery:", f"[bold yellow]{result.delivery}[/bold yellow]")

    if result.size:
        grid.add_row("File Size:", result.size)
    if result.seeders is not None:
        grid.add_row("Seeders:", f"[bold green]{result.seeders}[/bold green]")
    if result.thumbnail:
        grid.add_row("Thumbnail:", f"[dim cyan]{result.thumbnail}[/dim cyan]")

    grid.add_row("Score:", f"[bold cyan]{result.score:.1f}[/bold cyan] / 100")

    # Render ANSI graphic thumbnail if available
    ansi_thumb = _render_ascii_art_thumbnail(result.thumbnail) if result.thumbnail else ""

    # Badges row
    badge_str = " ".join([f"[reverse]{b}[/reverse]" for b in result.badges])

    footer = Text.from_markup(
        "\n[bold green]⌨ Keybindings:[/bold green]\n"
        " • [bold yellow]Enter[/bold yellow]   : 🎬 Stream instantly in MPV\n"
        " • [bold cyan]Ctrl+P[/bold cyan]  : 👁 Floating Live Preview (MPV Window)\n"
        " • [bold cyan]Ctrl+D[/bold cyan]  : ⚡ Turbo Download (aria2c / yt-dlp)\n"
        " • [bold magenta]Ctrl+Y[/bold magenta]  : 📋 Copy Stream / Magnet URL\n"
        " • [bold red]Esc / q[/bold red] : Exit"
    )

    if ansi_thumb:
        sio.write(ansi_thumb + "\n")

    p_console.print(Panel(grid, title=panel_title, border_style="cyan"))
    p_console.print(f"[bold]Badges:[/bold] {badge_str}")
    p_console.print(footer)

    return sio.getvalue()


def render_preview_cli(results_json_path: str, index: int):
    """CLI helper invoked by FZF preview window."""
    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        with open(results_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if 0 <= index < len(data):
            res_dict = data[index]
            r = SearchResult(**res_dict)
            sys.stdout.write(format_preview_text(r))
    except Exception as e:
        sys.stdout.write(f"Preview unavailable: {e}")


def run_fzf_selector(results: List[SearchResult]) -> tuple[Optional[SearchResult], str]:
    """Run interactive FZF selector with live preview and action hotkeys."""
    fzf_exe = shutil.which("fzf")
    if not fzf_exe:
        return run_rich_fallback(results)

    # Dump results to temp file for preview daemon
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".json") as tf:
        json_path = tf.name
        json.dump([r.__dict__ for r in results], tf, ensure_ascii=False)

    # Format list items for FZF
    lines = []
    for i, r in enumerate(results):
        top_mark = "⭐ TOP" if r.is_best else f"#{i+1:02d}"
        badge_short = f"[{r.resolution}] [{r.provider}]"
        cens_short = "[Uncensored]" if "Uncensored" in r.censorship or "Decensored" in r.censorship else ""
        lines.append(f"{i:03d} | {top_mark:<6} | {badge_short:<22} {cens_short:<12} | {r.title}")

    fzf_input = "\n".join(lines).encode("utf-8")

    # Command for FZF preview: calls current python script with --fzf-preview
    script_path = os.path.abspath(sys.argv[0])
    preview_cmd = f'"{sys.executable}" "{script_path}" --fzf-preview "{json_path}" {{1}}'

    cmd = [
        fzf_exe,
        "--ansi",
        "--prompt=🔎 Anime/Hentai Search > ",
        "--header=Enter: Play in MPV | Ctrl-D: Download | Ctrl-P: Floating Preview | Ctrl-Y: Copy Link | Esc: Exit",
        "--header-first",
        "--delimiter=\\|",
        "--preview", preview_cmd,
        "--preview-window=right:55%:wrap",
        "--expect=ctrl-d,ctrl-y,ctrl-p",
    ]

    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, _ = proc.communicate(input=fzf_input)
        if proc.returncode != 0 and proc.returncode != 1:
            return None, "exit"

        output_lines = out.decode("utf-8", errors="ignore").splitlines()
        if not output_lines:
            return None, "exit"

        key = ""
        selected_line = ""
        if len(output_lines) == 1:
            selected_line = output_lines[0]
            action = "play"
        elif len(output_lines) >= 2:
            key = output_lines[0].strip().lower()
            selected_line = output_lines[1]
            if key == "ctrl-d":
                action = "download"
            elif key == "ctrl-y":
                action = "copy"
            elif key == "ctrl-p":
                action = "preview"
            else:
                action = "play"
        else:
            return None, "exit"

        idx_str = selected_line.split("|")[0].strip()
        if idx_str.isdigit():
            idx = int(idx_str)
            if 0 <= idx < len(results):
                return results[idx], action

    finally:
        try:
            os.remove(json_path)
        except Exception:
            pass

    return None, "exit"


def run_rich_fallback(results: List[SearchResult]) -> tuple[Optional[SearchResult], str]:
    """Pure-Rich interactive terminal table with manual selection."""
    table = Table(title="Search & Quality Comparison Results", border_style="cyan")
    table.add_column("#", justify="right", style="cyan", no_wrap=True)
    table.add_column("Badge", style="bold yellow")
    table.add_column("Title", style="white")
    table.add_column("Provider", style="magenta")
    table.add_column("Quality", style="green")
    table.add_column("Audio / Subs", style="blue")
    table.add_column("Delivery", style="yellow")

    for i, r in enumerate(results, 1):
        top_mark = "⭐ TOP PICK" if r.is_best else f"#{i}"
        table.add_row(
            str(i),
            top_mark,
            r.title[:45] + ("..." if len(r.title) > 45 else ""),
            r.provider,
            f"{r.resolution} ({r.quality_type})",
            f"{r.audio} • {r.subtitles}",
            r.delivery
        )

    console.print(table)
    console.print("[bold yellow]Actions:[/bold yellow] [cyan]<num>[/cyan] play | [cyan]d <num>[/cyan] download | [cyan]p <num>[/cyan] preview | [cyan]c <num>[/cyan] copy link | [red]q[/red] exit.")

    while True:
        try:
            choice = input("\nSelect Option > ").strip()
            if not choice or choice.lower() in ("q", "exit"):
                return None, "exit"

            action = "play"
            if choice.lower().startswith("d "):
                action = "download"
                choice = choice[2:].strip()
            elif choice.lower().startswith("c "):
                action = "copy"
                choice = choice[2:].strip()
            elif choice.lower().startswith("p "):
                action = "preview"
                choice = choice[2:].strip()

            if choice.isdigit():
                num = int(choice)
                if 1 <= num <= len(results):
                    return results[num - 1], action
            console.print("[red]Invalid selection, try again.[/red]")
        except (KeyboardInterrupt, EOFError):
            return None, "exit"
