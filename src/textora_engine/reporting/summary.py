"""
Dataset statistics and summary calculation for Textora Engine.
"""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

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
    total_visual_frames: int = 0
    elapsed_seconds: float = 0.0
    language_breakdown: Dict[str, int] = field(default_factory=dict)
    source_breakdown: Dict[str, int] = field(default_factory=dict)
    quality_breakdown: Dict[str, int] = field(default_factory=dict)
    word_counts: List[int] = field(default_factory=list)

    def record_result(self, result: ProcessResult) -> None:
        src_type = result.source.source_type.value
        self.source_breakdown[src_type] = self.source_breakdown.get(src_type, 0) + 1

        if result.status == ProcessStatus.SUCCESS:
            self.processed += 1
            self.total_words += result.word_count
            self.total_characters += result.character_count
            self.word_counts.append(result.word_count)
            if result.visual_frame_count:
                self.total_visual_frames += result.visual_frame_count
            if result.language_decision:
                lang = result.language_decision.detected_language
                self.language_breakdown[lang] = self.language_breakdown.get(lang, 0) + 1
            if result.quality:
                q_stat = result.quality.status.value
                self.quality_breakdown[q_stat] = self.quality_breakdown.get(q_stat, 0) + 1
        elif result.status == ProcessStatus.SKIPPED:
            self.skipped_duplicates += 1
        elif result.status == ProcessStatus.FAILED:
            if result.error_category and "LANGUAGE" in result.error_category.value:
                self.language_mismatches += 1
            elif result.error_category and "QUALITY" in result.error_category.value:
                self.quality_failures += 1
            else:
                self.failed += 1

    def compute_word_stats(self) -> Dict[str, Any]:
        if not self.word_counts:
            return {
                "min": 0,
                "max": 0,
                "mean": 0.0,
                "p50": 0.0,
                "p90": 0.0,
            }
        sorted_counts = sorted(self.word_counts)
        n = len(sorted_counts)
        mean_val = sum(sorted_counts) / n

        def percentile(p: float) -> float:
            k = (n - 1) * p
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return float(sorted_counts[int(k)])
            d0 = sorted_counts[int(f)] * (c - k)
            d1 = sorted_counts[int(c)] * (k - f)
            return round(d0 + d1, 1)

        return {
            "min": sorted_counts[0],
            "max": sorted_counts[-1],
            "mean": round(mean_val, 1),
            "p50": percentile(0.50),
            "p90": percentile(0.90),
        }

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
            "total_visual_frames": self.total_visual_frames,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "language_breakdown": self.language_breakdown,
            "source_breakdown": self.source_breakdown,
            "quality_breakdown": self.quality_breakdown,
            "word_stats": self.compute_word_stats(),
        }

    def save_stats_json(self, output_dir: Path) -> Path:
        stats_path = output_dir / "stats.json"
        content = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        atomic_write_text(stats_path, content)
        return stats_path
