"""
Command line interface for Textora Engine.
Supports intuitive, single-command usage as well as specialized subcommands:
extract, preview, stats, validate, health, report, retry, doctor.
"""

from pathlib import Path
from typing import List, Optional
import typer
from rich.table import Table

from textora_engine.config import TextoraConfig
from textora_engine.discovery.detector import discover_from_query, discover_inputs
from textora_engine.models import TranscriptSourcePreference
from textora_engine.pipeline import TextoraPipeline
from textora_engine.reporting.console import console
from textora_engine.reporting.dashboard import generate_html_report
from textora_engine.validation.dataset_scanner import (
    print_health_scorecard,
    print_validation_report,
    validate_dataset,
)

app = typer.Typer(
    name="textora_engine",
    help="Textora Engine: Universal Video-to-Text & Multimodal Dataset Platform.",
    no_args_is_help=True,
)


def _build_config(
    output: Path = Path("./output"),
    language: str = "auto",
    transcript_source: str = "auto",
    stt_backend: str = "faster-whisper",
    stt_model: str = "base",
    group_by: str = "none",
    min_words: int = 20,
    min_characters: int = 100,
    workers: int = 1,
    dry_run: bool = False,
    force: bool = False,
    resume: bool = True,
    retry_failed: bool = False,
    export_srt: bool = False,
    export_vtt: bool = False,
    export_json: bool = False,
    export_jsonl: Optional[Path] = None,
    export_csv: bool = True,
    multimodal: bool = False,
    multimodal_provider: str = "null",
    frame_interval_seconds: float = 10.0,
    export_multimodal_md: bool = False,
    export_multimodal_json: bool = False,
    verbose: bool = False,
    quiet: bool = False,
    config_file: Optional[Path] = None,
    profile: Optional[str] = None,
) -> TextoraConfig:
    """Construct configuration with profile presets and optional TOML file loading."""
    if config_file and config_file.exists():
        cfg = TextoraConfig.load_from_toml(config_file)
    elif profile:
        cfg = TextoraConfig.from_profile(profile)
    else:
        cfg = TextoraConfig()

    cfg.output_dir = output
    if language != "auto" or cfg.language == "auto":
        cfg.language = language
    if transcript_source != "auto" or cfg.transcript_source == TranscriptSourcePreference.AUTO:
        cfg.transcript_source = TranscriptSourcePreference(transcript_source)
    if stt_backend:
        cfg.stt_backend = stt_backend
    if stt_model:
        cfg.stt_model = stt_model
    if group_by != "none":
        cfg.group_by = group_by
    if min_words != 20:
        cfg.min_words = min_words
    if min_characters != 100:
        cfg.min_characters = min_characters
    if workers != 1:
        cfg.workers = workers

    cfg.dry_run = dry_run
    cfg.force = force
    cfg.resume = resume
    cfg.retry_failed = retry_failed
    cfg.export_srt = export_srt
    cfg.export_vtt = export_vtt
    cfg.export_json = export_json
    cfg.export_jsonl = export_jsonl
    cfg.export_csv = export_csv
    cfg.verbose = verbose
    cfg.quiet = quiet

    # Multimodal settings
    if multimodal:
        cfg.multimodal = True
        cfg.multimodal_provider = multimodal_provider if multimodal_provider != "null" else "local"
    cfg.frame_interval_seconds = frame_interval_seconds
    cfg.export_multimodal_md = export_multimodal_md
    cfg.export_multimodal_json = export_multimodal_json

    return cfg


