"""SQLite persistence for Story Scout sources and candidates."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
VALID_STATUSES = {"new", "kept", "rejected"}

STORY_COLUMNS = {
    "fact": "TEXT",
    "interpretation": "TEXT",
    "channel_x": "TEXT",
    "channel_linkedin": "TEXT",
    "research_urls": "TEXT",
    "research_query": "TEXT",
}
EVIDENCE_COLUMNS = {
    "source": "TEXT",
    "url": "TEXT",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class InvalidSourcePath(ValueError, FileNotFoundError):
    """Raised when a source path is not an existing directory."""


def _resolve_path(path: Any) -> Path:
    return Path(path).expanduser().resolve()


def _candidate_dict(candidate: Any) -> dict[str, Any]:
    if isinstance(candidate, dict):
        data = dict(candidate)
    elif is_dataclass(candidate):
        data = asdict(candidate)
    else:
        data = {}
        for field in ("title", "angle", "rationale", "audience", "evidence_ids", "confidence"):
            if hasattr(candidate, field):
                data[field] = getattr(candidate, field)
    evidence_ids = data.get("evidence_ids", [])
    if isinstance(evidence_ids, tuple):
        evidence_ids = list(evidence_ids)
    if evidence_ids is None:
        evidence_ids = []
    research_urls = data.get("research_urls", ())
    if isinstance(research_urls, tuple):
        research_urls = list(research_urls)
    if research_urls is None:
        research_urls = []
    return {
        "title": data.get("title"),
        "angle": data.get("angle"),
        "rationale": data.get("rationale"),
        "audience": data.get("audience"),
        "confidence": data.get("confidence", 0.0),
        "evidence_ids": [str(item) for item in evidence_ids],
        "fact": data.get("fact") or "",
        "interpretation": data.get("interpretation") or "",
        "channel_x": data.get("channel_x") or "",
        "channel_linkedin": data.get("channel_linkedin") or "",
        "research_urls": [str(item) for item in research_urls],
        "research_query": data.get("research_query") or "",
    }


def _evidence_dict(evidence: Any) -> dict[str, Any]:
    if isinstance(evidence, dict):
        data = dict(evidence)
    elif is_dataclass(evidence):
        data = asdict(evidence)
    else:
        data = {}
        for field in ("id", "label", "kind", "excerpt", "date", "local_path", "commit", "line_start", "line_end"):
            if hasattr(evidence, field):
                data[field] = getattr(evidence, field)
    return {
        "id": str(data.get("id")),
        "label": data.get("label"),
        "kind": data.get("kind"),
        "excerpt": data.get("excerpt"),
        "date": data.get("date"),
        "local_path": data.get("local_path"),
        "commit": data.get("commit"),
        "line_start": data.get("line_start"),
        "line_end": data.get("line_end"),
        "source": data.get("source"),
        "url": data.get("url"),
    }


class Store:
    def __init__(self, db_path: Any) -> None:
        self.db_path = db_path
        self._memory_conn: sqlite3.Connection | None = None
        path = Path(db_path)
        if str(db_path) != ":memory:":
            path = path.expanduser()
            self.db_path = path
            parent = path.parent
            if str(parent) not in ("", "."):
                parent.mkdir(parents=True, exist_ok=True)
            if path.is_symlink():
                raise ValueError("database path must not be a symlink")
            if path.exists():
                if not path.is_file():
                    raise ValueError("database path must be a file")
                path.chmod(0o600)
            else:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
                os.close(descriptor)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        if str(self.db_path) == ":memory:":
            if self._memory_conn is None:
                conn = sqlite3.connect(":memory:")
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON")
                self._memory_conn = conn
            return self._memory_conn
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            if conn is not self._memory_conn:
                conn.close()

    def _init_schema(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS stories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    angle TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    audience TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_ids TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    draft TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    fact TEXT,
                    interpretation TEXT,
                    channel_x TEXT,
                    channel_linkedin TEXT,
                    research_urls TEXT,
                    research_query TEXT
                );
                CREATE TABLE IF NOT EXISTS story_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    story_id INTEGER NOT NULL,
                    evidence_id TEXT NOT NULL,
                    label TEXT,
                    kind TEXT,
                    excerpt TEXT,
                    date TEXT,
                    local_path TEXT,
                    "commit" TEXT,
                    line_start INTEGER,
                    line_end INTEGER,
                    source TEXT,
                    url TEXT,
                    FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE
                );
                """
            )
            self._ensure_columns(conn, "stories", STORY_COLUMNS)
            self._ensure_columns(conn, "story_evidence", EVIDENCE_COLUMNS)
            row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
            if row is None:
                conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
            else:
                current = int(row["version"])
                if current < SCHEMA_VERSION:
                    conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))

    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, declaration in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

    def add_source(self, path: Any) -> int:
        resolved = _resolve_path(path)
        if not resolved.exists() or not resolved.is_dir():
            raise InvalidSourcePath(f"source path is not an existing directory: {resolved}")
        with self._connection() as conn:
            existing = conn.execute(
                "SELECT id FROM sources WHERE path = ?", (str(resolved),)
            ).fetchone()
            if existing is not None:
                return int(existing["id"])
            cursor = conn.execute(
                "INSERT INTO sources (path, created_at) VALUES (?, ?)",
                (str(resolved), _now()),
            )
            return int(cursor.lastrowid)

    def list_sources(self) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT id, path FROM sources ORDER BY id").fetchall()
        return [{"id": int(row["id"]), "path": row["path"]} for row in rows]

    def remove_source(self, source_id: Any) -> bool:
        with self._connection() as conn:
            cursor = conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
            return cursor.rowcount > 0

    def save_candidates(self, candidates: Any, evidence: Any) -> list[int]:
        evidence_items = list(evidence) if evidence is not None else []
        evidence_by_id = {}
        for item in evidence_items:
            record = _evidence_dict(item)
            evidence_by_id[record["id"]] = record
        research_by_url = {
            record["url"]: record
            for record in evidence_by_id.values()
            if record.get("url")
        }

        result_ids: list[int] = []
        with self._connection() as conn:
            for candidate in (candidates or []):
                data = _candidate_dict(candidate)
                verified_urls = [url for url in data["research_urls"] if url in research_by_url]
                now = _now()
                cursor = conn.execute(
                    """
                    INSERT INTO stories
                    (title, angle, rationale, audience, confidence, evidence_ids,
                     status, draft, created_at, updated_at,
                     fact, interpretation, channel_x, channel_linkedin, research_urls,
                     research_query)
                    VALUES (?, ?, ?, ?, ?, ?, 'new', NULL, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["title"],
                        data["angle"],
                        data["rationale"],
                        data["audience"],
                        float(data["confidence"]) if data["confidence"] is not None else 0.0,
                        json.dumps(data["evidence_ids"]),
                        now,
                        now,
                        data["fact"],
                        data["interpretation"],
                        data["channel_x"],
                        data["channel_linkedin"],
                        json.dumps(verified_urls),
                        data["research_query"],
                    ),
                )
                story_id = int(cursor.lastrowid)
                stored_ids: set[str] = set()
                for evidence_id in data["evidence_ids"]:
                    record = evidence_by_id.get(evidence_id)
                    if record is None:
                        record = {
                            "id": evidence_id,
                            "label": None,
                            "kind": None,
                            "excerpt": None,
                            "date": None,
                            "local_path": None,
                            "commit": None,
                            "line_start": None,
                            "line_end": None,
                            "source": None,
                            "url": None,
                        }
                    self._insert_evidence(conn, story_id, record)
                    stored_ids.add(str(record["id"]))
                for url in data["research_urls"]:
                    record = research_by_url.get(url)
                    if record is None or str(record["id"]) in stored_ids:
                        continue
                    self._insert_evidence(conn, story_id, record)
                    stored_ids.add(str(record["id"]))
                result_ids.append(story_id)
        return result_ids

    @staticmethod
    def _insert_evidence(conn: sqlite3.Connection, story_id: int, record: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO story_evidence
            (story_id, evidence_id, label, kind, excerpt, date,
             local_path, "commit", line_start, line_end, source, url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                story_id,
                record["id"],
                record["label"],
                record["kind"],
                record["excerpt"],
                record["date"],
                record["local_path"],
                record["commit"],
                record["line_start"],
                record["line_end"],
                record["source"],
                record["url"],
            ),
        )

    def _row_to_story(self, conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        story_id = int(row["id"])
        evidence_rows = conn.execute(
            """
            SELECT evidence_id, label, kind, excerpt, date, local_path, "commit",
                   line_start, line_end, source, url
            FROM story_evidence
            WHERE story_id = ?
            ORDER BY id
            """,
            (story_id,),
        ).fetchall()
        evidence = [
            {
                "id": r["evidence_id"],
                "label": r["label"],
                "kind": r["kind"],
                "excerpt": r["excerpt"],
                "date": r["date"],
                "local_path": r["local_path"],
                "commit": r["commit"],
                "line_start": r["line_start"],
                "line_end": r["line_end"],
                "source": r["source"],
                "url": r["url"],
            }
            for r in evidence_rows
        ]
        try:
            evidence_ids = json.loads(row["evidence_ids"])
        except (json.JSONDecodeError, TypeError):
            evidence_ids = []
        if not isinstance(evidence_ids, list):
            evidence_ids = list(evidence_ids) if evidence_ids is not None else []
        try:
            research_urls = json.loads(row["research_urls"]) if row["research_urls"] else []
        except (json.JSONDecodeError, TypeError):
            research_urls = []
        if not isinstance(research_urls, list):
            research_urls = []
        return {
            "id": story_id,
            "title": row["title"],
            "angle": row["angle"],
            "rationale": row["rationale"],
            "audience": row["audience"],
            "confidence": row["confidence"],
            "evidence_ids": evidence_ids,
            "status": row["status"],
            "draft": row["draft"],
            "fact": row["fact"] or "",
            "interpretation": row["interpretation"] or "",
            "channel_x": row["channel_x"] or "",
            "channel_linkedin": row["channel_linkedin"] or "",
            "research_urls": research_urls,
            "research_query": row["research_query"] or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "evidence": evidence,
        }

    def list_stories(self, status: Any = None) -> list[dict[str, Any]]:
        with self._connection() as conn:
            if status is None:
                rows = conn.execute("SELECT * FROM stories ORDER BY id").fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM stories WHERE status = ? ORDER BY id", (status,)
                ).fetchall()
            # Need evidence per row; fetch within same connection.
            result = []
            for row in rows:
                result.append(self._row_to_story(conn, row))
        return result

    def get_story(self, story_id: Any) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
            if row is None:
                return None
            return self._row_to_story(conn, row)

    def set_status(self, story_id: Any, status: Any) -> bool:
        if status not in VALID_STATUSES:
            return False
        with self._connection() as conn:
            cursor = conn.execute(
                "UPDATE stories SET status = ?, updated_at = ? WHERE id = ?",
                (status, _now(), story_id),
            )
            return cursor.rowcount > 0

    def set_draft(self, story_id: Any, text: Any) -> bool:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT status FROM stories WHERE id = ?", (story_id,)
            ).fetchone()
            if row is None or row["status"] != "kept":
                return False
            cursor = conn.execute(
                "UPDATE stories SET draft = ?, updated_at = ? WHERE id = ?",
                (text, _now(), story_id),
            )
            return cursor.rowcount > 0

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._connection() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row is not None else default

    def set_setting(self, key: str, value: str) -> None:
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
