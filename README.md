# Textora Engine

<p align="center">
  <strong>The Video-to-Text & Multimodal Dataset Engineering Platform</strong><br>
  <em>Turn raw video sources into clean, validated, reproducible, provenance-aware AI datasets.</em>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#the-big-idea">The Big Idea</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#product-capabilities">Capabilities</a> •
  <a href="#cli-reference">CLI Reference</a> •
  <a href="#rest-api">REST API</a> •
  <a href="#python-sdk">Python SDK</a> •
  <a href="#multimodal-video-understanding">Multimodal</a> •
  <a href="#rag--ai-agent-readiness">RAG Readiness</a> •
  <a href="#testing--verification">Verification</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue?style=flat-square&logo=python" alt="Python Versions">
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/Automated%20Tests-97%20Passed-brightgreen?style=flat-square" alt="Automated Tests">
  <img src="https://img.shields.io/badge/E2E%20Scenarios-14%2F14%20Passed-brightgreen?style=flat-square" alt="E2E Scenarios">
  <img src="https://img.shields.io/badge/Architecture-Clean%204--Layer-purple?style=flat-square" alt="Architecture">
  <img src="https://img.shields.io/badge/Storage-Content--Addressed%20SHA--256-orange?style=flat-square" alt="Storage">
</p>

---

## Overview

**Textora Engine** is an open-source video-data engineering platform designed to discover, ingest, transcribe, normalize, validate, enrich, version, trace, and expose video-derived datasets.

Traditional transcription utilities treat speech-to-text as a one-off script: *give a video file, get a plain transcript*. Textora Engine approaches video from a **data systems perspective**:

- **Video is multi-dimensional**: Spoken knowledge is tightly coupled with visual demonstrations (code, diagrams, slides, and UI workflows).
- **Video transcripts are inherently noisy**: Rolling caption flickers, non-lexical audio annotations (`[Music]`, `[Applause]`), language drift, and transliterated Latin script (e.g., Hinglish) degrade downstream AI models.
- **Datasets require engineering rigor**: If data is used to train language models, ground AI agents, or populate RAG vector stores, it demands **cryptographic integrity, deterministic idempotency, immutable lineage, non-destructive repair, and multi-tenant access control**.

Textora Engine bridges this gap by wrapping robust media extraction and local Speech-to-Text (`faster-whisper`) inside a production-grade control plane, durable queue, and developer-first interfaces (**CLI, HTTP REST API, and Python SDK**).

---

## Why Textora Exists: The Video-to-Data Problem

Video is the fastest-growing repository of human technical knowledge. University lectures, conference talks, coding tutorials, product demos, and executive interviews contain rich information that AI systems need.

Yet building high-quality text and multimodal corpora from video poses severe engineering hurdles:

| Failure Mode in Naive Scraping | Engineering Impact | How Textora Engine Solves It |
|:---|:---|:---|
| **Caption Flicker Duplication** | Automated YouTube subtitles stream progressively, repeating preceding phrases across consecutive chunks. | **Deterministic De-flickering**: Eliminates overlapping n-gram word buffers using regex and string rules without generative hallucination. |
| **Audio Tag & Entity Pollution** | HTML entities (`&amp;`, `&#39;`) and non-speech markers (`[Music]`, `(Laughter)`) contaminate pretraining data. | **Normalizer**: Unescapes entities and scrubs sound effect tags while preserving meaningful spoken punctuation. |
| **Metadata Header Contamination** | Tools frequently inject titles, timestamps, or markdown headers (`# Title`, `---`) directly into `.txt` outputs. | **Pure `.txt` Invariant**: Spoken text is isolated 100% cleanly in `.txt`. Metadata is preserved separately in companion formats and manifests. |
| **Redundant STT Compute** | Running Whisper across hundreds of hours of video when human captions already exist wastes days of GPU/CPU time. | **Caption-First Dual Engine**: Automatically checks for manual and automatic captions before falling back to local STT. |
| **Language Drift & Transliteration** | Scraping tools fail to catch when English audio contains non-Latin scripts or transliterated Hinglish. | **Multi-Layer Language Gate**: Evaluates script boundaries and vocabulary ratios, flagging transliterated text while protecting technical jargon. |
| **Silent Job Crashes** | Network interruptions or corrupt media files leave zero-byte files, orphaned staging directories, and duplicate records. | **Durable Worker Leasing**: Atomic staging, `os.replace` promotion, heartbeat leases, and automatic crash recovery. |
| **Lost Provenance** | RAG retrieval chunks become untraceable; developers cannot verify which video segment or timestamp produced an answer. | **Lineage DAGs & Execution Manifests**: Every output links back to source URIs, config hashes, and pipeline versions. |

---

## The Big Idea: A Data Engineering Layer for Video

