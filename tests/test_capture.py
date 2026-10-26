from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from story_scout.capture import (
    MAX_TURN_CHARS,
    collect_conversations,
    collect_from_export,
    redact,
)


NOW = datetime(2026, 10, 26, 12, 0, 0)


def _make_v2_database(
    path: Path,
    sessions: list[tuple[str, str, str, int, str | None]],
    messages: dict[str, list[tuple[str, str]]],
) -> None:
    """sessions: (id, directory, title, time_updated_ms, parent_id)."""
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE session_v2 (
            id TEXT PRIMARY KEY,
            directory TEXT NOT NULL,
            title TEXT,
            time_updated INTEGER NOT NULL,
            parent_id TEXT
        );
        CREATE TABLE session_message (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            type TEXT NOT NULL,
            seq INTEGER NOT NULL,
            time_created INTEGER NOT NULL,
            time_updated INTEGER NOT NULL,
            data TEXT NOT NULL
        );
        """
    )
    for session_id, directory, title, updated, parent_id in sessions:
        connection.execute(
            "INSERT INTO session_v2 VALUES (?, ?, ?, ?, ?)",
            (session_id, directory, title, updated, parent_id),
        )
    counter = 0
    for session_id, rows in messages.items():
        for sequence, (message_type, data) in enumerate(rows):
            counter += 1
            connection.execute(
                "INSERT INTO session_message VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f"msg_{counter}",
                    session_id,
                    message_type,
                    sequence,
                    int(NOW.timestamp() * 1000),
                    int(NOW.timestamp() * 1000),
                    json.dumps(data),
                ),
            )
    connection.commit()
    connection.close()


def _user(text: str) -> tuple[str, dict]:
    return ("user", {"time": {"created": int(NOW.timestamp() * 1000)}, "text": text})


def _assistant(text: str) -> tuple[str, dict]:
    return ("assistant", {"content": [{"type": "text", "text": text}]})


class CaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="tell-capture-")
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.db = self.root / "opencode.db"
        self.recent = int((NOW - timedelta(days=1)).timestamp() * 1000)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_captures_turns_for_the_registered_project(self) -> None:
        _make_v2_database(
            self.db,
            [( "ses_aaaa1111", str(self.project), "Rewrite the parser", self.recent, None)],
            {
                "ses_aaaa1111": [
                    _user("The parser kept dropping the last line of every file I opened today."),
                    _assistant("The trailing newline was stripped before the split, so the last row vanished."),
                    ("system", {"text": "noise"}),
                ]
            },
        )
        evidence, omissions = collect_conversations([self.project], days=7, now=NOW, db_path=self.db)
        self.assertEqual(len(evidence), 1)
        item = evidence[0]
        self.assertEqual(item.kind, "agent")
        self.assertEqual(item.source, "agent")
        self.assertEqual(item.label, "Rewrite the parser #1")
        self.assertIn("last line", item.excerpt)
        self.assertIn("AGENT:", item.excerpt)
        self.assertEqual(item.date, NOW.date().isoformat())
        self.assertEqual(omissions, [])

    def test_ignores_sessions_outside_the_registered_project(self) -> None:
        other = self.root / "other"
        other.mkdir()
        _make_v2_database(
            self.db,
            [
                ("ses_aaaa1111", str(self.project), "Mine", self.recent, None),
                ("ses_bbbb2222", str(other), "Not mine", self.recent, None),
            ],
            {
                "ses_aaaa1111": [_user("A real problem I hit while building the thing today."), _assistant("Fixed.")],
                "ses_bbbb2222": [_user("Unrelated work that must never be captured here."), _assistant("Ok.")],
            },
        )
        evidence, _ = collect_conversations([self.project], days=7, now=NOW, db_path=self.db)
        self.assertEqual(len(evidence), 1)
        self.assertIn("real problem", evidence[0].excerpt)
        self.assertNotIn("Unrelated", evidence[0].excerpt)

    def test_child_subagent_sessions_are_skipped(self) -> None:
        _make_v2_database(
            self.db,
            [
                ("ses_aaaa1111", str(self.project), "Mine", self.recent, None),
                ("ses_cccc3333", str(self.project), "Subagent", self.recent, "ses_aaaa1111"),
            ],
            {
                "ses_aaaa1111": [_user("The real work I did on my own machine this week."), _assistant("Done.")],
                "ses_cccc3333": [_user("Subagent chatter that should never become a story idea."), _assistant("Ok.")],
            },
        )
        evidence, omissions = collect_conversations([self.project], days=7, now=NOW, db_path=self.db)
        self.assertEqual(len(evidence), 1)
        self.assertNotIn("Subagent chatter", evidence[0].excerpt)
        self.assertTrue(any("subagent" in omission for omission in omissions))

    def test_old_sessions_are_excluded_by_window(self) -> None:
        old = int((NOW - timedelta(days=30)).timestamp() * 1000)
        _make_v2_database(
            self.db,
            [("ses_old99999", str(self.project), "Old", old, None)],
            {"ses_old99999": [_user("Ancient work that is outside the requested window."), _assistant("Ok.")]},
        )
        evidence, _ = collect_conversations([self.project], days=7, now=NOW, db_path=self.db)
        self.assertEqual(evidence, [])

    def test_redaction_removes_secrets_and_home_paths(self) -> None:
        text = (
            "I pasted sk-abcdefghijklmnop1234 into the config and my password=hunter2 leaked, "
            "plus the log at /Users/derin/private/notes.txt."
        )
        cleaned = redact(text)
        self.assertNotIn("sk-abcdefghijklmnop1234", cleaned)
        self.assertNotIn("hunter2", cleaned)
        self.assertNotIn("/Users/derin", cleaned)
        self.assertIn("[redacted-secret]", cleaned)
        self.assertIn("~/private/notes.txt", cleaned)

    def test_turn_length_is_bounded_and_reported(self) -> None:
        long_text = "This is a long working note. " * 400
        _make_v2_database(
            self.db,
            [("ses_aaaa1111", str(self.project), "Long", self.recent, None)],
            {"ses_aaaa1111": [_user(long_text), _assistant(long_text)]},
        )
        evidence, omissions = collect_conversations([self.project], days=7, now=NOW, db_path=self.db)
        self.assertEqual(len(evidence), 1)
        self.assertLessEqual(len(evidence[0].excerpt), MAX_TURN_CHARS)
        self.assertTrue(any("character limit" in omission for omission in omissions))

    def test_missing_database_is_reported_not_raised(self) -> None:
        evidence, omissions = collect_conversations(
            [self.project], days=7, now=NOW, db_path=self.root / "absent.db"
        )
        self.assertEqual(evidence, [])
        self.assertTrue(any("not found" in omission for omission in omissions))

    def test_unreadable_database_is_reported_not_raised(self) -> None:
        broken = self.root / "broken.db"
        broken.write_text("not a database", encoding="utf-8")
        evidence, omissions = collect_conversations([self.project], days=7, now=NOW, db_path=broken)
        self.assertEqual(evidence, [])
        self.assertTrue(omissions)

    def test_export_markdown_is_captured(self) -> None:
        export = self.root / "conversation.md"
        export.write_text(
            "I spent the morning fighting a cache bug and found the real cause was a stale index.\n",
            encoding="utf-8",
        )
        evidence, omissions = collect_from_export(export)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].source, "agent")
        self.assertIn("stale index", evidence[0].excerpt)
        self.assertEqual(omissions, [])

    def test_export_jsonl_is_captured(self) -> None:
        export = self.root / "rollout.jsonl"
        records = [
            {"type": "event_msg", "payload": {"type": "user_message", "message": "Why does the build keep timing out after exactly ninety seconds?"}},
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "The test runner waits on a network call that never returns."}},
        ]
        export.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
        evidence, _ = collect_from_export(export)
        self.assertEqual(len(evidence), 1)
        self.assertIn("ninety seconds", evidence[0].excerpt)
        self.assertIn("never returns", evidence[0].excerpt)

    def test_no_project_filter_refuses_to_read_everything(self) -> None:
        _make_v2_database(
            self.db,
            [("ses_aaaa1111", str(self.project), "Mine", self.recent, None)],
            {"ses_aaaa1111": [_user("Any recent work counts when no project filter is given."), _assistant("Ok.")]},
        )
        evidence, omissions = collect_conversations(days=7, now=NOW, db_path=self.db)
        self.assertEqual(evidence, [])
        self.assertTrue(any("no project folder given" in omission for omission in omissions))

    def test_session_titles_are_redacted_in_labels_and_packets(self) -> None:
        title = "fix ghp_abcdefghijklmnopqrstuvwxyz for /Users/derin/secret-project/notes.md"
        _make_v2_database(
            self.db,
            [("ses_aaaa1111", str(self.project), title, self.recent, None)],
            {"ses_aaaa1111": [_user("A real problem I hit while building this thing today."), _assistant("Fixed.")]},
        )
        evidence, _ = collect_conversations([self.project], days=7, now=NOW, db_path=self.db)
        self.assertEqual(len(evidence), 1)
        label = evidence[0].label
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz", label)
        self.assertNotIn("/Users/derin", label)
        packet_label = evidence[0].public_dict()["label"]
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz", str(packet_label))
        self.assertNotIn("/Users/derin", str(packet_label))

    def test_unsupported_session_layout_is_reported(self) -> None:
        connection = sqlite3.connect(self.db)
        connection.executescript(
            """
            CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT, time_updated INTEGER);
            CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, data TEXT);
            CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, data TEXT);
            """
        )
        connection.execute("INSERT INTO session VALUES ('ses_old', 'Old', ?)", (self.recent,))
        connection.commit()
        connection.close()
        evidence, omissions = collect_conversations([self.project], days=7, now=NOW, db_path=self.db)
        self.assertEqual(evidence, [])
        self.assertTrue(any("does not use the supported" in omission for omission in omissions))


if __name__ == "__main__":
    unittest.main()
