from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from story_scout.cli import main
from story_scout.models import Evidence, StoryCandidate
from story_scout.store import Store


class CliPrivacyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "project"
        self.source.mkdir()
        (self.source / "notes.md").write_text(
            "I changed the onboarding flow after watching three people get stuck.",
            encoding="utf-8",
        )
        self.db = self.root / "story-scout.sqlite"

    def call_cli(self, *args: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = main(["--db", str(self.db), *args])
        return result, out.getvalue(), err.getvalue()

    def register_source(self) -> None:
        result, _, err = self.call_cli("source", "add", str(self.source))
        self.assertEqual(result, 0, err)

    def test_preview_does_not_call_model(self) -> None:
        self.register_source()
        with patch("story_scout.cli.suggest_stories") as suggest:
            result, out, err = self.call_cli("scan", "--days", "7")
        self.assertEqual(result, 0, err)
        self.assertIn("Local preview only", out)
        self.assertIn("Nothing was sent", out)
        suggest.assert_not_called()

    def test_remote_scan_stores_candidates_then_draft_requires_keep(self) -> None:
        self.register_source()
        evidence = Evidence(
            id="e1",
            label="notes.md",
            kind="markdown",
            excerpt="I changed the onboarding flow after watching three people get stuck.",
            local_path=str(self.source / "notes.md"),
        )
        candidate = StoryCandidate(
            title="Three people hit the same onboarding wall",
            angle="How observing a repeated stumble changed the flow",
            rationale="It turns a small design iteration into a concrete lesson.",
            audience="Product designers",
            evidence_ids=("e1",),
            confidence=0.82,
        )
        with patch("story_scout.cli.collect_evidence", return_value=([evidence], [])):
            with patch("story_scout.cli.suggest_stories", return_value=[candidate]) as suggest:
                result, out, err = self.call_cli("scan", "--remote")
        self.assertEqual(result, 0, err)
        self.assertIn("Sending 1 selected excerpt", out)
        suggest.assert_called_once()

        store = Store(self.db)
        stories = store.list_stories()
        self.assertEqual(len(stories), 1)
        story_id = stories[0]["id"]

        with patch("story_scout.cli.draft_story") as draft:
            result, _, err = self.call_cli("draft", str(story_id))
        self.assertEqual(result, 2)
        self.assertIn("Add --remote", err)
        draft.assert_not_called()

        result, _, err = self.call_cli("keep", str(story_id))
        self.assertEqual(result, 0, err)
        with patch("story_scout.cli.draft_story", return_value="A short evidence-led draft.") as draft:
            result, out, err = self.call_cli("draft", str(story_id), "--remote")
        self.assertEqual(result, 0, err)
        self.assertIn("has not been published", out)
        draft.assert_called_once()
        self.assertEqual(Store(self.db).get_story(story_id)["draft"], "A short evidence-led draft.")


if __name__ == "__main__":
    unittest.main()