```
A Standard Transcription Script:
Input Video  ───►  Speech-to-Text  ───►  Disposable Text File

The Textora Engine Platform:
Video Source
    │
    ▼
[ Source Discovery ] ──────────► YouTube Canonicalization, Playlists, Local Files
    │
    ▼
[ Dual Ingestion ] ────────────► Caption-First Routing with Faster-Whisper Fallback
    │
    ▼
[ Normalization ] ─────────────► De-flicker, Entity Unescape, Audio Tag Removal
    │
    ▼
[ Linguistic & Quality Gates ] ─► Script Validation, Vocabulary Ratio, N-gram Loops
    │
    ▼
[ Deduplication ] ─────────────► 64-bit xxHash & SHA-256 Fingerprinting
    │
    ▼
[ Multimodal Extraction ] ─────► Interval-Sampled Frames & Temporal Alignment
    │
    ▼
[ Artifact Promotion ] ────────► Atomic Staged Writes & Cryptographic Hashing
    │
    ▼
[ Lineage & Manifests ] ───────► Immutable DAG Events & Execution Manifests
    │
    ▼
[ Dataset Versioning ] ────────► Snapshot Releases (v1.0.0) & Non-Destructive Repair
    │
    ▼
[ Platform Consumption ] ──────► CLI • REST API • Python SDK • RAG Retrieval Chunks
```

---

## Why Textora? Core Differentiators

### 1. Dataset-First Architecture
Outputs are not treated as disposable scratch files. Every processed video produces a managed dataset artifact registered with size, xxHash64, SHA-256 digests, and strict storage schemas.

### 2. Reliability by Design
- **Durable Job Queue**: Backed by SQLite in WAL mode with worker leasing, heartbeats, and priority scheduling (`CRITICAL`, `HIGH`, `NORMAL`, `BATCH`).
- **Crash Recovery**: Stale leases from terminated workers are automatically reclaimed (`recover_expired_leases`).
- **Resource Governance**: `ResourceLimiter` enforces bounded concurrency slots for FFmpeg and STT, checks free disk space, and prevents OOM panics.

### 3. Bit-for-Bit Reproducibility
- **Canonical Configuration Hashing**: Normalizes configuration into key-sorted JSON (omitting volatile flags like verbosity) to generate deterministic SHA-256 config hashes.
- **Idempotent Deduplication**: Submitting the same video with identical configuration returns the existing job without repeating expensive compute.

### 4. Immutable Data Lineage
- **Lineage DAGs**: `LineageTracker` logs structured execution events across every stage (`DISCOVERY`, `INGESTION`, `NORMALIZATION`, `QUALITY`, `PROMOTION`).
- **Execution Manifests**: Stored in `_manifests/<execution_id>.json`, capturing environment metadata, provider details, and input/output hashes.

### 5. Snapshot Dataset Versioning
- `DatasetVersionManager` snapshots directory states into immutable releases (e.g., `v1.0.0`). Historical dataset versions remain bit-for-bit identical regardless of future additions.

### 6. Honest Multimodal Video Understanding
- Associates spoken segments with visual frames via timestamp containment.
- **Strict Honesty Guarantee**: Local frame extraction only claims what it actually computes (`sampled_frame`). It **never** fabricates semantic labels (`code_screen`, `slide`, `ui_demo`), OCR text, or synthetic confidence scores unless a verified vision provider generates them.

### 7. Security-in-Depth
- **SSRF Protection**: `URLValidator` blocks private IPv4/IPv6 ranges, link-local, loopback, cloud metadata endpoints (169.254.169.254), sensitive non-HTTP ports, and embedded URL credentials with redirect hop inspection.
- **Subprocess Isolation**: `SubprocessRunner` runs all FFmpeg processes with `shell=False`, argument list validation, execution timeouts, and complete process-tree termination.
- **Storage Protection**: Path traversal detection and Windows reserved-name (`CON`, `PRN`, `AUX`) sanitization.
- **Auth & Multi-Tenancy**: High-entropy API keys (`tx_live_...`) stored as salted SHA-256 hashes, constant-time verification (`hmac.compare_digest`), RBAC (`OWNER`, `ADMIN`, `MEMBER`, `VIEWER`), and tenant boundary enforcement.

### 8. Native RAG Readiness
- `TextoraChunker` splits transcripts into temporally bounded `RetrievalChunk` objects retaining chunk IDs, source URIs, dataset version, timestamps, visual frame paths, and SHA-256 provenance hashes.

---

## Product Capabilities Matrix