@app.command(name="extract", help="Extract transcripts from YouTube URLs, local videos, or search queries.")
def extract(
    inputs: List[str] = typer.Argument(None, help="Video URLs, local file paths, or directories to process."),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Input file containing URLs or paths, one per line."),
    playlist: Optional[str] = typer.Option(None, "--playlist", "-p", help="YouTube playlist URL to process."),
    query: Optional[str] = typer.Option(None, "--query", "-s", help="Search query to discover relevant YouTube videos."),
    config_file: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to TOML configuration file."),
    profile: Optional[str] = typer.Option(None, "--profile", help="Configuration profile: 'fast', 'balanced', 'high-quality'."),
    output: Path = typer.Option(Path("./output"), "--output", "-o", help="Target dataset output directory."),
    language: str = typer.Option("auto", "--language", "-l", help="Language filter ('auto' for any, or 'en', 'es', etc.)."),
    transcript_source: str = typer.Option("auto", "--transcript-source", help="Transcript source: 'auto', 'captions', or 'stt'."),
    stt_backend: str = typer.Option("faster-whisper", "--stt-backend", help="Speech-to-text engine ('faster-whisper')."),
    stt_model: str = typer.Option("base", "--stt-model", help="STT model size: 'tiny', 'base', 'small', 'medium'."),
    group_by: str = typer.Option("none", "--group-by", help="Folder grouping: 'none', 'source', 'language'."),
    min_words: int = typer.Option(20, "--min-words", help="Minimum required words."),
    min_characters: int = typer.Option(100, "--min-characters", help="Minimum required characters."),
    workers: int = typer.Option(1, "--workers", "-w", help="Worker count for processing."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate pipeline without writing files."),
    force: bool = typer.Option(False, "--force", help="Force reprocessing even if already in state."),
    resume: bool = typer.Option(True, "--resume/--no-resume", help="Skip already processed videos."),
    retry_failed: bool = typer.Option(False, "--retry-failed", help="Retry previously failed items."),
    export_srt: bool = typer.Option(False, "--export-srt", help="Also export .srt subtitle files."),
    export_vtt: bool = typer.Option(False, "--export-vtt", help="Also export .vtt subtitle files."),
    export_json: bool = typer.Option(False, "--export-json", help="Also export .json metadata+segments."),
    export_jsonl: Optional[Path] = typer.Option(None, "--export-jsonl", help="Stream records to a .jsonl dataset file."),
    export_csv: bool = typer.Option(True, "--export-csv/--no-csv", help="Generate manifest.csv."),
    multimodal: bool = typer.Option(False, "--multimodal", help="Enable multimodal video frame extraction."),
    multimodal_provider: str = typer.Option("local", "--multimodal-provider", help="Video understanding provider ('local', 'null')."),
    frame_interval: float = typer.Option(10.0, "--frame-interval", help="Frame extraction interval in seconds."),
    export_multimodal_md: bool = typer.Option(False, "--export-multimodal-md", help="Export synchronized Markdown (.multimodal.md)."),
    export_multimodal_json: bool = typer.Option(False, "--export-multimodal-json", help="Export structured JSON (.multimodal.json)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose debug logging."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error console output."),
):
    # Collect all inputs
    raw_inputs: List[str] = list(inputs or [])
    if file:
        raw_inputs.append(str(file))
    if playlist:
        raw_inputs.append(playlist)

    discovered = []
    if raw_inputs:
        console.print("[bold cyan]Textora Engine[/bold cyan] discovering inputs...")
        discovered.extend(discover_inputs(raw_inputs))

    if query:
        console.print(f"[bold cyan]Textora Engine[/bold cyan] searching for query: [italic]{query}[/italic]")
        query_items = discover_from_query(query, limit=10)
        discovered.extend(query_items)

    if not discovered:
        console.print("[bold yellow]No video sources discovered.[/bold yellow] Pass a URL, local path, query, or use --file / --playlist.")
        raise typer.Exit(code=1 if not (raw_inputs or query) else 0)

    config = _build_config(
        output=output,
        language=language,
        transcript_source=transcript_source,
        stt_backend=stt_backend,
        stt_model=stt_model,
        group_by=group_by,
        min_words=min_words,
        min_characters=min_characters,
        workers=workers,
        dry_run=dry_run,
        force=force,
        resume=resume,
        retry_failed=retry_failed,
        export_srt=export_srt,
        export_vtt=export_vtt,
        export_json=export_json,
        export_jsonl=export_jsonl,
        export_csv=export_csv,
        multimodal=multimodal,
        multimodal_provider=multimodal_provider,
        frame_interval_seconds=frame_interval,
        export_multimodal_md=export_multimodal_md,
        export_multimodal_json=export_multimodal_json,
        verbose=verbose,
        quiet=quiet,
        config_file=config_file,
        profile=profile,
    )

    console.print(f"Discovered [bold green]{len(discovered)}[/bold green] video source items.")
    pipeline = TextoraPipeline(config=config)
    pipeline.run(discovered)


@app.command(name="preview", help="Preview discovered sources without fetching or transcribing.")
def preview(
    inputs: List[str] = typer.Argument(None, help="Video URLs, local file paths, or directories."),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Input file with links or paths."),
    playlist: Optional[str] = typer.Option(None, "--playlist", "-p", help="YouTube playlist URL."),
    query: Optional[str] = typer.Option(None, "--query", "-s", help="Search query to preview."),
):
    raw_inputs: List[str] = list(inputs or [])
    if file:
        raw_inputs.append(str(file))
    if playlist:
        raw_inputs.append(playlist)

    discovered = []
    if raw_inputs:
        discovered.extend(discover_inputs(raw_inputs))
    if query:
        discovered.extend(discover_from_query(query, limit=10))

    if not discovered:
        console.print("[bold yellow]No inputs provided or discovered.[/bold yellow]")
        raise typer.Exit(code=1)

    table = Table(title=f"Discovered Sources ({len(discovered)} items)", border_style="cyan")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Type", style="cyan")
    table.add_column("ID / Name", style="bold white")
    table.add_column("URI / Path", style="dim")

    for i, item in enumerate(discovered, start=1):
        table.add_row(str(i), item.source_type.value, item.display_name, item.uri[:60])

    console.print(table)


@app.command(name="validate", help="Scan and audit an existing dataset directory on disk against manifest.json.")
def validate_cmd(
    output_dir: Path = typer.Argument(Path("./output"), help="Path to output dataset directory."),
):
    if not output_dir.exists():
        console.print(f"[bold red]Directory does not exist:[/bold red] {output_dir}")
        raise typer.Exit(code=1)

    report = validate_dataset(output_dir)
    print_validation_report(report, output_dir)


@app.command(name="health", help="Run comprehensive dataset health check and print scorecard.")
def health_cmd(
    output_dir: Path = typer.Argument(Path("./output"), help="Path to output dataset directory."),
):
    if not output_dir.exists():
        console.print(f"[bold red]Directory does not exist:[/bold red] {output_dir}")
        raise typer.Exit(code=1)

    report = validate_dataset(output_dir)
    print_health_scorecard(report, output_dir)


@app.command(name="report", help="Generate standalone interactive HTML dataset audit dashboard.")
def report_cmd(
    output_dir: Path = typer.Argument(Path("./output"), help="Path to output dataset directory."),
    output_file: Optional[Path] = typer.Option(None, "--target", "-t", help="Target HTML file path (default: <output_dir>/report.html)."),
):
    if not output_dir.exists():
        console.print(f"[bold red]Directory does not exist:[/bold red] {output_dir}")
        raise typer.Exit(code=1)

    target_path = generate_html_report(output_dir, target_file=output_file)
    console.print(f"[bold green]HTML dashboard generated successfully:[/bold green] {target_path.resolve()}")


@app.command(name="stats", help="Display aggregate statistics for an existing dataset.")
def stats_cmd(
    output_dir: Path = typer.Argument(Path("./output"), help="Path to output dataset directory."),
):
    manifest_file = output_dir / "manifest.json"
    stats_file = output_dir / "stats.json"

    if stats_file.exists():
        import json
        with open(stats_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        table = Table(title=f"Dataset Statistics: {output_dir}", border_style="green")
        table.add_column("Metric", style="bold white")
        table.add_column("Value", justify="right", style="bold green")
        for k, v in data.items():
            if isinstance(v, dict):
                continue
            table.add_row(str(k).replace("_", " ").title(), str(v))
        console.print(table)
    elif manifest_file.exists():
        report = validate_dataset(output_dir)
        print_validation_report(report, output_dir)
    else:
        console.print(f"[bold yellow]No manifest.json or stats.json found in {output_dir}[/bold yellow]")


@app.command(name="retry", help="Retry all previously failed items recorded in .state/failed.json.")
def retry_cmd(
    output: Path = typer.Option(Path("./output"), "--output", "-o", help="Target dataset output directory."),
    language: str = typer.Option("auto", "--language", "-l", help="Language filter."),
):
    state_file = output / ".state" / "failed.json"
    if not state_file.exists():
        console.print("[green]No failed items found in state.[/green]")
        raise typer.Exit(code=0)

    import json
    with open(state_file, "r", encoding="utf-8") as f:
        failed_data = json.load(f)

    if not failed_data:
        console.print("[green]No failed items found in state.[/green]")
        raise typer.Exit(code=0)

    console.print(f"Found [yellow]{len(failed_data)}[/yellow] failed items to retry.")
    sources = discover_inputs(list(failed_data.keys()))
    config = TextoraConfig(output_dir=output, language=language, force=True)
    pipeline = TextoraPipeline(config=config)
    pipeline.run(sources)


@app.command(name="doctor", help="Run system diagnostics, checking dependencies, FFmpeg, and provider readiness.")
def doctor_cmd(
    target_dir: Path = typer.Option(Path("./output"), "--target-dir", "-t", help="Directory to verify write permissions."),
):
    import sys
    from rich.table import Table

    table = Table(title="Textora Engine System Diagnostics", border_style="cyan")
    table.add_column("Component", style="bold white", width=25)
    table.add_column("Status", width=15)
    table.add_column("Details / Recommendations")

    # 1. Python Environment
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 10)
    table.add_row(
        "Python Runtime",
        "[green]OK[/green]" if py_ok else "[red]UPGRADE NEEDED[/red]",
        f"Version {py_ver} ({sys.executable})",
    )

    # 2. Core Dependencies
    core_pkgs = [
        ("typer", "CLI interface framework"),
        ("rich", "Terminal UI & formatting"),
        ("youtube_transcript_api", "YouTube transcript extraction engine"),
        ("langdetect", "Deterministic language detection fallback"),
        ("xxhash", "High-speed 64-bit hashing for deduplication"),
    ]
    for mod_name, desc in core_pkgs:
        try:
            m = __import__(mod_name)
            ver = getattr(m, "__version__", "Installed")
            table.add_row(f"Dependency: {mod_name}", "[green]OK[/green]", f"{desc} (v{ver})")
        except ImportError:
            table.add_row(f"Dependency: {mod_name}", "[bold red]MISSING[/bold red]", f"Run: pip install {mod_name}")

    # 3. Media & FFmpeg
    try:
        from textora_engine.media.ffmpeg_util import find_ffmpeg
        ff_path = find_ffmpeg()
        table.add_row("Media: FFmpeg", "[green]FOUND[/green]", f"Available at: {ff_path}")
    except Exception:
        table.add_row(
            "Media: FFmpeg",
            "[yellow]NOT FOUND[/yellow]",
            "Required for audio extraction and visual frame sampling. Install FFmpeg on PATH or run: pip install imageio-ffmpeg",
        )

    # 4. Speech-to-Text Providers
    try:
        import faster_whisper
        fw_ver = getattr(faster_whisper, "__version__", "Installed")
        table.add_row("STT: faster-whisper", "[green]AVAILABLE[/green]", f"Local Whisper transcription ready (v{fw_ver})")
    except ImportError:
        table.add_row(
            "STT: faster-whisper",
            "[yellow]NOT INSTALLED[/yellow]",
            "Optional for local Speech-to-Text. Run: pip install faster-whisper",
        )

    # 5. Video Understanding Registry
    try:
        from textora_engine.video_understanding import VideoUnderstandingRegistry
        providers = VideoUnderstandingRegistry.list_available()
        table.add_row("Video Understanding", "[green]READY[/green]", f"Registered providers: {', '.join(providers)}")
    except Exception as e:
        table.add_row("Video Understanding", "[yellow]NOT READY[/yellow]", str(e))

    # 6. Filesystem & Write Permissions
    try:
        test_dir = target_dir / ".doctor_test"
        test_dir.mkdir(parents=True, exist_ok=True)
        test_file = test_dir / "write_test.tmp"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        test_dir.rmdir()
        table.add_row("Filesystem Access", "[green]WRITABLE[/green]", f"Read/write access confirmed for: {target_dir.resolve()}")
    except Exception as e:
        table.add_row("Filesystem Access", "[bold red]ERROR[/bold red]", f"Cannot write to {target_dir}: {e}")

    console.print(table)


def main():
    app()


if __name__ == "__main__":
    main()
