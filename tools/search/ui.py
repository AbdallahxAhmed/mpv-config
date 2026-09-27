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

    grid.add_row("Score:", f"[bold cyan]{result.score:.1f}[/bold cyan] / 100")

    # Badges row
    badge_str = " ".join([f"[reverse]{b}[/reverse]" for b in result.badges])

    footer = Text.from_markup(
        "\n[bold green]⌨ Keybindings:[/bold green]\n"
        " • [bold yellow]Enter[/bold yellow]   : 🎬 Stream instantly in MPV\n"
        " • [bold cyan]Ctrl+D[/bold cyan]  : ⚡ Turbo Download (aria2c / yt-dlp)\n"
        " • [bold magenta]Ctrl+Y[/bold magenta]  : 📋 Copy Stream / Magnet URL\n"
        " • [bold red]Esc / q[/bold red] : Exit"
    )

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
        "--header=Enter: Play in MPV | Ctrl-D: Download | Ctrl-Y: Copy Link | Esc: Exit",
        "--header-first",
        "--delimiter=\\|",
        "--preview", preview_cmd,
        "--preview-window=right:55%:wrap",
        "--expect=ctrl-d,ctrl-y",
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
    console.print("[bold yellow]Actions:[/bold yellow] Enter number (e.g. [cyan]1[/cyan]) to play, [cyan]d 1[/cyan] to download, [cyan]c 1[/cyan] to copy link, or [red]q[/red] to exit.")

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

            if choice.isdigit():
                num = int(choice)
                if 1 <= num <= len(results):
                    return results[num - 1], action
            console.print("[red]Invalid selection, try again.[/red]")
        except (KeyboardInterrupt, EOFError):
            return None, "exit"
