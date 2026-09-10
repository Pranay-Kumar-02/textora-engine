"""
Database migration engine for Textora Engine.
Tracks and applies versioned SQL migrations deterministically.
"""

from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
from typing import List, Optional, Tuple

from textora_engine.db.connection import DatabaseBackend

logger = logging.getLogger("textora_engine.db.migrations")


class MigrationRunner:
    """Manages schema versioning and deterministic execution of migration files."""

    def __init__(self, db: DatabaseBackend, migrations_dir: Optional[Path] = None):
        self.db = db
        if migrations_dir is None:
            self.migrations_dir = Path(__file__).parent / "migrations"
        else:
            self.migrations_dir = Path(migrations_dir)

    def init_migration_table(self) -> None:
        """Create migration tracking table if not present."""
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS _schema_migrations (
                version TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
        """)

    def get_applied_versions(self) -> List[str]:
        self.init_migration_table()
        rows = self.db.fetchall("SELECT version FROM _schema_migrations ORDER BY version ASC")
        return [r["version"] for r in rows]

    def run_pending_migrations(self) -> List[str]:
        """Discover and execute all unapplied SQL migrations in sequence."""
        self.init_migration_table()
        applied = set(self.get_applied_versions())

        if not self.migrations_dir.exists():
            return []

        sql_files = sorted(self.migrations_dir.glob("*.sql"))
        applied_now: List[str] = []

        for sql_path in sql_files:
            version_part = sql_path.stem.split("_")[0]
            if version_part in applied:
                continue

            sql_content = sql_path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql_content.encode("utf-8")).hexdigest()

            logger.info(f"Applying migration {sql_path.name} (version {version_part})...")
            with self.db.transaction() as conn:
                # SQLite executescript allows multiple statements
                conn.executescript(sql_content)
                conn.execute(
                    "INSERT INTO _schema_migrations (version, name, checksum, applied_at) VALUES (?, ?, ?, ?)",
                    (version_part, sql_path.name, checksum, datetime.now(timezone.utc).isoformat()),
                )

            applied_now.append(version_part)

        return applied_now