| Capability Area | What Textora Engine Delivers | Why It Matters for Production |
|:---|:---|:---|
| **Source Discovery** | Canonical YouTube video & playlist parsing, local directory traversal, and batch inventory files. | Eliminates custom URL crawling scripts; handles varied video inputs through a single pipeline. |
| **Caption Extraction** | Sibling subtitle discovery (`.srt`, `.vtt`) for local video; YouTube manual and auto-generated tracks. | Avoids redundant STT computation, saving hours of GPU time and thousands in cloud compute. |
| **Speech-to-Text** | Local `faster-whisper` integration with selectable models (`tiny`, `base`, `small`, `medium`). | High-speed, private, offline transcription when native subtitles are unavailable. |
| **Text Normalization** | Entity unescaping, bracketed audio marker removal, and caption de-flickering. | Generates clean prose suitable for LLM pretraining without corrupting original speech. |
| **Linguistic Validation** | Language filtering, Latin script enforcement, and Hinglish vocabulary-ratio analysis. | Prevents silent corpus contamination from mismatched languages and transliterated scripts. |
| **Quality Evaluation** | Automated classification into `GOOD`, `SHORT`, `SUSPICIOUS` (n-gram looping), and `EMPTY`. | Isolates corrupted or low-information videos before they enter production training sets. |
| **Deduplication** | Content fingerprinting using 64-bit `xxhash` and SHA-256 verification. | Detects duplicate content across varying filenames or re-uploaded video files. |
| **Multimodal Alignment** | Timestamp-bounded frame extraction with companion `.multimodal.md` and `.multimodal.json`. | Equips multimodal AI agents with visual evidence linked directly to spoken words. |
| **Artifact Management** | Staged writes to `_staging/` with atomic promotion and zero-byte file rejection. | Ensures corrupt or partial files are never exposed to consumers or indexed into datasets. |
| **Durable Job Queue** | SQLite WAL queue with heartbeat leases, priority scheduling, and crash reclamation. | Enables reliable background job processing and prevents duplicate concurrent execution. |
| **Multi-Tenancy & RBAC** | Organization $\rightarrow$ Project hierarchy with API key validation and resource authorization. | Prevents cross-tenant data leaks in shared infrastructure and multi-team environments. |
| **Dataset Versioning** | Snapshot release creation (`v1.0.0`) and manifest archiving. | Guarantees machine learning experiment reproducibility and auditability over time. |
| **Non-Destructive Repair** | Recalculates disk checksums, indexes unindexed files, and reconstructs damaged manifests. | Recovers dataset metadata after system crashes without ever overwriting transcript text. |
| **RAG Retrieval Chunker** | Temporally bounded text chunking with aggregated frame paths and provenance hashes. | Provides structured, citation-ready payloads for vector databases and AI agents. |
| **Observability** | Structured JSON logs, request IDs, worker IDs, and in-memory metrics registry. | Provides operational transparency, latency tracking, and queue depth monitoring. |

---

## Architecture

Textora Engine is structured into four cleanly separated architectural layers:

```mermaid
flowchart TD
    subgraph CLIENTS ["Platform Interfaces"]
        CLI["Typer CLI\n(textora-engine)"]
        SDK["Python SDK\n(TextoraClient)"]
        API["FastAPI REST Server\n(/v1/...)"]
    end

    subgraph CONTROL ["Control Plane"]
        AUTH["Auth & RBAC\n(APIKeyManager, TenantAuthorizer)"]
        IDEMP["Idempotency Engine\n(Canonical Config Hashing)"]
        DB[(Platform Database\nSQLite WAL + Migrations)]
        QUEUE["Durable Job Queue\n(Worker Leasing & Heartbeats)"]
    end

    subgraph DATA ["Data Plane (Job Workers)"]
        WORKER["Background Worker Pool"]
        LIMITER["Resource Limiter\n(Concurrency & Disk Bounds)"]
        STAGING["Artifact Staging\n(_staging/ & Atomic Promotion)"]
    end

    subgraph CORE ["Textora Core Engine"]
        DISC["Source Discovery\n(YouTube / Local Files)"]
        COORD{"Transcript Coordinator"}
        CAPTIONS["Caption Extractor\n(Local SRT / YouTube Tracks)"]
        STT["Faster-Whisper STT\n(16kHz PCM Pipeline)"]
        NORM["Normalizer\n(De-flicker & Tag Scrubbing)"]
        LANG["Linguistic Gate\n(Script & Hinglish Check)"]
        QUAL["Quality Evaluator\n(N-gram Loop Detection)"]
        VISION["Multimodal Provider\n(Frame Extraction & Alignment)"]
    end

    subgraph STORAGE ["Storage & Lineage"]
        ARTIFACTS["Data Artifacts\n(.txt, .srt, .vtt, .json)"]
        LINEAGE["Lineage Tracker\n(DAG Event Log)"]
        MANIFESTS["Execution Manifests\n(_manifests/<id>.json)"]
        VERSIONS["Dataset Versions\n(versions/v1.0.0)"]
        RAG["RAG Chunks\n(RetrievalChunk)"]
    end

    CLI --> CONTROL
    SDK --> API
    API --> AUTH
    AUTH --> IDEMP
    IDEMP --> DB
    IDEMP --> QUEUE
    QUEUE --> WORKER
    WORKER --> LIMITER
    LIMITER --> CORE

    DISC --> COORD
    COORD -- Subtitles Present --> CAPTIONS
    COORD -- Audio Only --> STT
    CAPTIONS --> NORM
    STT --> NORM
    NORM --> LANG
    LANG --> QUAL
    QUAL --> VISION
    VISION --> STAGING

    STAGING --> ARTIFACTS
    STAGING --> LINEAGE
    STAGING --> MANIFESTS
    ARTIFACTS --> VERSIONS
    ARTIFACTS --> RAG
```

