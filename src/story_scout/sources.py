"""Collect local evidence from explicitly registered source folders."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from story_scout.models import Evidence
from story_scout.redact import redact

TEXT_EXTENSIONS = {".md", ".txt", ".rst"}
PER_FILE_LIMIT = 12_000
TOTAL_LIMIT = 60_000
MAX_TEXT_FILES = 40

UNSAFE_TOKENS = (
    "credential",
    "secret",
    "token",
    "password",
    "private-key",
    "private_key",
    "privatekey",
    "api-key",
    "api_key",
    "apikey",
    "oauth",
)
MAX_GIT_COMMITS = 50
MAX_GIT_PATHS = 20
MAX_GIT_SUBJECT_CHARS = 500


def collect_evidence(source_paths, *, days=7, now=None):
    if isinstance(source_paths, (str, Path, os.PathLike)):
        source_paths = [source_paths]
    paths = list(source_paths)
    for sp in paths:
        p = Path(sp)
        if not p.exists():
            raise ValueError(f"source path does not exist: {sp}")
        if not p.is_dir():
            raise ValueError(f"source path is not a directory: {sp}")

    base_now = now if now is not None else datetime.now()
    threshold = base_now - timedelta(days=days)

    evidence = []
    omissions = []
    seen_ids = set()

    def unique_id(candidate):
        if candidate not in seen_ids:
            seen_ids.add(candidate)
            return candidate
        i = 2
        while f"{candidate}-{i}" in seen_ids:
            i += 1
        final = f"{candidate}-{i}"
        seen_ids.add(final)
        return final

    # Git metadata per source path.
    total_chars = 0
    git_count = 0
    for sp in paths:
        if git_count >= MAX_GIT_COMMITS:
            omissions.append(f"omitted additional Git commits: commit limit ({MAX_GIT_COMMITS})")
            break
        root = Path(sp).resolve()
        try:
            inside = subprocess.run(
                ["git", "--no-pager", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            inside = None
        if inside is None or inside.returncode != 0 or inside.stdout.strip() != "true":
            continue
        try:
            toplevel_out = subprocess.run(
                ["git", "--no-pager", "-C", str(root), "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            )
            toplevel = Path(toplevel_out.stdout.strip()).resolve()
            try:
                rel_prefix = root.relative_to(toplevel).as_posix()
            except ValueError:
                rel_prefix = ""
            if rel_prefix == ".":
                rel_prefix = ""
        except (subprocess.SubprocessError, OSError):
            continue

        since_arg = threshold.isoformat()
        try:
            log_out = subprocess.run(
                [
                    "git",
                    "--no-pager",
                    "-C",
                    str(root),
                    "log",
                    f"--since={since_arg}",
                    f"--max-count={MAX_GIT_COMMITS + 1}",
                    "--format=%H%x1f%ad%x1f%s",
                    "--date=short",
                    "--",
                    ".",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        except (subprocess.SubprocessError, OSError):
            continue

        for line in log_out.stdout.splitlines():
            if git_count >= MAX_GIT_COMMITS:
                omissions.append(f"omitted additional Git commits: commit limit ({MAX_GIT_COMMITS})")
                break
            line = line.strip()
            if not line:
                continue
            parts = line.split("\x1f")
            if len(parts) < 3:
                continue
            full_hash, date_str, subject = parts[0], parts[1], parts[2]
            subject = subject[:MAX_GIT_SUBJECT_CHARS]
            short_hash = full_hash[:7]
            if _unsafe_name(subject):
                omissions.append(f"omitted Git commit {short_hash}: credential-like subject")
                continue
            try:
                diff_out = subprocess.run(
                    [
                        "git",
                        "--no-pager",
                        "-C",
                        str(root),
                        "diff-tree",
                        "--no-commit-id",
                        "--name-only",
                        "-r",
                        "--root",
                        full_hash,
                        "--",
                        ".",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                changed = []
                truncated_paths = False
                for f in diff_out.stdout.splitlines():
                    f = f.strip()
                    if not f:
                        continue
                    if rel_prefix and f.startswith(rel_prefix + "/"):
                        f = f[len(rel_prefix) + 1:]
                    parts = Path(f).parts
                    if any(part.startswith(".") or _unsafe_name(part) for part in parts):
                        continue
                    if len(changed) >= MAX_GIT_PATHS:
                        truncated_paths = True
                        break
                    changed.append(f[:300])
                if truncated_paths:
                    omissions.append(
                        f"truncated changed paths for commit {short_hash}: "
                        f"path limit ({MAX_GIT_PATHS})"
                    )
            except (subprocess.SubprocessError, OSError):
                changed = []
            excerpt_lines = [subject]
            if changed:
                excerpt_lines.append("changed files:")
                excerpt_lines.extend(changed)
            excerpt = redact("\n".join(excerpt_lines))
            budget = TOTAL_LIMIT - total_chars
            if budget <= 0:
                omissions.append(f"omitted additional Git evidence: total character limit ({TOTAL_LIMIT})")
                break
            if len(excerpt) > budget:
                excerpt = excerpt[:budget]
                omissions.append(f"truncated Git evidence {short_hash}: total character limit ({TOTAL_LIMIT})")
            eid = unique_id(f"git:{short_hash}")
            evidence.append(
                Evidence(
                    id=eid,
                    label=short_hash,
                    kind="git_commit",
                    excerpt=excerpt,
                    date=date_str or None,
                    local_path=str(toplevel),
                    commit=short_hash,
                    line_start=None,
                    line_end=None,
                )
            )
            total_chars += len(excerpt)
            git_count += 1

    # Text files.
    all_text_files = []
    for sp in paths:
        root = Path(sp).resolve()
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            pruned = []
            for d in dirnames:
                full = Path(dirpath) / d
                if d.startswith("."):
                    continue
                if full.is_symlink():
                    rel = _relative_or_str(full, root)
                    omissions.append(f"omitted symlink: {rel}")
                    continue
                if _unsafe_name(d):
                    rel = _relative_or_str(full, root)
                    omissions.append(f"omitted unsafe path: {rel}")
                    continue
                pruned.append(d)
            dirnames[:] = sorted(pruned)
            for name in sorted(filenames):
                full = Path(dirpath) / name
                if name.startswith("."):
                    continue
                if full.is_symlink():
                    if full.suffix.lower() in TEXT_EXTENSIONS:
                        rel = _relative_or_str(full, root)
                        omissions.append(f"omitted symlink: {rel}")
                    continue
                if not full.is_file():
                    continue
                if full.suffix.lower() not in TEXT_EXTENSIONS:
                    continue
                if _unsafe_name(name):
                    rel = _relative_or_str(full, root)
                    omissions.append(f"omitted unsafe path: {rel}")
                    continue
                all_text_files.append(full)

    try:
        threshold_ts = threshold.timestamp()
    except (AttributeError, OSError, ValueError):
        threshold_ts = datetime(threshold.year, threshold.month, threshold.day).timestamp()
    recent_files = []
    for full in all_text_files:
        try:
            mtime = full.stat().st_mtime
        except OSError:
            omissions.append(f"could not stat {_relative_or_str(full, _owning_root(full, paths))}: permission denied")
            continue
        if mtime >= threshold_ts:
            recent_files.append((mtime, full))
    recent_files.sort(key=lambda item: (-item[0], str(item[1])))

    files_read = 0
    for idx, (mtime, full) in enumerate(recent_files):
        if files_read >= MAX_TEXT_FILES:
            remaining = len(recent_files) - idx
            omissions.append(f"omitted {remaining} text files: text file limit ({MAX_TEXT_FILES})")
            break
        if total_chars >= TOTAL_LIMIT:
            remaining = len(recent_files) - idx
            omissions.append(f"omitted {remaining} text files: total character limit ({TOTAL_LIMIT})")
            break

        root = _owning_root(full, paths)
        rel = _relative_or_str(full, root)

        try:
            with full.open("rb") as f:
                raw = f.read(PER_FILE_LIMIT + 1)
        except OSError as e:
            omissions.append(f"could not read {rel}: {e}")
            continue
        truncated_file = len(raw) > PER_FILE_LIMIT
        raw = raw[:PER_FILE_LIMIT]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")

        if truncated_file:
            omissions.append(f"truncated {rel}: file limit ({PER_FILE_LIMIT})")

        if total_chars + len(text) > TOTAL_LIMIT:
            budget = TOTAL_LIMIT - total_chars
            if budget <= 0:
                remaining = len(all_text_files) - idx
                omissions.append(f"omitted {remaining} text files: total character limit ({TOTAL_LIMIT})")
                break
            text = text[:budget]
            omissions.append(f"truncated {rel}: total character limit ({TOTAL_LIMIT})")

        if text == "":
            line_start = None
            line_end = None
        else:
            lines = text.splitlines()
            line_start = 1
            line_end = len(lines) if lines else 1

        suffix = full.suffix.lower()
        if suffix == ".md":
            kind = "markdown"
        else:
            kind = "text"

        eid = unique_id(f"text:{rel}")
        evidence.append(
            Evidence(
                id=eid,
                label=rel,
                kind=kind,
                excerpt=redact(text),
                date=None,
                local_path=str(full),
                commit=None,
                line_start=line_start,
                line_end=line_end,
            )
        )
        total_chars += len(text)
        files_read += 1

    return evidence, omissions


def _unsafe_name(name):
    lower = name.lower()
    if lower == ".env" or lower.startswith(".env."):
        return True
    return any(tok in lower for tok in UNSAFE_TOKENS)


def _relative_or_str(path, root):
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _owning_root(full, paths):
    for sp in paths:
        root = Path(sp).resolve()
        try:
            full.relative_to(root)
            return root
        except ValueError:
            continue
    return full.parent
