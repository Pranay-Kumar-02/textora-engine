"""
Offline dataset scanner and health validation for Textora Engine.
Audits output directory against manifest.json, checking file existence, hash integrity,
and detecting orphaned or corrupted files.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from rich.table import Table

from textora_engine.dedup.fingerprint import compute_sha256
from textora_engine.reporting.console import console


@dataclass
class ValidationReport:
    total_manifest_records: int = 0
    valid_files_on_disk: int = 0
    missing_files: List[str] = field(default_factory=list)
    empty_or_corrupt_files: List[str] = field(default_factory=list)
    hash_mismatches: List[str] = field(default_factory=list)
    unindexed_files: List[str] = field(default_factory=list)
    total_words: int = 0
    total_characters: int = 0

    @property
    def is_healthy(self) -> bool:
        return (
            len(self.missing_files) == 0
            and len(self.empty_or_corrupt_files) == 0
            and len(self.hash_mismatches) == 0
        )


def validate_dataset(output_dir: Path) -> ValidationReport:
    """
    Audit dataset files on disk against manifest.json.
    Never modifies or deletes files.
    """
    report = ValidationReport()
    manifest_path = output_dir / "manifest.json"
    transcripts_dir = output_dir / "transcripts"

    manifest_records: Dict[str, Dict[str, Any]] = {}
    known_disk_paths = set()

    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    report.total_manifest_records += 1
                    out_path_str = item.get("output_path")
                    if out_path_str:
                        manifest_records[out_path_str] = item
        except Exception as e:
            console.print(f"[bold red]Error reading manifest.json:[/bold red] {e}")

    # Check each manifest record against disk
    for path_str, rec in manifest_records.items():
        file_path = Path(path_str)
        # Handle relative path resolution against output_dir if needed
        if not file_path.is_absolute():
            file_path = output_dir / file_path

        if not file_path.exists():
            report.missing_files.append(f"Missing: {path_str} (Source: {rec.get('source_id')})")
            continue

        known_disk_paths.add(file_path.resolve())

        try:
            size = file_path.stat().st_size
            if size == 0:
                report.empty_or_corrupt_files.append(f"Empty: {path_str}")
                continue

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            report.valid_files_on_disk += 1
            words = content.split()
            report.total_words += len(words)
            report.total_characters += len(content)

            # Check hash integrity
            expected_hash = rec.get("transcript_hash")
            if expected_hash:
                actual_hash = compute_sha256(content)
                if actual_hash != expected_hash:
                    report.hash_mismatches.append(f"Modified: {path_str}")
        except Exception as e:
            report.empty_or_corrupt_files.append(f"Unreadable: {path_str} ({e})")

    # Check for unindexed files inside transcripts/
    if transcripts_dir.exists():
        for f in transcripts_dir.rglob("*.txt"):
            if f.resolve() not in known_disk_paths:
                report.unindexed_files.append(str(f.relative_to(output_dir)))

    return report


def print_validation_report(report: ValidationReport, output_dir: Path) -> None:
    """Print clean validation audit table."""
    table = Table(title=f"Dataset Integrity Audit: {output_dir}", border_style="cyan")
    table.add_column("Audit Check", style="bold white")
    table.add_column("Result", justify="right")

    status_color = "green" if report.is_healthy else "red"
    health_str = f"[{status_color}]{'HEALTHY' if report.is_healthy else 'ISSUES FOUND'}[/{status_color}]"

    table.add_row("Overall Health", health_str)
    table.add_row("Manifest Records", str(report.total_manifest_records))
    table.add_row("Verified Files on Disk", f"[green]{report.valid_files_on_disk}[/green]")
    table.add_row("Missing Files", f"[red]{len(report.missing_files)}[/red]" if report.missing_files else "0")
    table.add_row("Corrupt / Empty Files", f"[red]{len(report.empty_or_corrupt_files)}[/red]" if report.empty_or_corrupt_files else "0")
    table.add_row("Hash Mismatches", f"[yellow]{len(report.hash_mismatches)}[/yellow]" if report.hash_mismatches else "0")
    table.add_row("Unindexed Files", f"[dim]{len(report.unindexed_files)}[/dim]")
    table.add_row("Total Verified Words", f"{report.total_words:,}")
    table.add_row("Total Verified Characters", f"{report.total_characters:,}")

    console.print("\n")
    console.print(table)

    if report.missing_files:
        console.print("\n[bold red]Missing Files Detail:[/bold red]")
        for m in report.missing_files[:10]:
            console.print(f"  - {m}")
        if len(report.missing_files) > 10:
            console.print(f"  ... and {len(report.missing_files) - 10} more.")

    if report.hash_mismatches:
        console.print("\n[bold yellow]Modified / Hash Mismatch Detail:[/bold yellow]")
        for h in report.hash_mismatches[:10]:
            console.print(f"  - {h}")
