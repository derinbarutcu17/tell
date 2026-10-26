"""Capture evidence from agent conversations that already exist on disk.

Tell does not record anything itself. Agent tools write their sessions to disk
while the user works, and this module reads only the parts that carry a story:
what the person asked for, and what the agent concluded.

Local paths are kept for provenance and are never sent to a model.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from story_scout.models import Evidence
from story_scout.redact import redact

MAX_SESSIONS = 8
MAX_TURNS_PER_SESSION = 24
MAX_TURN_CHARS = 4000
MAX_AGENT_CHARS = 40_000
MIN_TURN_CHARS = 40

SKIP_MESSAGE_TYPES = frozenset(
    {
        "system",
        "idle",
        "model-switched",
        "agent-switched",
        "synthetic",
        "compaction",
    }
)

def default_database_paths() -> list[Path]:
    """Return candidate OpenCode session databases, most likely first."""
    candidates: list[Path] = []
    override = os.environ.get("TELL_SESSION_DB")
    if override:
        candidates.append(Path(override).expanduser())
    candidates.append(Path.home() / ".local" / "share" / "opencode" / "opencode.db")
    candidates.append(Path.home() / "Library" / "Application Support" / "opencode" / "opencode.db")
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        candidates.append(Path(xdg).expanduser() / "opencode" / "opencode.db")
    seen: set[Path] = set()
    result: list[Path] = []
    for candidate in candidates:
        resolved = candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            result.append(resolved)
    return result


def _connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    return connection


def _table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row["name"] for row in rows}


def _as_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _assistant_text(payload: dict[str, object]) -> str:
    parts: list[str] = []
    content = payload.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = _as_text(item.get("text"))
                if text:
                    parts.append(text)
    if not parts:
        for key in ("text", "message"):
            text = _as_text(payload.get(key))
            if text:
                parts.append(text)
                break
    return "\n\n".join(parts)


def _bound(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit].rstrip(), True


def _turn_evidence(
    session_id: str,
    session_title: str,
    directory: str | None,
    turns: list[tuple[str, str, str]],
    *,
    max_turns: int,
    total_budget: int,
) -> tuple[list[Evidence], list[str], int]:
    """Turn a list of (iso_date, user_text, agent_text) into Evidence items."""
    evidence: list[Evidence] = []
    omissions: list[str] = []
    consumed = 0
    short_id = session_id.replace("ses_", "")[:8]
    selected = turns[-max_turns:] if len(turns) > max_turns else turns
    if len(turns) > max_turns:
        omissions.append(
            f"omitted {len(turns) - max_turns} earlier turns from session {short_id}: turn limit ({max_turns})"
        )
    for index, (date_value, user_text, agent_text) in enumerate(selected, start=1):
        body = f"USER: {user_text}".strip()
        if agent_text:
            body = f"{body}\n\nAGENT: {agent_text}".strip()
        body = redact(body).strip()
        if len(body) < MIN_TURN_CHARS:
            continue
        body, truncated = _bound(body, MAX_TURN_CHARS)
        if truncated:
            omissions.append(f"truncated turn {index} in session {short_id}: turn character limit")
        remaining = total_budget - consumed
        if remaining <= 0:
            omissions.append(f"omitted remaining turns in session {short_id}: agent character limit")
            break
        if len(body) > remaining:
            body, _ = _bound(body, remaining)
            omissions.append(f"truncated agent evidence: total character limit ({MAX_AGENT_CHARS})")
        title = redact(session_title.strip() or short_id)
        evidence.append(
            Evidence(
                id=f"agent:{short_id}:{index}",
                label=f"{title} #{index}",
                kind="agent",
                excerpt=body,
                date=date_value,
                local_path=directory,
                commit=None,
                line_start=None,
                line_end=None,
                source="agent",
                url=None,
            )
        )
        consumed += len(body)
        if consumed >= total_budget:
            break
    return evidence, omissions, consumed


def _iso_from_ms(value: object) -> str | None:
    try:
        milliseconds = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if milliseconds <= 0:
        return None
    return datetime.fromtimestamp(milliseconds / 1000).date().isoformat()


def _normalize_dir(value: str | os.PathLike[str] | None) -> str:
    if not value:
        return ""
    try:
        return str(Path(value).expanduser().resolve())
    except (OSError, RuntimeError, ValueError):
        return str(value)


def _within_any(directory: str, roots: list[str]) -> bool:
    if not roots:
        return False
    candidate = _normalize_dir(directory)
    for root in roots:
        if candidate == root or candidate.startswith(root.rstrip("/") + "/"):
            return True
    return False


def collect_conversations(
    project_paths: object = (),
    *,
    days: int = 7,
    now: datetime | None = None,
    db_path: str | os.PathLike[str] | None = None,
    max_sessions: int = MAX_SESSIONS,
    max_turns: int = MAX_TURNS_PER_SESSION,
) -> tuple[list[Evidence], list[str]]:
    """Read recent agent sessions for the given project folders.

    Returns (evidence, omissions). Never raises for a missing or unreadable
    database; the reason is reported as an omission instead.
    """
    if isinstance(project_paths, (str, os.PathLike)):
        project_paths = [project_paths]
    roots = [_normalize_dir(path) for path in (project_paths or [])]
    roots = [root for root in roots if root]
    if not roots:
        return [], [
            "no project folder given, so no agent session was read "
            "(Tell never reads sessions outside folders you registered)"
        ]

    if db_path is not None:
        candidates = [Path(db_path).expanduser()]
        if not candidates[0].is_file():
            return [], [f"session database not found: {candidates[0]}"]
    else:
        candidates = default_database_paths()
        if not candidates:
            return [], ["no agent session database found"]

    base_now = now if now is not None else datetime.now()
    threshold_ms = int((base_now - timedelta(days=days)).timestamp() * 1000)

    evidence: list[Evidence] = []
    omissions: list[str] = []
    consumed = 0

    for database in candidates:
        connection: sqlite3.Connection | None = None
        try:
            connection = _connect_readonly(database)
        except sqlite3.Error as error:
            omissions.append(f"could not open session database {database.name}: {error}")
            continue
        try:
            tables = _table_names(connection)
            has_v2 = "session_v2" in tables and "session_message" in tables
            if not has_v2:
                omissions.append(
                    f"session database {database.name} does not use the supported "
                    "OpenCode session_v2 tables; export a conversation instead"
                )
                continue
            session_rows = connection.execute(
                "SELECT id, directory, title, time_updated FROM session_v2 "
                "WHERE time_updated >= ? AND (parent_id IS NULL OR parent_id = '') "
                "ORDER BY time_updated DESC",
                (threshold_ms,),
            ).fetchall()
            child_count = connection.execute(
                "SELECT count(*) FROM session_v2 WHERE time_updated >= ? "
                "AND parent_id IS NOT NULL AND parent_id != ''",
                (threshold_ms,),
            ).fetchone()[0]
            if child_count:
                omissions.append(f"skipped {child_count} subagent session(s): not the user's own work")

            selected = [row for row in session_rows if _within_any(row["directory"], roots)]
            if len(selected) > max_sessions:
                omissions.append(
                    f"omitted {len(selected) - max_sessions} sessions: session limit ({max_sessions})"
                )
                selected = selected[:max_sessions]

            for row in selected:
                session_id = str(row["id"])
                directory = row["directory"]
                title = row["title"] or ""
                message_rows = connection.execute(
                    "SELECT type, data FROM session_message WHERE session_id = ? ORDER BY seq",
                    (session_id,),
                ).fetchall()
                turns = _build_turns(message_rows)
                if not turns:
                    continue
                session_evidence, session_omissions, used = _turn_evidence(
                    session_id,
                    title,
                    directory,
                    turns,
                    max_turns=max_turns,
                    total_budget=MAX_AGENT_CHARS - consumed,
                )
                evidence.extend(session_evidence)
                omissions.extend(session_omissions)
                consumed += used
                if consumed >= MAX_AGENT_CHARS:
                    omissions.append(f"omitted remaining sessions: agent character limit ({MAX_AGENT_CHARS})")
                    return evidence, omissions
        except sqlite3.Error as error:
            omissions.append(f"could not read session database {database.name}: {error}")
        finally:
            if connection is not None:
                connection.close()

    return evidence, omissions


def _created_ms(payload: dict[str, object]) -> object:
    """Return the creation timestamp from a message payload, whatever its shape."""
    time_value = payload.get("time")
    if isinstance(time_value, dict):
        return time_value.get("created")
    return None


def _build_turns(message_rows: list[sqlite3.Row]) -> list[tuple[str, str, str]]:
    """Collapse raw rows into (date, user_text, agent_text) turns."""
    turns: list[tuple[str, str, str]] = []
    current_date: str | None = None
    current_user = ""
    current_agent: list[str] = []

    def flush() -> None:
        nonlocal current_user, current_agent, current_date
        if current_user or current_agent:
            turns.append(
                (
                    current_date or "",
                    current_user,
                    "\n\n".join(part for part in current_agent if part),
                )
            )
        current_user = ""
        current_agent = []

    for row in message_rows:
        try:
            payload = json.loads(row["data"])
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(payload, dict):
            continue
        try:
            message_type = str(row["type"])
            if message_type in SKIP_MESSAGE_TYPES:
                continue
            if message_type == "user":
                flush()
                current_user = _as_text(payload.get("text"))
                current_date = _iso_from_ms(_created_ms(payload)) or current_date
            elif message_type == "assistant":
                text = _assistant_text(payload)
                if text:
                    current_agent.append(text)
        except (AttributeError, TypeError, KeyError, ValueError):
            continue
    flush()
    return turns


def collect_from_export(path: str | os.PathLike[str]) -> tuple[list[Evidence], list[str]]:
    """Read a single exported conversation file (JSONL or Markdown/plain text)."""
    target = Path(path).expanduser()
    if not target.is_file():
        return [], [f"conversation export not found: {target}"]
    try:
        raw = target.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return [], [f"could not read conversation export {target.name}: {error}"]

    stem = target.stem
    if target.suffix.lower() == ".jsonl":
        turns = _turns_from_jsonl(raw)
        if not turns:
            return [], [f"no conversation turns found in {target.name}"]
        evidence, omissions, _consumed = _turn_evidence(
            f"export-{stem}",
            stem,
            str(target.parent),
            turns,
            max_turns=MAX_TURNS_PER_SESSION,
            total_budget=MAX_AGENT_CHARS,
        )
        return evidence, omissions
    body, truncated = _bound(redact(raw).strip(), MAX_TURN_CHARS)
    omissions = [f"truncated {target.name}: turn character limit"] if truncated else []
    if len(body) < MIN_TURN_CHARS:
        return [], [f"conversation export {target.name} is too short to use"]
    return (
        [
            Evidence(
                id=f"agent:{stem[:16]}:1",
                label=stem,
                kind="agent",
                excerpt=body,
                date=None,
                local_path=str(target),
                commit=None,
                line_start=None,
                line_end=None,
                source="agent",
                url=None,
            )
        ],
        omissions,
    )


def _turns_from_jsonl(raw: str) -> list[tuple[str, str, str]]:
    """Best-effort extraction from Codex-style rollout JSONL files."""
    turns: list[tuple[str, str, str]] = []
    pending_user = ""
    pending_agent: list[str] = []

    def flush() -> None:
        nonlocal pending_user, pending_agent
        if pending_user or pending_agent:
            turns.append(("", pending_user, "\n\n".join(pending_agent)))
        pending_user = ""
        pending_agent = []

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        message_type = record.get("type")
        inner_type = payload.get("type")
        if message_type == "event_msg" and inner_type == "user_message":
            flush()
            pending_user = _as_text(payload.get("message"))
            continue
        if message_type == "event_msg" and inner_type == "agent_message":
            text = _as_text(payload.get("message"))
            if text:
                pending_agent.append(text)
            continue
        if message_type == "response_item" and inner_type == "message":
            role = payload.get("role")
            text = _assistant_text(payload)
            if not text:
                continue
            if role == "user":
                flush()
                pending_user = text
            elif role == "assistant":
                pending_agent.append(text)
    flush()
    return turns
