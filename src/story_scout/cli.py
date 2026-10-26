"""Command-line interface for Story Scout."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from story_scout import __version__
from story_scout.model import DEFAULT_MODEL, draft_story, suggest_stories
from story_scout.models import Evidence, StoryCandidate
from story_scout.paths import database_path
from story_scout.sources import collect_evidence
from story_scout.store import Store


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="story-scout",
        description="Find evidence-backed story ideas in project folders you choose.",
    )
    parser.add_argument("--db", help=argparse.SUPPRESS)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    source = commands.add_parser("source", help="Manage folders that Story Scout may inspect.")
    source_commands = source.add_subparsers(dest="source_command", required=True)
    add = source_commands.add_parser("add", help="Register an existing folder.")
    add.add_argument("path")
    source_commands.add_parser("list", help="List registered folders.")
    remove = source_commands.add_parser("remove", help="Unregister a folder without deleting it.")
    remove.add_argument("id", type=int)

    scan = commands.add_parser("scan", help="Preview or scan selected project evidence.")
    scan.add_argument("--days", type=int, default=7)
    scan.add_argument(
        "--remote",
        action="store_true",
        help=f"Send the selected evidence excerpts to {DEFAULT_MODEL} for story suggestions.",
    )

    stories = commands.add_parser("stories", help="List saved story candidates.")
    stories.add_argument("--status", choices=("new", "kept", "rejected"))

    keep = commands.add_parser("keep", help="Keep a candidate so it can be drafted.")
    keep.add_argument("id", type=int)
    reject = commands.add_parser("reject", help="Reject a candidate.")
    reject.add_argument("id", type=int)

    draft = commands.add_parser("draft", help="Draft a kept candidate. This does not publish.")
    draft.add_argument("id", type=int)
    draft.add_argument(
        "--remote",
        action="store_true",
        help=f"Send the candidate and its saved evidence to {DEFAULT_MODEL}.",
    )
    return parser


def _store(args: argparse.Namespace) -> Store:
    path = Path(args.db).expanduser() if args.db else database_path()
    return Store(path)


def _print_evidence(evidence: Sequence[Evidence]) -> None:
    if not evidence:
        print("No eligible evidence was found in the selected folders.")
        return
    print(f"Prepared {len(evidence)} evidence item(s):")
    for item in evidence:
        date = f", {item.date}" if item.date else ""
        preview = " ".join(item.excerpt.split())
        if len(preview) > 260:
            preview = preview[:257].rstrip() + "..."
        print(f"\n{item.id}  {item.label}  [{item.kind}{date}]")
        print(f"  {preview}")


def _print_candidate(story_id: int, candidate: StoryCandidate) -> None:
    print(f"\n#{story_id} {candidate.title}")
    print(f"Angle: {candidate.angle}")
    print(f"Why it may matter: {candidate.rationale}")
    print(f"Audience: {candidate.audience}")
    print(f"Confidence: {candidate.confidence:.0%}")
    print("Evidence: " + ", ".join(candidate.evidence_ids))


def _print_saved_story(story: dict) -> None:
    print(f"\n#{story['id']} [{story['status']}] {story['title']}")
    print(f"Angle: {story['angle']}")
    print(f"Why it may matter: {story['rationale']}")
    print(f"Audience: {story['audience']}")
    evidence = story.get("evidence", [])
    labels = [item.get("label", item.get("id", "evidence")) for item in evidence]
    print("Evidence: " + (", ".join(labels) if labels else "none"))
    if story.get("draft"):
        print("\nDraft:\n" + story["draft"])


def _make_candidate(story: dict) -> StoryCandidate:
    evidence = story.get("evidence", [])
    return StoryCandidate(
        title=story["title"],
        angle=story["angle"],
        rationale=story["rationale"],
        audience=story["audience"],
        evidence_ids=tuple(item["id"] for item in evidence),
        confidence=float(story["confidence"]),
    )


def _as_evidence(rows: Sequence[dict]) -> list[Evidence]:
    return [
        Evidence(
            id=row["id"],
            label=row["label"],
            kind=row["kind"],
            excerpt=row["excerpt"],
            date=row.get("date"),
            local_path=row.get("local_path"),
            commit=row.get("commit"),
            line_start=row.get("line_start"),
            line_end=row.get("line_end"),
        )
        for row in rows
    ]


def _run(args: argparse.Namespace) -> int:
    store = _store(args)
    if args.command == "source":
        if args.source_command == "add":
            source_id = store.add_source(Path(args.path).expanduser())
            print(f"Added source #{source_id}: {Path(args.path).expanduser().resolve()}")
            return 0
        if args.source_command == "list":
            rows = store.list_sources()
            if not rows:
                print("No source folders registered. Add one with: story-scout source add PATH")
                return 0
            for row in rows:
                print(f"#{row['id']} {row['path']}")
            return 0
        removed = store.remove_source(args.id)
        if not removed:
            print(f"No registered source with ID {args.id}.", file=sys.stderr)
            return 2
        print(f"Unregistered source #{args.id}. Its folder and files were not changed.")
        return 0

    if args.command == "scan":
        if args.days < 1 or args.days > 365:
            print("--days must be between 1 and 365.", file=sys.stderr)
            return 2
        sources = store.list_sources()
        if not sources:
            print("No source folders registered. Add one with: story-scout source add PATH")
            return 2
        evidence, omissions = collect_evidence(
            [Path(row["path"]) for row in sources],
            days=args.days,
        )
        _print_evidence(evidence)
        for omission in omissions:
            print(f"Skipped: {omission}")
        if not evidence:
            return 0
        if not args.remote:
            print(
                f"\nLocal preview only. Nothing was sent. Re-run with --remote to send these "
                f"selected excerpts to {DEFAULT_MODEL}."
            )
            return 0
        print(
            f"\nSending {len(evidence)} selected excerpt(s) to {DEFAULT_MODEL}. "
            "Only the listed evidence is attached."
        )
        candidates = suggest_stories(evidence, model=DEFAULT_MODEL)
        if not candidates:
            print("The evidence did not support a story worth suggesting.")
            return 0
        ids = store.save_candidates(candidates, evidence)
        for story_id, candidate in zip(ids, candidates, strict=True):
            _print_candidate(story_id, candidate)
        return 0

    if args.command == "stories":
        rows = store.list_stories(status=args.status)
        if not rows:
            print("No matching story candidates.")
            return 0
        for row in rows:
            _print_saved_story(row)
        return 0

    if args.command in ("keep", "reject"):
        status = "kept" if args.command == "keep" else "rejected"
        if not store.set_status(args.id, status):
            print(f"No story candidate with ID {args.id}.", file=sys.stderr)
            return 2
        print(f"Marked story #{args.id} as {status}.")
        return 0

    if args.command == "draft":
        if not args.remote:
            print(
                f"Drafting sends the kept candidate and its evidence to {DEFAULT_MODEL}. "
                "Add --remote to continue.",
                file=sys.stderr,
            )
            return 2
        story = store.get_story(args.id)
        if story is None:
            print(f"No story candidate with ID {args.id}.", file=sys.stderr)
            return 2
        if story["status"] != "kept":
            print(f"Keep story #{args.id} before asking for a draft.", file=sys.stderr)
            return 2
        evidence = _as_evidence(story.get("evidence", []))
        candidate = _make_candidate(story)
        draft = draft_story(candidate, evidence, model=DEFAULT_MODEL)
        if not store.set_draft(args.id, draft):
            print("The draft could not be saved.", file=sys.stderr)
            return 2
        print(draft)
        print("\nDraft saved locally. It has not been published.")
        return 0

    return 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"story-scout: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