### Layer Responsibilities
1. **Platform Interfaces**: CLI for local developers and terminal workflows; REST API for microservice architectures; Python SDK for programmatic pipeline orchestration.
2. **Control Plane**: Manages tenant isolation, project boundaries, API keys, idempotent job submission, and durable queue scheduling.
3. **Data Plane**: Governs worker lifecycles, sandboxed subprocesses, execution limits, temporary staging isolation, and atomic promotions.
4. **Core Engine**: Pure content processing domain without HTTP or framework coupling—handles media extraction, STT, normalization, quality evaluation, and frame extraction.

---

## End-to-End Data Flow

Every video processed through Textora Engine executes through a verifiable 16-stage pipeline:

```
 1. Source Discovery      ──► Canonicalize YouTube IDs, playlist items, or local file paths.
 2. SSRF & Security Check ──► Validate IP targets, reject private ranges and malicious URLs.
 3. Config Hashing        ──► Generate deterministic configuration fingerprint.
 4. Idempotency Check     ──► Return existing completed job if identical request was processed.
 5. Durable Queue Enqueue ──► Register job in state QUEUED with priority ordering.
 6. Worker Claim & Lease  ──► Worker claims job atomically, establishing heartbeat lease.
 7. Ingestion Routing     ──► Extract sibling subtitles if present; route to STT otherwise.
 8. Normalization         ──► Strip HTML entities, remove sound tags, and eliminate caption flickers.
 9. Linguistic Validation ──► Enforce target language and reject transliterated Hinglish.
10. Quality Evaluation    ──► Detect repetition loops, empty transcripts, and minimum length.
11. Content Fingerprint   ──► Calculate 64-bit xxHash and SHA-256 content digest.
12. Multimodal Sampling   ──► Extract visual frames at specified intervals via FFmpeg.
13. Temporal Alignment    ──► Correlate frames to transcript segments by timestamp.
14. Atomic Staging        ──► Write artifacts to _staging/<job_id>_<attempt_id> with fsync.
15. Atomic Promotion      ──► Promote files to permanent storage; verify file hashes and size > 0.
16. Lineage & Manifest    ──► Record execution manifest, update dataset manifest, acknowledge job.
```

---

## Quick Start

### Requirements
- **Python**: `3.10` or higher
- **FFmpeg**: Required for local media audio extraction and frame sampling. *(Available via system package manager or bundled via `imageio-ffmpeg`)*.

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/Pranay-Kumar-02/textora-engine.git
cd textora-engine

# Standard installation (CLI, YouTube ingestion, and validation tools)
pip install -e .

# Full installation (Local Speech-to-Text with Faster-Whisper + FFmpeg)
pip install -e ".[stt]"

# Platform installation (REST API server + SDK + dev tools)
pip install -e ".[server,dev,stt]"
```

### 2. Verify System Readiness

Run the built-in diagnostic tool to audit your Python runtime, dependencies, FFmpeg installation, and disk write permissions:

```bash
textora-engine doctor
```

Example Output:
```text
                       Textora Engine System Diagnostics                       
+-----------------------------------------------------------------------------+
| Component                 | Status          | Details / Recommendations     |
|---------------------------+-----------------+-------------------------------|
| Python Runtime            | OK              | Version 3.12.5                |
| Dependency: typer         | OK              | CLI interface framework       |
| Dependency: rich          | OK              | Terminal UI & formatting      |
| Dependency: youtube_api   | OK              | YouTube transcript engine     |
| Dependency: langdetect    | OK              | Deterministic language filter |
| Dependency: xxhash        | OK              | Fast 64-bit content hashing   |
| Media: FFmpeg             | FOUND           | Available on system PATH      |
| STT: faster-whisper       | AVAILABLE       | Local Whisper engine ready    |
| Video Understanding       | READY           | Registered: local, null       |
| Filesystem Access         | WRITABLE        | Read/write access confirmed   |
+-----------------------------------------------------------------------------+
```

---

## CLI Reference

Textora Engine exposes 11 CLI commands under `textora-engine` (or the alias `textora`).

```bash
textora-engine [COMMAND] [OPTIONS]
```

| Command | Purpose | Primary Options | Example |
|:---|:---|:---|:---|
| `extract` | Ingest and process videos into clean dataset files. | `-o`, `-l`, `--stt-model`, `--multimodal`, `--export-srt` | `textora-engine extract https://youtu.be/dQw4w9WgXcQ -o ./data` |
| `preview` | Inspect discovered sources without downloading or transcribing. | `-f`, `-p`, `-s`, `--json` | `textora-engine preview -p "https://youtube.com/playlist?list=..."` |
| `validate` | Perform cryptographic disk checksum audit against `manifest.json`. | *(Target directory argument)* | `textora-engine validate ./data` |
| `health` | Run an executive dataset health check and render a scorecard. | *(Target directory argument)* | `textora-engine health ./data` |
| `report` | Generate a self-contained, interactive HTML audit dashboard. | `--output-file` | `textora-engine report ./data` |
| `stats` | Display aggregate metrics (words, chars, durations, frames). | *(Target directory argument)* | `textora-engine stats ./data` |
| `retry` | Target and re-process previously failed items in `.state/failed.json`. | `--config`, `--profile`, `-v` | `textora-engine retry ./data` |
| `doctor` | Inspect runtime environment, FFmpeg, Whisper, and permissions. | *(None)* | `textora-engine doctor` |
| `repair` | Non-destructively rebuild missing manifests and unindexed files. | *(Target directory argument)* | `textora-engine repair ./data` |
| `version` | Create or list immutable dataset release snapshots. | `action` (`create`/`list`), `--version-tag` | `textora-engine version create ./data --version-tag v1.0.0` |
| `serve` | Launch the Textora Engine HTTP REST API server. | `--host`, `--port`, `--output`, `--db-path` | `textora-engine serve --port 8000` |

