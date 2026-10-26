"""Command-line interface for Tell."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

from story_scout import __version__
from story_scout.capture import collect_conversations, collect_from_export
from story_scout.model import DEFAULT_MODEL, draft_story, suggest_queries, suggest_stories
from story_scout.models import Evidence, StoryCandidate
from story_scout.paths import data_directory, database_path
from story_scout.render import render_inbox
from story_scout.research import collect_research
from story_scout.sources import collect_evidence
from story_scout.store import Store


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="story-scout",
        description="Find evidence-backed story ideas in the work you choose to share.",
    )
    parser.add_argument("--db", help=argparse.SUPPRESS)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    source = commands.add_parser("source", help="Manage folders that Tell may inspect.")
    source_commands = source.add_subparsers(dest="source_command", required=True)
    add = source_commands.add_parser("add", help="Register an existing folder.")
    add.add_argument("path")
    source_commands.add_parser("list", help="List registered folders.")
    remove = source_commands.add_parser("remove", help="Unregister a folder without deleting it.")
    remove.add_argument("id", type=int)

    capture = commands.add_parser(
        "capture",
        help="Preview what Tell reads from agent conversations. Local only.",
    )
    capture.add_argument("--days", type=int, default=7)
    capture.add_argument("--project", action="append", default=[], help="Project folder to read.")
    capture.add_argument("--db", dest="session_db", help="Path to an agent session database.")
    capture.add_argument("--export", help="Path to one exported conversation file.")
    capture.add_argument("--limit", type=int, default=5, help="How many turns to print.")

    scan = commands.add_parser("scan", help="Preview or scan selected work evidence.")
    scan.add_argument("--days", type=int, default=7)
    scan.add_argument("--remote", action="store_true", help=f"Send selected excerpts to {DEFAULT_MODEL}.")
    scan.add_argument(
        "--no-agents",
        action="store_true",
        help="Skip agent conversations and read only files and Git metadata.",
    )

    inbox = commands.add_parser("inbox", help="Render the local HTML inbox from saved ideas.")
    inbox.add_argument("--out", help="Output path for the HTML file.")
    inbox.add_argument("--status", choices=("new", "kept", "rejected"), default=None)

    stories = commands.add_parser("stories", help="List saved story candidates.")
    stories.add_argument("--status", choices=("new", "kept", "rejected"))

    keep = commands.add_parser("keep", help="Keep a candidate so it can be drafted.")
    keep.add_argument("id", type=int)
    reject = commands.add_parser("reject", help="Reject a candidate.")
    reject.add_argument("id", type=int)

    draft = commands.add_parser("draft", help="Draft a kept candidate. This does not publish.")
    draft.add_argument("id", type=int)
    draft.add_argument("--remote", action="store_true", help=f"Send the candidate and its saved evidence to {DEFAULT_MODEL}.")
    return parser


def _store(args: argparse.Namespace) -> Store:
    path = Path(args.db).expanduser() if getattr(args, "db", None) else database_path()
    return Store(path)


def _print_evidence(evidence: Sequence[Evidence]) -> None:
    if not evidence:
        print("No eligible evidence was found in the selected work.")
        return
    print(f"Prepared {len(evidence)} evidence item(s):")
    for item in evidence:
        date = f", {item.date}" if item.date else ""
        url = f" {item.url}" if item.url else ""
        preview = " ".join(item.excerpt.split())
        if len(preview) > 200:
            preview = preview[:197].rstrip() + "..."
        print(f"\n{item.id}  {item.label}  [{item.kind}/{item.source}{date}]{url}")
        print(f"  {preview}")


def _print_candidate(story_id: int, candidate: StoryCandidate) -> None:
    print(f"\n#{story_id} {candidate.title}")
    print(f"Angle: {candidate.angle}")
    print(f"Why it may matter: {candidate.rationale}")
    if candidate.fact:
        print(f"Fact: {candidate.fact}")
    if candidate.interpretation:
        print(f"Interpretation: {candidate.interpretation}")
    print(f"Audience: {candidate.audience}")
    print(f"Confidence: {candidate.confidence:.0%}")
    if candidate.research_urls:
        print("Research: " + ", ".join(candidate.research_urls))
    print("Evidence: " + ", ".join(candidate.evidence_ids))


def _print_saved_story(story: dict) -> None:
    print(f"\n#{story['id']} [{story['status']}] {story['title']}")
    print(f"Angle: {story['angle']}")
    print(f"Why it may matter: {story['rationale']}")
    if story.get("fact"):
        print(f"Fact: {story['fact']}")
    if story.get("interpretation"):
        print(f"Interpretation: {story['interpretation']}")
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
        fact=story.get("fact") or "",
        interpretation=story.get("interpretation") or "",
        research_urls=tuple(story.get("research_urls") or ()),
        channel_x=story.get("channel_x") or "",
        channel_linkedin=story.get("channel_linkedin") or "",
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
            source=row.get("source") or "file",
            url=row.get("url"),
        )
        for row in rows
    ]


def _ideas_from_store(store: Store, status: str | None = None) -> list[dict]:
    ideas = []
    for story in store.list_stories(status=status):
        candidate = _make_candidate(story)
        idea = candidate.as_idea()
        idea["id"] = story["id"]
        idea["status"] = story["status"]
        ideas.append(idea)
    return ideas


def _render(store: Store, out: str | None = None, status: str | None = None) -> Path:
    target = Path(out).expanduser() if out else data_directory() / "inbox.html"
    ideas = _ideas_from_store(store, status=status)
    return render_inbox(
        ideas,
        target,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        title="Tell",
    )


def _registered_projects(store: Store) -> list[Path]:
    return [Path(row["path"]) for row in store.list_sources()]


def _run_capture(args: argparse.Namespace, store: Store) -> int:
    if args.days < 1 or args.days > 365:
        print("--days must be between 1 and 365.", file=sys.stderr)
        return 2
    if args.export:
        evidence, omissions = collect_from_export(args.export)
    else:
        projects = [Path(path).expanduser() for path in args.project] or _registered_projects(store)
        if not projects:
            print("No project folders registered. Add one with: story-scout source add PATH", file=sys.stderr)
            return 2
        evidence, omissions = collect_conversations(projects, days=args.days, db_path=args.session_db)
    print(f"Captured {len(evidence)} conversation turn(s) locally. Nothing was sent.")
    for item in evidence[: max(1, args.limit)]:
        preview = " ".join(item.excerpt.split())
        if len(preview) > 240:
            preview = preview[:237].rstrip() + "..."
        print(f"\n{item.id}  {item.label}  [{item.date or 'no date'}]")
        print(f"  {preview}")
    if len(evidence) > args.limit:
        print(f"\n... {len(evidence) - args.limit} more turn(s) not shown.")
    for omission in omissions:
        print(f"Skipped: {omission}")
    return 0


def _run_scan(args: argparse.Namespace, store: Store) -> int:
    if args.days < 1 or args.days > 365:
        print("--days must be between 1 and 365.", file=sys.stderr)
        return 2
    projects = _registered_projects(store)
    if not projects:
        print("No source folders registered. Add one with: story-scout source add PATH", file=sys.stderr)
        return 2

    evidence, omissions = collect_evidence(projects, days=args.days)
    if not args.no_agents:
        agent_evidence, agent_omissions = collect_conversations(projects, days=args.days)
        evidence.extend(agent_evidence)
        omissions.extend(agent_omissions)
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

    print(f"\nChoosing research directions with {DEFAULT_MODEL}.")
    queries = suggest_queries(evidence, model=DEFAULT_MODEL)
    for query in queries:
        print(f"  query: {query}")
    research_evidence: list[Evidence] = []
    if queries:
        print(f"Fetching sources for {len(queries)} query(ies).")
        research_evidence, research_omissions = collect_research(queries)
        omissions.extend(research_omissions)
        for item in research_evidence:
            print(f"  source: {item.url}")
        if not research_evidence:
            print("No source could be fetched. Suggestions will carry no citations.")

    print(
        f"\nSending {len(evidence)} work excerpt(s) and {len(research_evidence)} fetched "
        f"source(s) to {DEFAULT_MODEL}."
    )
    warnings: list[str] = []
    candidates = suggest_stories(
        evidence,
        research_evidence,
        model=DEFAULT_MODEL,
        warnings=warnings,
    )
    for warning in warnings:
        print(f"Dropped: {warning}")
    if not candidates:
        print("The evidence did not support a story worth suggesting.")
        return 0
    ids = store.save_candidates(candidates, list(evidence) + list(research_evidence))
    for story_id, candidate in zip(ids, candidates, strict=True):
        _print_candidate(story_id, candidate)
    inbox_path = _render(store)
    print(f"\nInbox: {inbox_path}")
    return 0


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

    if args.command == "capture":
        return _run_capture(args, store)

    if args.command == "scan":
        return _run_scan(args, store)

    if args.command == "inbox":
        path = _render(store, out=args.out, status=args.status)
        print(f"Inbox: {path}")
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
