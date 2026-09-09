"""
Dataset statistics and summary calculation for Textora Engine.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from textora_engine.models import ProcessResult, ProcessStatus
from textora_engine.storage.writer import atomic_write_text


@dataclass
class RunSummary:
    total_discovered: int = 0
    processed: int = 0
    skipped_duplicates: int = 0
    language_mismatches: int = 0
    quality_failures: int = 0
    failed: int = 0
    total_words: int = 0
    total_characters: int = 0
    elapsed_seconds: float = 0.0
    language_breakdown: Dict[str, int] = field(default_factory=dict)
    source_breakdown: Dict[str, int] = field(default_factory=dict)

    def record_result(self, result: ProcessResult) -> None:
        src_type = result.source.source_type.value
        self.source_breakdown[src_type] = self.source_breakdown.get(src_type, 0) + 1

        if result.status == ProcessStatus.SUCCESS:
            self.processed += 1
            self.total_words += result.word_count
            self.total_characters += result.character_count
            if result.language_decision:
                lang = result.language_decision.detected_language
                self.language_breakdown[lang] = self.language_breakdown.get(lang, 0) + 1
        elif result.status == ProcessStatus.SKIPPED:
            self.skipped_duplicates += 1
        elif result.status == ProcessStatus.FAILED:
            if result.error_category and "LANGUAGE" in result.error_category.value:
                self.language_mismatches += 1
            elif result.error_category and "QUALITY" in result.error_category.value:
                self.quality_failures += 1
            else:
                self.failed += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_discovered": self.total_discovered,
            "processed": self.processed,
            "skipped_duplicates": self.skipped_duplicates,
            "language_mismatches": self.language_mismatches,
            "quality_failures": self.quality_failures,
            "failed": self.failed,
            "total_words": self.total_words,
            "total_characters": self.total_characters,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "language_breakdown": self.language_breakdown,
            "source_breakdown": self.source_breakdown,
        }

    def save_stats_json(self, output_dir: Path) -> Path:
        stats_path = output_dir / "stats.json"
        content = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        atomic_write_text(stats_path, content)
        return stats_path
