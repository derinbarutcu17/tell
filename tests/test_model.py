from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from story_scout.model import DEFAULT_MODEL, draft_story, suggest_stories
from story_scout.models import Evidence, StoryCandidate


def _text_event(text: str) -> str:
    return json.dumps({"type": "text", "part": {"type": "text", "text": text}})


class ModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evidence = [
            Evidence(
                id="e1",
                label="notes.md",
                kind="markdown",
                excerpt="A user test revealed the same onboarding problem three times.",
                local_path="/private/path/notes.md",
            ),
            Evidence(
                id="e2",
                label="commit:abc1234",
                kind="git_commit",
                excerpt="Simplify onboarding",
                local_path="/private/repo",
            ),
        ]

    def test_suggest_sends_public_evidence_and_validates_response(self) -> None:
        response = {
            "candidates": [
                {
                    "title": "Three users found the same onboarding wall",
                    "angle": "Repeated friction changed the design.",
                    "rationale": "The notes record the same issue in three tests.",
                    "audience": "Product designers",
                    "evidence_ids": ["e1"],
                    "confidence": 0.8,
                }
            ]
        }
        attached: list[Path] = []

        def fake_run(command, **kwargs):
            path = Path(command[command.index("--file") + 1])
            attached.append(path)
            packet = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual([item["id"] for item in packet["work_evidence"]], ["e1", "e2"])
            self.assertNotIn("research_evidence", packet)
            self.assertTrue(all("local_path" not in item for item in packet["work_evidence"]))
            self.assertEqual(command[command.index("--model") + 1], DEFAULT_MODEL)
            self.assertEqual(command[command.index("--agent") + 1], "story-scout")
            return SimpleNamespace(returncode=0, stdout=_text_event(json.dumps(response)), stderr="")

        with patch("story_scout.model.subprocess.run", side_effect=fake_run):
            candidates = suggest_stories(self.evidence)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].evidence_ids, ("e1",))
        self.assertFalse(attached[0].exists())

    def test_empty_evidence_skips_model(self) -> None:
        with patch("story_scout.model.subprocess.run") as run:
            self.assertEqual(suggest_stories([]), [])
        run.assert_not_called()

    def test_unrecognized_evidence_id_is_rejected(self) -> None:
        response = {
            "candidates": [
                {
                    "title": "A claim",
                    "angle": "Angle",
                    "rationale": "Reason",
                    "audience": "People",
                    "evidence_ids": ["not-in-packet"],
                    "confidence": 0.5,
                }
            ]
        }
        with patch(
            "story_scout.model.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout=_text_event(json.dumps(response)), stderr=""),
        ):
            with self.assertRaisesRegex(ValueError, "evidence ID"):
                suggest_stories(self.evidence)

    def test_invalid_json_is_rejected(self) -> None:
        with patch(
            "story_scout.model.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout=_text_event("not JSON"), stderr=""),
        ):
            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                suggest_stories(self.evidence)

    def test_nonzero_exit_does_not_echo_credentials_or_payload(self) -> None:
        with patch(
            "story_scout.model.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stdout="private payload", stderr="secret token"),
        ):
            with self.assertRaises(RuntimeError) as raised:
                suggest_stories(self.evidence)
        self.assertNotIn("private payload", str(raised.exception))
        self.assertNotIn("secret token", str(raised.exception))

    def test_go_auth_error_has_clear_reauth_guidance(self) -> None:
        payload = {
            "type": "error",
            "error": {"type": "provider.auth", "message": "This API key can't call models", "status": 403},
        }
        with patch(
            "story_scout.model.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stdout=json.dumps(payload), stderr=""),
        ):
            with self.assertRaisesRegex(RuntimeError, "Reconnect the Go provider"):
                suggest_stories(self.evidence)

    def test_free_tier_restriction_has_clear_cli_guidance(self) -> None:
        payload = {
            "type": "error",
            "error": {
                "type": "provider.auth",
                "message": "OpenCode's free tier can only be used from within OpenCode.",
                "status": 403,
            },
        }
        with patch(
            "story_scout.model.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stdout=json.dumps(payload), stderr=""),
        ):
            with self.assertRaisesRegex(RuntimeError, "only works inside the OpenCode app"):
                suggest_stories(self.evidence)

    def test_paid_model_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "pinned to the free model"):
            suggest_stories(self.evidence, model="opencode-go/gpt-6-luna")

    def test_both_free_models_are_accepted(self) -> None:
        response = {
            "candidates": [
                {
                    "title": "A free model story",
                    "angle": "Angle",
                    "rationale": "Reason",
                    "audience": "People",
                    "evidence_ids": ["e1"],
                    "confidence": 0.4,
                }
            ]
        }
        for model in ("opencode/deepseek-v4.1-flash-free", "opencode-go/beam-free"):
            with patch(
                "story_scout.model.subprocess.run",
                return_value=SimpleNamespace(
                    returncode=0, stdout=_text_event(json.dumps(response)), stderr=""
                ),
            ) as run:
                candidates = suggest_stories(self.evidence, model=model)
            self.assertEqual(len(candidates), 1)
            self.assertEqual(run.call_args.kwargs["timeout"], 240)
            command = run.call_args.args[0]
            self.assertEqual(command[command.index("--model") + 1], model)

    def test_model_supplied_citations_are_ignored(self) -> None:
        response = {
            "candidates": [
                {
                    "title": "Fabricated citation",
                    "angle": "Angle",
                    "rationale": "Reason",
                    "audience": "People",
                    "evidence_ids": ["e1"],
                    "research_query": "citation provenance",
                    "research_urls": ["https://example.com/invented"],
                    "confidence": 0.5,
                }
            ]
        }
        warnings: list[str] = []
        with patch(
            "story_scout.model.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout=_text_event(json.dumps(response)), stderr=""),
        ):
            candidates = suggest_stories(self.evidence, warnings=warnings)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].research_urls, ())
        self.assertEqual(candidates[0].research_query, "citation provenance")
        self.assertTrue(any("ignored" in warning for warning in warnings))

    def test_research_query_is_optional(self) -> None:
        response = {
            "candidates": [
                {
                    "title": "No query idea",
                    "angle": "Angle",
                    "rationale": "Reason",
                    "audience": "People",
                    "evidence_ids": ["e1"],
                    "confidence": 0.5,
                }
            ]
        }
        with patch(
            "story_scout.model.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout=_text_event(json.dumps(response)), stderr=""),
        ):
            candidates = suggest_stories(self.evidence)
        self.assertEqual(candidates[0].research_query, "")

    def test_draft_receives_only_selected_evidence(self) -> None:
        candidate = StoryCandidate(
            title="Keep the observed friction",
            angle="Repeated user confusion led to a design change.",
            rationale="The note records the tests.",
            audience="Product designers",
            evidence_ids=("e1",),
            confidence=0.8,
        )
        attached: list[Path] = []

        def fake_run(command, **kwargs):
            path = Path(command[command.index("--file") + 1])
            attached.append(path)
            packet = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual([item["id"] for item in packet["evidence"]], ["e1"])
            self.assertNotIn("local_path", packet["evidence"][0])
            return SimpleNamespace(returncode=0, stdout=_text_event("We redesigned the step after seeing the same confusion in three tests."), stderr="")

        with patch("story_scout.model.subprocess.run", side_effect=fake_run):
            draft = draft_story(candidate, self.evidence)
        self.assertIn("three tests", draft)
        self.assertFalse(attached[0].exists())

    def test_draft_rejects_missing_evidence(self) -> None:
        candidate = StoryCandidate(
            title="A story",
            angle="Angle",
            rationale="Reason",
            audience="People",
            evidence_ids=("missing",),
            confidence=0.5,
        )
        with self.assertRaisesRegex(ValueError, "evidence is missing"):
            draft_story(candidate, self.evidence)


if __name__ == "__main__":
    unittest.main()