### Key CLI Examples

```bash
# 1. Extract from YouTube with companion subtitle and JSON formats
textora-engine extract https://www.youtube.com/watch?v=dQw4w9WgXcQ \
  --output ./my_dataset --export-srt --export-vtt --export-json

# 2. Extract from a batch inventory file using configuration profiles
textora-engine extract --file sources.txt --output ./my_dataset --profile high-quality

# 3. Multimodal extraction with 10-second interval frame sampling
textora-engine extract ./lecture.mp4 --output ./multimodal_data \
  --multimodal --frame-interval 10.0 --export-multimodal-md --export-multimodal-json

# 4. Audit dataset integrity and render HTML dashboard
textora-engine validate ./my_dataset
textora-engine report ./my_dataset

# 5. Snapshot dataset into an immutable release
textora-engine version create ./my_dataset --version-tag v1.0.0 --message "Initial release"

# 6. Launch platform API server
textora-engine serve --host 127.0.0.1 --port 8000 --output ./my_dataset
```

---

## REST API

Textora Engine includes a production-grade FastAPI application (`/v1/...`) with request ID tracing, security middleware, and structured error schemas.

### Starting the Server

```bash
textora-engine serve --host 127.0.0.1 --port 8000 --output ./output_data
```

Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

### API Endpoints

#### System & Health
- `GET /v1/health`: Basic liveness check.
- `GET /v1/readiness`: Deep readiness check auditing database connection, storage access, FFmpeg availability, and queue depth.
- `GET /v1/metrics`: Returns operational Prometheus-compatible metrics snapshots (API requests, queue depths, latencies).

#### Projects
- `POST /v1/projects`: Create a project boundary.
- `GET /v1/projects`: List projects within the authenticated organization.

#### Jobs (Asynchronous & Idempotent)
- `POST /v1/jobs`: Submit a video for asynchronous processing.
  - Headers: `Idempotency-Key` *(optional)*, `X-API-Key` or `Authorization: Bearer <key>`, `X-Org-ID`.
  - Body parameters: `source_uri`, `project_id`, `language`, `transcript_source`, `stt_model`, `multimodal`, `frame_interval_seconds`, `priority`.
- `GET /v1/jobs/{job_id}`: Retrieve job status, stage, attempt counts, and metadata.
- `POST /v1/jobs/{job_id}/cancel`: Request cancellation of an active or queued job.
- `GET /v1/jobs/{job_id}/artifacts`: List verified artifacts registered to this job.

#### Datasets & Versions
- `GET /v1/datasets`: List managed datasets.
- `GET /v1/datasets/{dataset_id}/versions`: List immutable version snapshots.
- `POST /v1/datasets/{dataset_id}/versions`: Create an immutable version release snapshot (`v1.0.0`).

### Example Request & Response

```bash
# Submit an asynchronous video processing job
curl -X POST http://127.0.0.1:8000/v1/jobs \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: ingest_run_001" \
  -d '{
    "source_uri": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "language": "en",
    "multimodal": true,
    "frame_interval_seconds": 10.0
  }'
```

Response (`202 Accepted`):
```json
{
  "job": {
    "id": "job_3f4e2a1b9c0d",
    "org_id": "default_org",
    "project_id": "default_project",
    "source_uri": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "state": "QUEUED",
    "priority": 0,
    "created_at": "2026-09-10T12:00:00Z"
  },
  "is_new": true,
  "message": "Job enqueued for processing"
}
```

---

## Python SDK

Textora Engine provides a lightweight, zero-dependency Python client (`TextoraClient`) built entirely on standard library primitives (`urllib.request`).

```python
from textora_engine.sdk import TextoraClient, TextoraAPIError

# Initialize client
client = TextoraClient(base_url="http://127.0.0.1:8000", api_key="tx_live_...")

try:
    # 1. Verify service readiness
    ready_status = client.readiness()
    print("Cluster Status:", ready_status["status"])

    # 2. Submit an idempotent video processing job
    submission = client.jobs.create(
        source_uri="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        language="en",
        multimodal=True,
        frame_interval_seconds=15.0,
        idempotency_key="batch_item_101",
    )
    job_id = submission["job"]["id"]
    print(f"Submitted Job ID: {job_id} (Is New: {submission['is_new']})")

    # 3. Poll job status
    job_info = client.jobs.get(job_id)
    print(f"Current State: {job_info['state']}")

    # 4. List produced artifacts once completed
    if job_info["state"] == "COMPLETED":
        artifacts = client.jobs.list_artifacts(job_id)
        for art in artifacts:
            print(f"Artifact: {art['artifact_type']} -> {art['storage_path']}")

except TextoraAPIError as e:
    print(f"API Error [{e.status_code}] ({e.error_code}): {e.message}")
    print(f"Request ID: {e.request_id}")
```

