# Textora Engine

Universal Video-to-Text & Dataset Collection Tool.

Converts videos (YouTube, local files, folders, batch lists) into clean, faithful, dataset-ready plain text corpora.

## Features
- **Universal Discovery**: Automatically detects YouTube URLs, playlists, local video files (`.mp4`, `.mkv`, `.webm`, etc.), directories, and batch text files.
- **Dual Engine**: Prefers native/embedded subtitles and captions; seamlessly falls back to Speech-to-Text (Faster-Whisper).
- **Deterministic Quality**: Automatic language validation, repetition filtering, character density analysis, and quality tiering.
- **Pure Output**: Outputs 100% pure text transcripts with companion `.srt`, `.vtt`, and structured `manifest.json`.
- **Atomic Persistence**: Crash-safe atomic writes and checkpoint resume.

## Quickstart
```bash
# Preview inputs
python -m textora_engine preview https://www.youtube.com/watch?v=dQw4w9WgXcQ

# Extract transcripts
python -m textora_engine extract https://www.youtube.com/watch?v=dQw4w9WgXcQ --output ./dataset

# Audit dataset
python -m textora_engine validate ./dataset

# View dataset statistics
python -m textora_engine stats ./dataset

# Run system diagnostics
python -m textora_engine doctor
```

Alternatively, use the installed CLI command directly:
```bash
textora-engine --help
```
