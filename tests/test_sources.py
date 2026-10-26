import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from story_scout.models import Evidence
from story_scout.sources import collect_evidence


class TestSources(unittest.TestCase):
    def test_recent_text_inclusion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "note.md").write_text("hello story\nsecond line\n")
            (root / "info.txt").write_text("plain text")
            evidence, omissions = collect_evidence([root], days=7)
            kinds = {e.kind for e in evidence}
            self.assertIn("markdown", kinds)
            self.assertTrue(any("hello story" in e.excerpt for e in evidence))
            # line numbers
            md = [e for e in evidence if e.label == "note.md"][0]
            self.assertEqual(md.line_start, 1)
            self.assertEqual(md.line_end, 2)
            self.assertTrue(all(isinstance(e, Evidence) for e in evidence))

    def test_source_code_exclusion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "main.py").write_text("print('secret')")
            (root / "app.js").write_text("console.log('x')")
            (root / "readme.md").write_text("docs")
            evidence, omissions = collect_evidence([root], days=7)
            labels = {e.label for e in evidence}
            self.assertNotIn("main.py", labels)
            self.assertNotIn("app.js", labels)
            self.assertIn("readme.md", labels)

    def test_hidden_and_credential_exclusion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            hidden_dir = root / ".hidden"
            hidden_dir.mkdir()
            (hidden_dir / "note.md").write_text("hidden")
            (root / ".secret.md").write_text("hidden file")
            (root / "credentials.md").write_text("creds")
            (root / "secret.txt").write_text("shh")
            (root / "token.md").write_text("tok")
            (root / "password.txt").write_text("pw")
            (root / "private-key.pem.txt").write_text("pk")  # extension txt but unsafe name
            (root / "oauth.md").write_text("oauth")
            (root / "normal.md").write_text("ok")
            (root / ".env").write_text("ENV=1")
            evidence, omissions = collect_evidence([root], days=7)
            labels = {e.label for e in evidence}
            self.assertEqual(labels, {"normal.md"})
            self.assertTrue(any("unsafe" in o or "symlink" in o for o in omissions) or len(omissions) >= 1)

    def test_symlink_escape_exclusion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "root"
            outside = Path(td) / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "escape.md").write_text("escaped")
            target = outside / "escape.md"
            link = root / "escape.md"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlinks not supported")
            evidence, omissions = collect_evidence([root], days=7)
            labels = {e.label for e in evidence}
            self.assertNotIn("escape.md", labels)
            # symlink omission expected if supported
            # (not strictly required)

    def test_git_metadata_without_code_contents(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
            (root / "README.md").write_text("hi")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "initial commit"], cwd=root, check=True)
            (root / "notes.txt").write_text("note")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "add notes"], cwd=root, check=True)
            evidence, omissions = collect_evidence([root], days=7)
            git_ev = [e for e in evidence if e.kind == "git_commit"]
            self.assertGreaterEqual(len(git_ev), 2)
            # code contents not present
            for e in git_ev:
                self.assertNotIn("print(", e.excerpt)
            # changed relative filenames present
            joined = "\n".join(e.excerpt for e in git_ev)
            self.assertIn("notes.txt", joined)
            # unique ids
            ids = [e.id for e in evidence]
            self.assertEqual(len(ids), len(set(ids)))
            # local_path absolute
            self.assertTrue(all(e.local_path and Path(e.local_path).is_absolute() for e in git_ev))

    def test_non_git_folder_no_fail(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.md").write_text("x")
            evidence, omissions = collect_evidence([root], days=7)
            self.assertTrue(any(e.label == "a.md" for e in evidence))

    def test_missing_path_raises(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            missing = root / "nope"
            with self.assertRaises(ValueError):
                collect_evidence([missing])

    def test_non_directory_raises(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "file.txt"
            f.write_text("x")
            with self.assertRaises(ValueError):
                collect_evidence([f])

    def test_bounds(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # 45 text files
            for i in range(45):
                (root / f"f{i}.txt").write_text("a" * 100)
            evidence, omissions = collect_evidence([root], days=7)
            text_ev = [e for e in evidence if e.kind == "text"]
            self.assertLessEqual(len(text_ev), 40)
            self.assertTrue(any("text file limit" in o for o in omissions))

    def test_large_file_truncation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "big.md").write_text("b" * 20000)
            evidence, omissions = collect_evidence([root], days=7)
            self.assertEqual(len(evidence), 1)
            self.assertLessEqual(len(evidence[0].excerpt), 12000)
            self.assertTrue(any("file limit" in o for o in omissions))

    def test_labels_relative(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sub = root / "sub"
            sub.mkdir()
            (sub / "x.md").write_text("x")
            evidence, omissions = collect_evidence([root], days=7)
            for e in evidence:
                if e.kind != "git_commit":
                    self.assertFalse(Path(e.label).is_absolute())

    def test_determinism(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.md").write_text("a")
            (root / "b.md").write_text("b")
            e1, o1 = collect_evidence([root], days=7)
            e2, o2 = collect_evidence([root], days=7)
            self.assertEqual([e.id for e in e1], [e.id for e in e2])
            self.assertEqual([e.excerpt for e in e1], [e.excerpt for e in e2])

    def test_recent_files_win_when_text_file_limit_is_reached(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            now = datetime.now()
            old_time = now.timestamp() - 3600
            for i in range(45):
                path = root / f"note-{i:02d}.md"
                path.write_text(f"old {i}", encoding="utf-8")
                os.utime(path, (old_time, old_time))
            newest = root / "z-most-recent.md"
            newest.write_text("the newest note", encoding="utf-8")
            evidence, omissions = collect_evidence([root], days=7, now=now)
            labels = {item.label for item in evidence}
            self.assertIn("z-most-recent.md", labels)
            self.assertLessEqual(sum(item.kind != "git_commit" for item in evidence), 40)

    def test_total_character_limit_covers_all_text_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for i in range(6):
                (root / f"note-{i}.md").write_text("x" * 12000, encoding="utf-8")
            evidence, omissions = collect_evidence([root], days=7)
            total = sum(len(item.excerpt) for item in evidence if item.kind != "git_commit")
            self.assertEqual(total, 60000)
            self.assertTrue(any("total character limit" in note for note in omissions))

    def test_git_metadata_omits_hidden_and_credential_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
            (root / ".env").write_text("KEY=x", encoding="utf-8")
            (root / "credentials.txt").write_text("secret", encoding="utf-8")
            (root / "notes.md").write_text("safe note", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "update files"], cwd=root, check=True)
            evidence, omissions = collect_evidence([root], days=7)
            excerpts = "\n".join(item.excerpt for item in evidence)
            self.assertNotIn(".env", excerpts)
            self.assertNotIn("credentials.txt", excerpts)


if __name__ == "__main__":
    unittest.main()