---

## Data Outputs & Artifact Structure

Textora Engine organizes generated datasets with strict physical layout rules:

```text
my_dataset/
├── transcripts/
│   ├── dQw4w9WgXcQ.txt                 # The Pure Plain Text Transcript (Strict spoken text)
│   ├── dQw4w9WgXcQ.srt                 # Optional: SubRip subtitle format
│   ├── dQw4w9WgXcQ.vtt                 # Optional: WebVTT subtitle format
│   ├── dQw4w9WgXcQ.json                # Optional: Segment timestamp JSON
│   ├── dQw4w9WgXcQ.multimodal.md       # Optional: Markdown with embedded frame citations
│   └── dQw4w9WgXcQ.multimodal.json     # Optional: Machine-readable multimodal schema
├── frames/
│   └── dQw4w9WgXcQ/
│       ├── frame_0001.jpg              # Sampled video frame (timestamp: 0.0s)
│       └── frame_0002.jpg              # Sampled video frame (timestamp: 10.0s)
├── _manifests/
│   └── exec_a1b2c3d4e5f6.json          # Immutable execution manifest with config hash
├── versions/
│   └── v1.0.0/
│       ├── manifest.json               # Frozen snapshot manifest
│       └── version_meta.json           # Release metadata and word counts
├── .state/
│   ├── processed.json                  # State ledger of completed items for resume
│   └── failed.json                     # Structured error log for targeted retry
├── manifest.json                       # Canonical dataset manifest array
├── manifest.csv                        # Spreadsheet-ready CSV export
└── stats.json                          # Aggregate execution summary metrics
```

### The Pure `.txt` Invariant
Output `.txt` files contain **strictly spoken prose**. They have zero markdown headers, zero timestamp annotations, zero speaker prefix brackets, and zero metadata footers.

*Example `transcripts/lecture_01.txt`:*
```text
We begin our discussion of distributed systems by examining the consensus problem.
When multiple nodes communicate over an unreliable network, achieving agreement on a
single shared state requires fault-tolerant consensus protocols such as Raft or Paxos...
```

---

## Multimodal Video Understanding

Modern technical videos contain essential knowledge in visual frames that text-only transcriptions lose. Textora Engine provides a provider-independent architecture for multimodal frame extraction and temporal alignment.

### Temporal Alignment
The engine aligns visual frames to transcript segments by timestamp containment or nearest temporal boundary:

```
[00:10.000 ──► 00:25.000]
"In this diagram, the client communicates directly with the durable queue."
     │
     └── Associated Visual Frame: frames/arch_demo/frame_0002.jpg (Timestamp: 00:15.000)
```

### Honest Semantics Guarantee
The built-in `LocalVideoUnderstandingProvider` extracts frames at deterministic intervals using FFmpeg.
- **What it reports**: Accurate timestamps, frame dimensions, file paths, and type `sampled_frame`.
- **What it never does**: It **never** fabricates fake OCR text, semantic categories (`code_screen`, `slide`), or artificial confidence scores.
- **Extensibility**: Advanced semantic vision models or external visual LLMs can be integrated by implementing `BaseVideoUnderstandingProvider`.

---

## RAG & AI Agent Readiness

Traditional RAG chunking across raw transcript text loses temporal context and visual evidence. Textora Engine’s `TextoraChunker` generates structured `RetrievalChunk` objects:

```json
{
  "chunk_id": "chk_8a1f9c2d0e",
  "source_id": "lecture_01",
  "dataset_version": "v1.0.0",
  "start_timestamp": 120.5,
  "end_timestamp": 165.2,
  "duration": 44.7,
  "text": "The durable queue utilizes SQLite write-ahead logging to guarantee zero-loss commits...",
  "associated_frame_paths": [
    "frames/lecture_01/frame_0012.jpg"
  ],
  "artifact_ref": "transcripts/lecture_01.txt",
  "provenance_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
}
```

This structure enables AI retrieval systems to return not just text, but exact video playback timestamps and corresponding visual slides or code screenshots.

---

## Data Integrity & Reproducibility

1. **4-State Artifact Lifecycle**: Files transition strictly through `CREATING` $\rightarrow$ `READY` $\rightarrow$ `FAILED` / `DELETED`.
2. **Isolated Staging**: Artifacts are written into `_staging/<job_id>_<attempt_id>` and flushed to disk with `os.fsync`.
3. **Atomic Promotion**: Validated files are promoted to their permanent path via `os.replace`. Partial or zero-byte files are rejected before promotion.
4. **Execution Manifests**: Every job writes an immutable manifest recording execution ID, source URI, config hash, pipeline version, stage timings, and artifact SHA-256 hashes.
5. **Non-Destructive Repair**: The `textora-engine repair` command audits disk contents against `manifest.json`. It indexes unindexed files and recalculates missing checksums **without ever altering or deleting original transcript text**.

