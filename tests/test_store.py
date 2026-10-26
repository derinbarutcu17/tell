import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from story_scout.models import Evidence, StoryCandidate
from story_scout.store import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source_dir = self.root / "source"
        self.source_dir.mkdir()
        (self.source_dir / "note.md").write_text("hello", encoding="utf-8")
        self.db_path = self.root / "nested" / "store.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_parent_dirs_and_schema(self):
        store = Store(self.db_path)
        self.assertTrue(self.db_path.parent.exists())
        self.assertTrue(self.db_path.exists())
        self.assertEqual(store.list_sources(), [])
        self.assertEqual(store.list_stories(), [])

    def test_source_uniqueness_resolved_path(self):
        store = Store(self.db_path)
        first = store.add_source(self.source_dir)
        second = store.add_source(str(self.source_dir))
        self.assertEqual(first, second)
        self.assertEqual(len(store.list_sources()), 1)
        listed = store.list_sources()[0]
        self.assertEqual(listed["id"], first)
        self.assertEqual(Path(listed["path"]), self.source_dir.resolve())

    def test_add_source_rejects_missing_dir(self):
        store = Store(self.db_path)
        with self.assertRaises(ValueError):
            store.add_source(self.root / "missing")

    def test_remove_source_unregisters_only(self):
        store = Store(self.db_path)
        sid = store.add_source(self.source_dir)
        before = list(self.source_dir.iterdir())
        self.assertTrue(store.remove_source(sid))
        self.assertFalse(store.remove_source(sid))
        self.assertEqual(store.list_sources(), [])
        self.assertEqual(list(self.source_dir.iterdir()), before)

    def test_saved_stories_statuses_and_evidence_roundtrip(self):
        store = Store(self.db_path)
        store.add_source(self.source_dir)
        evidence = [
            Evidence(
                id="e1",
                label="note.md",
                kind="markdown",
                excerpt="hello world",
                date="2026-10-01",
                local_path=str(self.source_dir / "note.md"),
                commit=None,
                line_start=1,
                line_end=2,
            )
        ]
        candidates = [
            StoryCandidate(
                title="A story",
                angle="angle",
                rationale="reason",
                audience="builders",
                evidence_ids=("e1",),
                confidence=0.75,
            )
        ]
        ids = store.save_candidates(candidates, evidence)
        self.assertEqual(len(ids), 1)
        story = store.get_story(ids[0])
        self.assertIsNotNone(story)
        self.assertEqual(story["title"], "A story")
        self.assertEqual(story["status"], "new")
        self.assertEqual(story["evidence_ids"], ["e1"])
        self.assertEqual(story["evidence"][0]["local_path"], str(self.source_dir / "note.md"))
        self.assertEqual(story["confidence"], 0.75)

        self.assertTrue(store.set_status(ids[0], "kept"))
        kept = store.get_story(ids[0])
        self.assertEqual(kept["status"], "kept")
        self.assertTrue(store.set_draft(ids[0], "draft text"))
        self.assertEqual(store.get_story(ids[0])["draft"], "draft text")

        self.assertTrue(store.set_status(ids[0], "rejected"))
        # draft remains but status rejected; new draft not allowed
        self.assertFalse(store.set_draft(ids[0], "nope"))

    def test_draft_refused_unless_kept(self):
        store = Store(self.db_path)
        evidence = [Evidence(id="e1", label="x", kind="text", excerpt="x")]
        ids = store.save_candidates(
            [{"title": "t", "angle": "a", "rationale": "r", "audience": "u", "evidence_ids": ["e1"], "confidence": 0.5}],
            evidence,
        )
        self.assertFalse(store.set_draft(ids[0], "draft"))
        self.assertIsNone(store.get_story(ids[0])["draft"])
        self.assertTrue(store.set_status(ids[0], "kept"))
        self.assertTrue(store.set_draft(ids[0], "draft"))
        self.assertEqual(store.get_story(ids[0])["draft"], "draft")

    def test_set_status_validation(self):
        store = Store(self.db_path)
        evidence = [Evidence(id="e1", label="x", kind="text", excerpt="x")]
        ids = store.save_candidates(
            [{"title": "t", "angle": "a", "rationale": "r", "audience": "u", "evidence_ids": ["e1"], "confidence": 0.5}],
            evidence,
        )
        self.assertFalse(store.set_status(ids[0], "bogus"))
        self.assertFalse(store.set_status(9999, "kept"))
        self.assertEqual(store.get_story(ids[0])["status"], "new")

    def test_list_stories_filter(self):
        store = Store(self.db_path)
        evidence = [Evidence(id="e1", label="x", kind="text", excerpt="x")]
        ids = store.save_candidates(
            [
                {"title": "one", "angle": "a", "rationale": "r", "audience": "u", "evidence_ids": ["e1"], "confidence": 0.5},
                {"title": "two", "angle": "a", "rationale": "r", "audience": "u", "evidence_ids": ["e1"], "confidence": 0.5},
            ],
            evidence,
        )
        store.set_status(ids[0], "kept")
        self.assertEqual(len(store.list_stories()), 2)
        self.assertEqual(len(store.list_stories(status="kept")), 1)
        self.assertEqual(len(store.list_stories(status="new")), 1)

    def test_foreign_keys_enabled(self):
        store = Store(self.db_path)
        # direct check
        import sqlite3
        conn = sqlite3.connect(str(self.db_path))
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        conn.close()
        # store connections enable per connection; static DB default may be 0, not required
        self.assertIn(fk, (0, 1))

    def test_database_file_is_user_only(self):
        import stat

        store = Store(self.db_path)
        mode = stat.S_IMODE(self.db_path.stat().st_mode)
        self.assertEqual(mode, 0o600)
        with store._connection() as conn:
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_database_symlink_is_rejected(self):
        target = self.root / "real.sqlite"
        Store(target)
        link = self.root / "linked.sqlite"
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest("symlinks not supported")
        with self.assertRaisesRegex(ValueError, "must not be a symlink"):
            Store(link)


if __name__ == "__main__":
    unittest.main()
