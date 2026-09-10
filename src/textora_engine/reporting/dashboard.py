"""
Self-contained HTML dashboard generator for Textora Engine.
Produces an offline, responsive visual report with zero external CDN dependencies.
"""

import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from textora_engine.storage.writer import atomic_write_text
from textora_engine.validation.dataset_scanner import validate_dataset


def generate_html_report(
    output_dir: Path,
    target_file: Optional[Path] = None,
    title: str = "Textora Engine — Dataset Audit & Health Dashboard",
) -> Path:
    """
    Generate an offline-capable, standalone HTML dashboard summarizing
    the dataset contents, quality distribution, and health metrics.
    """
    output_dir = Path(output_dir)
    target_path = target_file or (output_dir / "report.html")

    # 1. Load manifest.json
    manifest_records: List[Dict[str, Any]] = []
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_records = json.load(f)
        except Exception:
            manifest_records = []

    # 2. Load stats.json if available
    stats_data: Dict[str, Any] = {}
    stats_path = output_dir / "stats.json"
    if stats_path.exists():
        try:
            with open(stats_path, "r", encoding="utf-8") as f:
                stats_data = json.load(f)
        except Exception:
            stats_data = {}

    # 3. Perform offline health audit
    validation = validate_dataset(output_dir)

    # 4. Aggregations
    total_records = len(manifest_records)
    total_words = sum(r.get("word_count", 0) for r in manifest_records) or validation.total_words
    total_chars = sum(r.get("character_count", 0) for r in manifest_records) or validation.total_characters
    total_frames = sum(r.get("visual_frame_count", 0) for r in manifest_records) or validation.valid_frames_on_disk

    # Languages
    lang_counts: Dict[str, int] = {}
    for r in manifest_records:
        lang = r.get("language") or "unknown"
        lang_counts[lang] = lang_counts.get(lang, 0) + 1

    # Sources
    source_counts: Dict[str, int] = {}
    for r in manifest_records:
        stype = r.get("source_type") or "unknown"
        source_counts[stype] = source_counts.get(stype, 0) + 1

    # Quality breakdown
    quality_counts: Dict[str, int] = {}
    for r in manifest_records:
        q = r.get("quality_status") or "unknown"
        quality_counts[q] = quality_counts.get(q, 0) + 1

    # Format rows for table
    table_rows = []
    for rec in manifest_records[:100]:  # limit to top 100 in table
        t_title = html.escape(str(rec.get("title", "Untitled")))
        t_src = html.escape(str(rec.get("source_type", "unknown")).upper())
        t_lang = html.escape(str(rec.get("language", "auto")).upper())
        t_words = f"{rec.get('word_count', 0):,}"
        t_frames = str(rec.get("visual_frame_count", 0))
        t_status = html.escape(str(rec.get("status", "SUCCESS")).upper())
        t_quality = html.escape(str(rec.get("quality_status", "PASS")).upper())
        badge_class = "badge-green" if t_status == "SUCCESS" else "badge-red"
        table_rows.append(
            f"<tr>"
            f"<td><strong>{t_title}</strong></td>"
            f"<td><span class='badge'>{t_src}</span></td>"
            f"<td><span class='badge'>{t_lang}</span></td>"
            f"<td class='num'>{t_words}</td>"
            f"<td class='num'>{t_frames}</td>"
            f"<td><span class='badge {badge_class}'>{t_status}</span></td>"
            f"<td><span class='badge'>{t_quality}</span></td>"
            f"</tr>"
        )
    table_body = "\n".join(table_rows) if table_rows else "<tr><td colspan='7' style='text-align:center;'>No records found in manifest.json</td></tr>"

    # Bar chart helpers
    def render_bars(data: Dict[str, int]) -> str:
        if not data:
            return "<p class='dim'>No data</p>"
        max_val = max(data.values()) if data else 1
        bars = []
        for k, v in sorted(data.items(), key=lambda x: x[1], reverse=True):
            pct = round((v / max_val) * 100, 1)
            bars.append(
                f"<div class='bar-row'>"
                f"<div class='bar-label'>{html.escape(k)}</div>"
                f"<div class='bar-track'><div class='bar-fill' style='width: {pct}%;'></div></div>"
                f"<div class='bar-val'>{v}</div>"
                f"</div>"
            )
        return "\n".join(bars)

    lang_bars = render_bars(lang_counts)
    quality_bars = render_bars(quality_counts)
    source_bars = render_bars(source_counts)

    health_class = "health-good" if validation.is_healthy else "health-warn"
    health_title = "SYSTEM HEALTHY" if validation.is_healthy else "ISSUES DETECTED"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<style>
  :root {{
    --bg: #0d1117;
    --card: #161b22;
    --card-border: #30363d;
    --text: #e6edf3;
    --text-dim: #8b949e;
    --accent: #58a6ff;
    --green: #2ea043;
    --yellow: #d29922;
    --red: #f85149;
    --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background-color: var(--bg);
    color: var(--text);
    font-family: var(--font);
    padding: 32px 24px;
    line-height: 1.5;
  }}
  .container {{
    max-width: 1200px;
    margin: 0 auto;
  }}
  header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--card-border);
    padding-bottom: 24px;
    margin-bottom: 32px;
  }}
  .header-left h1 {{
    font-size: 1.8rem;
    font-weight: 700;
    letter-spacing: -0.5px;
    color: #ffffff;
  }}
  .header-left p {{
    color: var(--text-dim);
    font-size: 0.95rem;
    margin-top: 4px;
  }}
  .score-badge {{
    display: flex;
    flex-direction: column;
    align-items: center;
    background: var(--card);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 12px 20px;
  }}
  .score-val {{
    font-size: 2rem;
    font-weight: 800;
    color: var(--accent);
  }}
  .score-label {{
    font-size: 0.75rem;
    text-transform: uppercase;
    color: var(--text-dim);
    letter-spacing: 1px;
  }}
  .metrics-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
  }}
  .card {{
    background: var(--card);
    border: 1px solid var(--card-border);
    border-radius: 8px;
    padding: 20px;
  }}
  .card-label {{
    font-size: 0.85rem;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  .card-value {{
    font-size: 1.9rem;
    font-weight: 700;
    color: #ffffff;
    margin-top: 6px;
  }}
  .card-sub {{
    font-size: 0.8rem;
    color: var(--text-dim);
    margin-top: 4px;
  }}
  .charts-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
    gap: 20px;
    margin-bottom: 32px;
  }}
  .chart-title {{
    font-size: 1rem;
    font-weight: 600;
    margin-bottom: 16px;
    color: var(--text);
  }}
  .bar-row {{
    display: flex;
    align-items: center;
    margin-bottom: 10px;
    font-size: 0.85rem;
  }}
  .bar-label {{
    width: 100px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--text);
  }}
  .bar-track {{
    flex: 1;
    height: 8px;
    background: #21262d;
    border-radius: 4px;
    margin: 0 12px;
    overflow: hidden;
  }}
  .bar-fill {{
    height: 100%;
    background: var(--accent);
    border-radius: 4px;
  }}
  .bar-val {{
    width: 40px;
    text-align: right;
    color: var(--text-dim);
  }}
  .table-container {{
    background: var(--card);
    border: 1px solid var(--card-border);
    border-radius: 8px;
    overflow-x: auto;
    margin-bottom: 32px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.88rem;
    text-align: left;
  }}
  th {{
    background: #21262d;
    padding: 12px 16px;
    color: var(--text-dim);
    font-weight: 600;
    border-bottom: 1px solid var(--card-border);
  }}
  td {{
    padding: 12px 16px;
    border-bottom: 1px solid #21262d;
  }}
  td.num {{
    text-align: right;
    font-family: monospace;
  }}
  .badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.75rem;
    background: #21262d;
    color: var(--text);
  }}
  .badge-green {{
    background: rgba(46, 160, 67, 0.2);
    color: #3fb950;
    border: 1px solid rgba(46, 160, 67, 0.4);
  }}
  .badge-red {{
    background: rgba(248, 81, 73, 0.2);
    color: #f85149;
    border: 1px solid rgba(248, 81, 73, 0.4);
  }}
  .health-banner {{
    padding: 16px 20px;
    border-radius: 8px;
    margin-bottom: 32px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .health-good {{
    background: rgba(46, 160, 67, 0.15);
    border: 1px solid var(--green);
    color: #3fb950;
  }}
  .health-warn {{
    background: rgba(248, 81, 73, 0.15);
    border: 1px solid var(--red);
    color: #f85149;
  }}
  footer {{
    text-align: center;
    color: var(--text-dim);
    font-size: 0.85rem;
    margin-top: 40px;
    border-top: 1px solid var(--card-border);
    padding-top: 20px;
  }}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="header-left">
      <h1>Textora Engine</h1>
      <p>Dataset Audit, Integrity, and Multimodal Health Report</p>
    </div>
    <div class="score-badge">
      <span class="score-val">{validation.health_score}</span>
      <span class="score-label">Health Score</span>
    </div>
  </header>

  <div class="health-banner {health_class}">
    <div>
      <strong>{health_title}:</strong> {validation.valid_files_on_disk} verified on disk, {len(validation.missing_files)} missing, {len(validation.empty_or_corrupt_files)} corrupt, {len(validation.hash_mismatches)} hash mismatches.
    </div>
  </div>

  <div class="metrics-grid">
    <div class="card">
      <div class="card-label">Total Transcripts</div>
      <div class="card-value">{total_records:,}</div>
      <div class="card-sub">{validation.valid_files_on_disk} verified on disk</div>
    </div>
    <div class="card">
      <div class="card-label">Spoken Words</div>
      <div class="card-value">{total_words:,}</div>
      <div class="card-sub">{total_chars:,} characters</div>
    </div>
    <div class="card">
      <div class="card-label">Visual Frames</div>
      <div class="card-value">{total_frames:,}</div>
      <div class="card-sub">Synchronized multimodal frames</div>
    </div>
    <div class="card">
      <div class="card-label">Health Score</div>
      <div class="card-value">{validation.health_score}/100</div>
      <div class="card-sub">{len(validation.unindexed_files)} unindexed files</div>
    </div>
  </div>

  <div class="charts-grid">
    <div class="card">
      <div class="chart-title">Languages</div>
      {lang_bars}
    </div>
    <div class="card">
      <div class="chart-title">Quality Tiers</div>
      {quality_bars}
    </div>
    <div class="card">
      <div class="chart-title">Source Types</div>
      {source_bars}
    </div>
  </div>

  <div class="table-container">
    <table>
      <thead>
        <tr>
          <th>Title</th>
          <th>Source</th>
          <th>Language</th>
          <th style="text-align: right;">Words</th>
          <th style="text-align: right;">Frames</th>
          <th>Status</th>
          <th>Quality</th>
        </tr>
      </thead>
      <tbody>
        {table_body}
      </tbody>
    </table>
  </div>

  <footer>
    Generated by Textora Engine &bull; Deterministic Dataset Synthesis
  </footer>
</div>
</body>
</html>
"""

    atomic_write_text(target_path, html_content)
    return target_path