---

## Reliability & Concurrency

- **Worker Heartbeat Leasing**: Background workers acquire jobs with a time-bounded lease. Active workers periodically send heartbeats. If a worker process terminates unexpectedly, `recover_expired_leases` automatically resets the job state for re-processing.
- **Classified Error Taxonomy**:
  - `TRANSIENT`: Rate limits, network drops, and storage lock timeouts automatically retry with exponential backoff and jitter.
  - `PERMANENT`: Linguistic mismatches, quality check failures, and invalid media stop processing immediately to avoid wasted compute.
  - `FATAL`: Missing dependencies or invalid configuration halt processing safely.
- **Resource Limiter**: Enforces strict semaphore bounds on concurrent FFmpeg and STT tasks, and verifies that the target filesystem has sufficient free disk space before initiating downloads.

---

## Security & Threat Model

Textora Engine is engineered to safely process untrusted user inputs:

- **SSRF Defense**: `URLValidator` inspects target URLs, resolving hostnames and validating every redirect hop against private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.0/8`), IPv6 link-local (`fe80::/10`), cloud metadata IP (`169.254.169.254`), and blacklisted sensitive ports (e.g. 22, 6379). Embedded credentials (`http://user:pass@host`) are explicitly rejected.
- **Sandboxed Subprocess Execution**: `SubprocessRunner` runs media extraction with `shell=False`, strict argument arrays, hard execution timeouts, and complete process-tree termination.
- **Filesystem Traversal Prevention**: `PathSanitizer` neutralizes `../` traversal, UNC paths, and Windows device names (`CON`, `PRN`, `AUX`, `NUL`).
- **Multi-Tenant Isolation**: Database queries enforce organization boundaries. Negative test suites confirm that cross-tenant access attempts return HTTP 403 `PERMISSION_DENIED`.

---

## Observability & Metrics

- **Correlation Tracing**: Every log entry includes structured fields: `timestamp`, `level`, `request_id`, `job_id`, `attempt_id`, `worker_id`, and `org_id`.
- **Sensitive Data Redaction**: Automatic log filters redact API keys, bearer tokens, passwords, and sensitive URL query parameters.
- **In-Memory Metrics Registry**: Records request counters, queue depth gauges, and duration timers exposed via `GET /v1/metrics`.

---

## Testing & Verification

Textora Engine is verified through rigorous automated test suites and real-world execution scenarios:

```bash
# Run the complete automated test suite
python -m pytest tests -v

# Run the 14-scenario real-world end-to-end suite
python tests/test_e2e_real_world.py
```

### Verified Test Summary

```
============================= 97 passed in 47.51s =============================
```

- **Domain & State Machine**: State transition validation, lifecycle enforcement, entity serialization.
- **Database & Transactions**: SQLite WAL migrations, multi-statement rollback under simulated errors.
- **Concurrency & Races**: 10 concurrent threads submitting identical idempotency keys (1 created, 9 deduplicated); 8 concurrent workers claiming a single job (exactly 1 claim).
- **Security & SSRF**: Private IP ranges, cloud metadata endpoints, redirect validation, subprocess isolation, API key verification, RBAC permissions.
- **Storage & Path Security**: Directory traversal defense, Windows reserved names, atomic staging, and promotion.
- **Dataset Versioning & Repair**: Manifest snapshot immutability, non-destructive repair of corrupt metadata.
- **Full-Chain Platform Integration**: End-to-end execution from API submission $\rightarrow$ Queue $\rightarrow$ Worker $\rightarrow$ Pipeline $\rightarrow$ Artifacts $\rightarrow$ Lineage $\rightarrow$ Versioning $\rightarrow$ Repair $\rightarrow$ RAG Chunker.
- **14/14 Real-World E2E Scenarios**: Live YouTube extraction, playlist queues, sibling subtitle ingestion, STT fallback, linguistic boundaries, quality thresholds, crash resume, and multimodal alignment.

---

## Project Structure

