"""
Terminal reporting and progress indicators using rich for Textora Engine.
"""

from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def log_item_header(index: int, total: int, title: str, source_type: str) -> None:
    """Print clean start header for an item."""
    console.print(f"\n[bold cyan][{index}/{total}][/bold cyan] [bold white]Processing ({source_type})[/bold white]")
    console.print(f"  [dim]Title:[/dim] [white]{title}[/white]")


def log_success(output_path: str, language: str, word_count: int, transcript_source: str) -> None:
    """Print success notification."""
    console.print(f"  [bold green][SUCCESS][/bold green] [green]{transcript_source}[/green] | [cyan]{language.upper()}[/cyan] | [yellow]{word_count:,} words[/yellow]")
    console.print(f"  [dim]Saved ->[/dim] [blue]{output_path}[/blue]")


def log_skip(reason: str, detail: Optional[str] = None) -> None:
    """Print skip notification."""
    console.print(f"  [bold yellow][SKIP][/bold yellow] [yellow]{reason}[/yellow]" + (f": [dim]{detail}[/dim]" if detail else ""))


def log_failure(reason: str, error_msg: Optional[str] = None) -> None:
    """Print failure notification."""
    console.print(f"  [bold red][FAIL][/bold red] [red]{reason}[/red]" + (f": [dim]{error_msg}[/dim]" if error_msg else ""))


def render_summary_table(
    total_discovered: int,
    processed: int,
    skipped_duplicates: int,
    language_mismatches: int,
    failed: int,
    total_words: int,
    total_characters: int,
    elapsed_seconds: float,
) -> None:
    """Render structured execution summary table."""
    table = Table(title="Textora Engine Batch Summary", border_style="cyan")
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="bold green", justify="right")

    table.add_row("Total Discovered", f"{total_discovered:,}")
    table.add_row("Successfully Processed", f"{processed:,}")
    table.add_row("Skipped (Duplicates/State)", f"{skipped_duplicates:,}")
    table.add_row("Language Mismatches", f"{language_mismatches:,}")
    table.add_row("Failed", f"{failed:,}")
    table.add_row("Total Words Collected", f"{total_words:,}")
    table.add_row("Total Characters", f"{total_characters:,}")
    table.add_row("Duration", f"{elapsed_seconds:.2f} seconds")

    console.print("\n")
    console.print(table)
