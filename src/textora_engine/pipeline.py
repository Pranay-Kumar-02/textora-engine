"""
Core processing pipeline for Textora Engine.
Orchestrates discovery, transcript acquisition (captions or STT), language validation,
safe normalization, quality checking, deduplication, atomic storage, and checkpointing.
"""

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from textora_engine.config import ForgeConfig
from textora_engine.dedup.fingerprint import (
    DedupRegistry,
    compute_normalized_hash,
    compute_sha256,
)
from textora_engine.exceptions import (
    LanguageMismatchError,
    QualityThresholdError,
    TextoraEngineError,
    TranscriptUnavailableError,
)
from textora_engine.language.validator import UniversalLanguageValidator
from textora_engine.models import (
    DedupStatus,
    ErrorCategory,
    ManifestRecord,
    ProcessResult,
    ProcessStatus,
    SourceItem,
)
from textora_engine.normalization.cleaner import normalize_text
from textora_engine.quality.evaluator import QualityEvaluator
from textora_engine.reporting.console import (
    log_failure,
    log_item_header,
    log_skip,
    log_success,
    render_summary_table,
)
from textora_engine.reporting.summary import RunSummary
from textora_engine.state.checkpoint import StateManager
from textora_engine.storage.manifest import ManifestManager
from textora_engine.storage.writer import DatasetWriter
from textora_engine.transcripts.coordinator import TranscriptCoordinator
from textora_engine.video_understanding import VideoUnderstandingRegistry

logger = logging.getLogger("textora_engine.pipeline")