```text
src/textora_engine/
├── api/                      # FastAPI REST application, endpoints, and error schemas
├── cli.py                    # Typer & Rich CLI subcommands (11 commands)
├── config.py                 # TextoraConfig, profile definitions, and TOML parser
├── dataset/                  # Immutable dataset versioning and non-destructive repair
├── db/                       # SQLite WAL database connection, migrations, and repositories
├── dedup/                    # xxHash64 fingerprinting and content deduplication
├── diarization/              # Speaker diarization interfaces and data models
├── discovery/                # YouTube canonicalization, playlists, and file detection
├── domain/                   # Pure domain entities, enums, and state machines
├── exceptions.py             # Classified exception hierarchy
├── jobs/                     # Durable queue, worker pool, idempotency, retry, and limiter
├── language/                 # Script validation, Hinglish vocabulary filter, langdetect
├── lineage/                  # Execution manifests and immutable lineage DAG tracker
├── media/                    # FFmpeg audio conversion and media utilities
├── models.py                 # Core transcript and segment dataclasses
├── normalization/            # Deterministic caption de-flickering and tag removal
├── observability/            # Structured JSON logging and metrics registry
├── pipeline.py               # Core batch processing pipeline orchestrator
├── quality/                  # N-gram repetition loops and transcript quality evaluation
├── reporting/                # Terminal tables, summary statistics, and HTML dashboard
├── retrieval/                # RAG retrieval chunker with temporal and visual provenance
├── sdk/                      # Lightweight zero-dependency Python client SDK
├── security/                 # SSRF validator, subprocess runner, path sanitizer, and auth
├── state/                    # Checkpointing and resume ledger (.state/)
├── storage/                  # ArtifactManager, StorageBackend, manifest and writer
├── stt/                      # Speech-to-Text provider registry and faster-whisper backend
├── transcripts/              # Caption-first coordinator and subtitle parsers
├── validation/               # Offline dataset scanner and hash auditor
└── video_understanding/      # Multimodal frame extraction and temporal alignment
```

---

## Deployment Options

### Tier 1: Standalone CLI
Ideal for single machines, researchers, and local data collection:
```bash
textora-engine extract ./my_video.mp4 --output ./dataset
```

### Tier 2: Single-Node Platform Server
Runs the REST API server and local background worker over an embedded SQLite WAL database:
```bash
textora-engine serve --host 0.0.0.0 --port 8000 --output /data/textora
```

### Tier 3: Docker & Docker Compose
A multi-stage containerized deployment with non-root security (`textora:10001`), pre-installed FFmpeg, and persistent data volumes:

```bash
docker compose up -d
```

*`docker-compose.yml` snippet:*
```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - TEXTORA_OUTPUT_DIR=/app/output
      - TEXTORA_LOG_LEVEL=INFO
    volumes:
      - textora-data:/app/output
```

---

## Operational Limitations

To maintain strict technical honesty, the following system boundaries are documented:

1. **SQLite Concurrency Boundary**: SQLite WAL mode provides high read concurrency and safe multi-threaded writes via table serialization. Workloads exceeding 100 concurrent write operations per second should utilize PostgreSQL via the storage abstraction.
2. **Local Frame Sampling vs. Semantic Vision**: The built-in local video understanding provider performs interval-based visual frame extraction. It does not perform OCR or semantic slide classification locally. Semantic labeling requires configuring an external vision provider.
3. **YouTube Rate Limits**: Bulk YouTube caption extraction is subject to public IP throttling by YouTube. For large collections, use appropriate batch delays and worker bounds.
4. **FFmpeg System Dependency**: Media extraction and frame sampling require FFmpeg on the system `PATH`. When absent, the engine gracefully reports the limitation via `textora-engine doctor`.

---

## Strategic Roadmap

*(Future evolution points designed to build upon the current architecture)*

```
TODAY: Textora Engine (Core Processing + Dataset Engineering)
  │
  ├──► NEAR-TERM: Platform Expansion
  │      • PostgreSQL storage and metadata driver
  │      • S3 / MinIO / GCS object storage backend
  │      • Distributed Redis / Celery / RabbitMQ queue integration
  │
  ├──► MEDIUM-TERM: Rich Multimodal Intelligence
  │      • Optical Character Recognition (OCR) provider integration
  │      • Automated slide and code screen classifier
  │      • Multi-speaker diarization integration (PyAnnote)
  │
  └──► LONG-TERM: Multimodal AI Data Infrastructure
         • Multi-worker distributed clusters
         • Enterprise web audit dashboard
         • Streaming audio/video ingestion (HLS, RTMP)
         • Vector database sync (Milvus, Qdrant, Pinecone)
```

---

## Contributing

Contributions to Textora Engine are welcome!

1. Fork the repository and create a feature branch (`git checkout -b feature/my-feature`).
2. Install development dependencies:
   ```bash
   pip install -e ".[server,dev,stt]"
   ```
3. Run the automated test suite before opening a pull request:
   ```bash
   python -m pytest tests -v
   python tests/test_e2e_real_world.py
   ```
4. Adhere to the established architectural boundaries (pure core engine, sandboxed subprocesses, honest multimodal semantics, and the pure `.txt` invariant).

---

## License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for details.

```text
Copyright (c) 2026 Pranay Kumar
```

---

## Acknowledgements

Textora Engine is built upon exceptional open-source software:
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper): Highly optimized Whisper inference using CTranslate2.
- [FFmpeg](https://ffmpeg.org): Industry-standard multimedia processing framework.
- [FastAPI](https://fastapi.tiangolo.com): Modern, high-performance web framework for Python APIs.
- [Typer](https://typer.tiangolo.com) & [Rich](https://github.com/Textualize/rich): Beautiful, type-safe terminal CLI engineering.
- [xxHash](https://github.com/Cyan4973/xxHash): Extremely fast non-cryptographic hash algorithm.
- [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api): Resilient YouTube caption extraction.
