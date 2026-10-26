from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


FAKE_OPENCODE = r'''#!@PYTHON@
import json
import os
import sys

args = sys.argv[1:]
payload_path = args[args.index("--file") + 1]
with open(payload_path, encoding="utf-8") as stream:
    payload = json.load(stream)
work = payload.get("work_evidence") or payload.get("evidence") or []
research = payload.get("research_evidence") or []
if not work or any("local_path" in item for item in work):
    raise SystemExit("unexpected evidence payload")
if any(os.path.isabs(item.get("label", "")) for item in work):
    raise SystemExit("absolute path in evidence payload")
with open(os.environ["STORY_SCOUT_E2E_LOG"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps({"payload_path": payload_path}) + "\n")

prompt = args[-1]
if "short web search queries" in prompt:
    response = json.dumps({"queries": []})
elif "Draft one concise social post" in prompt:
    response = "A small UX change taught me to reduce the first decision."
else:
    response = json.dumps({"candidates": [{
        "title": "Reduce the first decision",
        "angle": "A user got stuck, so the first-run flow was simplified.",
        "rationale": "The note records a concrete friction and product change.",
        "audience": "People designing onboarding",
        "fact": "The user got stuck and the flow now asks for one choice at a time.",
        "interpretation": "Fewer first decisions may reduce drop-off.",
        "evidence_ids": [work[0]["id"]],
        "research_urls": [],
        "channel_x": "One choice at a time beat four.",
        "channel_linkedin": "A new user got stuck, so we cut the first-run flow to one decision.",
        "confidence": 0.82,
    }]})
print(json.dumps({"type": "text", "part": {"text": response}}))
'''


class CliEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="story-scout-e2e-")
        self.root = Path(self.temp.name)
        self.source = self.root / "synthetic-project"
        self.source.mkdir()
        (self.source / "notes.md").write_text(
            "# A product decision\n"
            "I simplified the first-run flow after a new user got stuck. "
            "The project now asks for one choice at a time.\n",
            encoding="utf-8",
        )
        self.db = self.root / "story-scout.sqlite"
        self.call_log = self.root / "model-calls.jsonl"
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        fake_cli = fake_bin / "opencode"
        fake_cli.write_text(FAKE_OPENCODE.replace("@PYTHON@", sys.executable), encoding="utf-8")
        fake_cli.chmod(0o755)
        self.env = os.environ.copy()
        self.env["PATH"] = os.pathsep.join((str(fake_bin), self.env.get("PATH", "")))
        self.env["PYTHONPATH"] = os.pathsep.join(
            (str(ROOT / "src"), self.env.get("PYTHONPATH", ""))
        )
        self.env["STORY_SCOUT_E2E_LOG"] = str(self.call_log)
        self.env["STORY_SCOUT_DATA_DIR"] = str(self.root / "data")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "story_scout", "--db", str(self.db), *args],
            cwd=ROOT,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def require_success(self, *args: str) -> str:
        result = self.run_cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_preview_review_and_draft_flow_with_local_model_stub(self) -> None:
        self.require_success("source", "add", str(self.source))

        preview = self.require_success("scan", "--days", "7")
        self.assertIn("Nothing was sent", preview)
        self.assertFalse(self.call_log.exists(), "local preview must not invoke OpenCode")

        candidates = self.require_success("scan", "--days", "7", "--remote")
        self.assertIn("Reduce the first decision", candidates)
        stories = self.require_success("stories")
        self.assertIn("Reduce the first decision", stories)
        self.require_success("keep", "1")

        draft = self.require_success("draft", "1", "--remote")
        self.assertIn("A small UX change", draft)
        self.assertIn("Draft saved locally", draft)

        calls = [json.loads(line) for line in self.call_log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(not Path(call["payload_path"]).exists() for call in calls))


if __name__ == "__main__":
    unittest.main()