class TextoraPipeline:
    """Universal video-to-text pipeline."""

    """
    Universal video-to-text pipeline.
    """

    def __init__(self, config: ForgeConfig, stt_provider=None):
        self.config = config
        self.output_dir = config.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.coordinator = TranscriptCoordinator(
            preference=config.transcript_source,
            stt_provider=stt_provider,
            target_language=config.language,
        )
        self.lang_validator = UniversalLanguageValidator(
            target_language=config.language,
        )
        self.quality_evaluator = QualityEvaluator(
            min_words=config.min_words,
            min_characters=config.min_characters,
            max_repeated_ngram_ratio=config.max_repeated_ngram_ratio,
        )
        self.dedup_registry = DedupRegistry()
        self.writer = DatasetWriter(
            output_dir=self.output_dir,
            group_by=config.group_by,
            export_srt=config.export_srt,
            export_vtt=config.export_vtt,
            export_json=config.export_json,
            export_multimodal_md=config.export_multimodal_md,
            export_multimodal_json=config.export_multimodal_json,
        )
        self.manifest_manager = ManifestManager(
            output_dir=self.output_dir,
            export_csv=config.export_csv,
            export_jsonl_path=config.export_jsonl,
        )
        self.state_manager = StateManager(output_dir=self.output_dir)

    def run(self, sources: List[SourceItem]) -> RunSummary:
        """
        Execute the pipeline over a collection of video sources.
        """
        summary = RunSummary(total_discovered=len(sources))
        start_time = time.time()

        try:
            for idx, source in enumerate(sources, start=1):
                if not self.config.quiet:
                    log_item_header(
                        index=idx,
                        total=len(sources),
                        title=source.display_name,
                        source_type=source.source_type.value,
                    )

                result = self.process_single_source(source)
                summary.record_result(result)

        except KeyboardInterrupt:
            logger.warning("\nPipeline execution interrupted by user (Ctrl+C). Saving state...")
        finally:
            summary.elapsed_seconds = time.time() - start_time
            # Atomically flush manifests and state
            if not self.config.dry_run:
                self.manifest_manager.save()
                self.state_manager.save()
                summary.save_stats_json(self.output_dir)

            if not self.config.quiet:
                render_summary_table(
                    total_discovered=summary.total_discovered,
                    processed=summary.processed,
                    skipped_duplicates=summary.skipped_duplicates,
                    language_mismatches=summary.language_mismatches,
                    failed=summary.failed,
                    total_words=summary.total_words,
                    total_characters=summary.total_characters,
                    elapsed_seconds=summary.elapsed_seconds,
                )

        return summary

    def process_single_source(self, source: SourceItem) -> ProcessResult:
        """
        Process an individual video source with end-to-end guarantees.
        """
        # 1. Source duplication check (in current batch)
        if self.dedup_registry.is_source_duplicate(source.source_id):
            if not self.config.quiet:
                log_skip("Duplicate source ID in batch", source.source_id)
            return ProcessResult(source=source, status=ProcessStatus.SKIPPED)
        self.dedup_registry.register_source(source.source_id)

        # 2. Checkpoint resume check (already processed in previous run)
        if self.config.resume and not self.config.force:
            if self.state_manager.is_processed(source.source_id, verify_file_exists=True):
                if not self.config.quiet:
                    log_skip("Already processed in previous run", source.source_id)
                return ProcessResult(source=source, status=ProcessStatus.SKIPPED)

        # 3. Dry-run mode
        if self.config.dry_run:
            if not self.config.quiet:
                target_mock = self.writer.resolve_target_filepath(source, self.config.language)
                log_success(str(target_mock), self.config.language, 0, "[DRY-RUN SIMULATED]")
            return ProcessResult(source=source, status=ProcessStatus.SUCCESS)

        # 4. Transcript Acquisition (Captions or Local STT)
        try:
            raw_transcript = self.coordinator.acquire_transcript(source)
        except LanguageMismatchError as e:
            if not self.config.quiet:
                log_skip("Language mismatch", str(e))
            self.state_manager.mark_failed(source.source_id, ErrorCategory.LANGUAGE_MISMATCH, str(e))
            return ProcessResult(
                source=source,
                status=ProcessStatus.FAILED,
                error_category=ErrorCategory.LANGUAGE_MISMATCH,
                error_message=str(e),
            )
        except TranscriptUnavailableError as e:
            if not self.config.quiet:
                log_failure("Transcript unavailable", str(e))
            self.state_manager.mark_failed(source.source_id, ErrorCategory.NO_TRANSCRIPT, str(e))
            return ProcessResult(
                source=source,
                status=ProcessStatus.FAILED,
                error_category=ErrorCategory.NO_TRANSCRIPT,
                error_message=str(e),
            )
        except TextoraEngineError as e:
            if not self.config.quiet:
                log_failure("Acquisition failed", str(e))
            self.state_manager.mark_failed(source.source_id, e.category, str(e))
            return ProcessResult(
                source=source,
                status=ProcessStatus.FAILED,
                error_category=e.category,
                error_message=str(e),
            )
        except Exception as e:
            if not self.config.quiet:
                log_failure("Unexpected acquisition error", str(e))
            self.state_manager.mark_failed(source.source_id, ErrorCategory.UNKNOWN_ERROR, str(e))
            return ProcessResult(
                source=source,
                status=ProcessStatus.FAILED,
                error_category=ErrorCategory.UNKNOWN_ERROR,
                error_message=str(e),
            )

        # 5. Universal Language Validation
        lang_decision = self.lang_validator.validate(raw_transcript)
        if not lang_decision.is_acceptable:
            if not self.config.quiet:
                log_skip("Language rejected", lang_decision.reason)
            self.state_manager.mark_failed(
                source.source_id, ErrorCategory.LANGUAGE_MISMATCH, lang_decision.reason
            )
            return ProcessResult(
                source=source,
                status=ProcessStatus.FAILED,
                language_decision=lang_decision,
                error_category=ErrorCategory.LANGUAGE_MISMATCH,
                error_message=lang_decision.reason,
            )

        # 6. Safe Text Normalization (Faithful to spoken audio)
        clean_text = normalize_text(raw_transcript)

        # 7. Quality Validation
        quality = self.quality_evaluator.evaluate(clean_text, raw_transcript)
        if not quality.is_usable:
            reason = "; ".join(quality.warning_reasons)
            if not self.config.quiet:
                log_failure("Quality threshold failed", reason)
            self.state_manager.mark_failed(source.source_id, ErrorCategory.QUALITY_FAILURE, reason)
            return ProcessResult(
                source=source,
                status=ProcessStatus.FAILED,
                quality=quality,
                error_category=ErrorCategory.QUALITY_FAILURE,
                error_message=reason,
            )

        # 8. Content Fingerprinting & Deduplication
        raw_hash = compute_sha256(raw_transcript.raw_text)
        norm_hash = compute_normalized_hash(clean_text)
        dedup_status = self.dedup_registry.check_content_duplicate(norm_hash, source.source_id)

        notes = None
        if dedup_status == DedupStatus.POSSIBLE_DUPLICATE_CONTENT:
            notes = "Identical transcript content to another processed video"
            logger.info(f"Note: {source.source_id} shares identical content with an earlier video.")

        # 9. Atomic Storage (.txt contains strictly pure transcript)
        try:
            saved_path = self.writer.save_transcript(
                source=source,
                raw_transcript=raw_transcript,
                normalized_text=clean_text,
            )
        except Exception as e:
            if not self.config.quiet:
                log_failure("Storage error", str(e))
            self.state_manager.mark_failed(source.source_id, ErrorCategory.STORAGE_ERROR, str(e))
            return ProcessResult(
                source=source,
                status=ProcessStatus.FAILED,
                error_category=ErrorCategory.STORAGE_ERROR,
                error_message=str(e),
            )

        # 9b. Multimodal Video Understanding (optional, isolated companion output)
        visual_frame_count = 0
        multimodal_transcript = None
        if self.config.multimodal:
            try:
                provider = VideoUnderstandingRegistry.get_provider(
                    self.config.multimodal_provider,
                    frame_interval_seconds=self.config.frame_interval_seconds,
                )
                multimodal_transcript = provider.process(
                    source=source,
                    segments=raw_transcript.segments,
                    output_dir=self.output_dir,
                    frame_interval_seconds=self.config.frame_interval_seconds,
                )
                if multimodal_transcript and multimodal_transcript.visual_frames:
                    visual_frame_count = len(multimodal_transcript.visual_frames)
                    if self.config.export_multimodal_md or self.config.export_multimodal_json:
                        self.writer.save_multimodal(
                            source=source,
                            multimodal_transcript=multimodal_transcript,
                            language_code=lang_decision.detected_language,
                        )
            except Exception as e:
                logger.warning(f"Multimodal video understanding encountered error for {source.source_id}: {e}")

        # 10. Update Manifest & State Checkpoint
        manifest_record = ManifestRecord(
            source_id=source.source_id,
            source_type=source.source_type.value,
            uri=source.uri,
            title=source.display_name,
            output_path=str(saved_path.resolve()),
            transcript_source=raw_transcript.transcript_source.value,
            stt_backend=raw_transcript.stt_backend,
            stt_model=raw_transcript.stt_model,
            language=lang_decision.detected_language,
            quality_status=quality.status.value,
            word_count=quality.word_count,
            character_count=quality.character_count,
            duration_seconds=source.duration_seconds,
            transcript_hash=raw_hash,
            normalized_hash=norm_hash,
            confidence=lang_decision.confidence,
            processed_at=datetime.now(timezone.utc).isoformat(),
            status=ProcessStatus.SUCCESS.value,
            notes=notes,
            author=source.author,
            upload_date=source.upload_date,
            visual_frame_count=visual_frame_count,
            multimodal_enabled=self.config.multimodal,
        )
        self.manifest_manager.add_record(manifest_record, full_text=clean_text)
        self.state_manager.mark_success(
            source_id=source.source_id,
            output_path=saved_path,
            content_hash=raw_hash,
            word_count=quality.word_count,
        )

        if not self.config.quiet:
            log_success(
                output_path=str(saved_path),
                language=lang_decision.detected_language,
                word_count=quality.word_count,
                transcript_source=raw_transcript.transcript_source.value,
            )

        return ProcessResult(
            source=source,
            status=ProcessStatus.SUCCESS,
            output_path=saved_path,
            transcript_source=raw_transcript.transcript_source,
            language_decision=lang_decision,
            quality=quality,
            transcript_hash=raw_hash,
            normalized_hash=norm_hash,
            word_count=quality.word_count,
            character_count=quality.character_count,
            duration_seconds=source.duration_seconds,
            multimodal_transcript=multimodal_transcript,
            visual_frame_count=visual_frame_count,
        )

ForgePipeline = TextoraPipeline
