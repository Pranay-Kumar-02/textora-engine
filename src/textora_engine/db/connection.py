"""
Database connection management and backend abstraction for Textora Engine.
"""

from abc import ABC, abstractmethod
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, Generator, List, Optional, Tuple


class DatabaseBackend(ABC):
    """Abstract interface for relational metadata persistence."""

    @abstractmethod
    def execute(self, query: str, params: Tuple[Any, ...] = ()) -> int:
        """Execute non-query and return rowcount."""
        pass

    @abstractmethod
    def fetchone(self, query: str, params: Tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
        """Fetch single row as dictionary."""
        pass

    @abstractmethod
    def fetchall(self, query: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        """Fetch all matching rows as dictionaries."""
        pass

    @abstractmethod
    @contextmanager
    def transaction(self) -> Generator[Any, None, None]:
        """Context manager for ACID transaction boundaries."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close connection pools."""
        pass


class SQLiteDatabase(DatabaseBackend):
    """
    Thread-safe SQLite implementation with WAL mode and row dictionary factories.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        # Initialize WAL mode on database file
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=10000;")
        conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(str(self.db_path), timeout=10.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.execute("PRAGMA busy_timeout=10000;")
            self._local.conn = conn
        return self._local.conn

    def execute(self, query: str, params: Tuple[Any, ...] = ()) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        rowcount = cursor.rowcount
        if getattr(self._local, "tx_depth", 0) == 0:
            conn.commit()
        return rowcount

    def fetchone(self, query: str, params: Tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def fetchall(self, query: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self._get_connection()
        depth = getattr(self._local, "tx_depth", 0)
        self._local.tx_depth = depth + 1
        if depth == 0:
            conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            if depth == 0:
                conn.commit()
        except Exception:
            if depth == 0:
                conn.rollback()
            raise
        finally:
            self._local.tx_depth = depth

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None
