"""One scan pipeline, shared by the command line and the dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from story_scout.capture import collect_conversations
from story_scout.model import DEFAULT_MODEL, suggest_stories
from story_scout.models import Evidence, StoryCandidate
from story_scout.research import attach_research
from story_scout.sources import collect_evidence
from story_scout.store import Store

Log = Callable[[str], None]


def registered_projects(store: Store) -> list[Path]:
    return [Path(row["path"]) for row in store.list_sources()]


def collect_packet(
    store: Store,
    *,
    days: int,
    no_agents: bool = False,
    log: Log = print,
) -> tuple[list[Evidence], list[str]]:
    """Gather file, Git, and agent evidence for the registered folders."""
    projects = registered_projects(store)
    if not projects:
        raise ValueError("No source folders registered. Add one first.")
    evidence, omissions = collect_evidence(projects, days=days)
    if not no_agents:
        agent_evidence, agent_omissions = collect_conversations(projects, days=days)
        evidence.extend(agent_evidence)
        omissions.extend(agent_omissions)
    return evidence, omissions


def run_scan(
    store: Store,
    *,
    days: int = 7,
    remote: bool = False,
    model: str = DEFAULT_MODEL,
    no_agents: bool = False,
    no_research: bool = False,
    log: Log = print,
    evidence: list[Evidence] | None = None,
    omissions: list[str] | None = None,
) -> dict[str, object]:
    """Run one scan. Preview is local; remote adds ideas and verified sources."""
    if days < 1 or days > 365:
        raise ValueError("--days must be between 1 and 365.")
    if evidence is None:
        evidence, collected_omissions = collect_packet(
            store, days=days, no_agents=no_agents, log=log
        )
        omissions = collected_omissions
    omissions = list(omissions or [])
    log(f"Prepared {len(evidence)} evidence item(s).")
    for omission in omissions:
        log(f"Skipped: {omission}")
    if not evidence:
        return {
            "preview": not remote,
            "evidence": 0,
            "ideas": [],
            "ids": [],
            "sources": 0,
            "cited": 0,
        }
    if not remote:
        log("Local preview only. Nothing was sent.")
        return {
            "preview": True,
            "evidence": len(evidence),
            "ideas": [],
            "ids": [],
            "sources": 0,
            "cited": 0,
        }

    log(f"Asking {model} for story ideas.")
    warnings: list[str] = []
    candidates = suggest_stories(evidence, model=model, warnings=warnings)
    for warning in warnings:
        log(f"Dropped: {warning}")
    if not candidates:
        log("The evidence did not support a story worth suggesting.")
        return {
            "preview": False,
            "evidence": len(evidence),
            "ideas": [],
            "ids": [],
            "sources": 0,
            "cited": 0,
        }

    log(f"Fetching a source for each of {len(candidates)} idea(s).")
    if no_research:
        research_evidence: list[Evidence] = []
        research_notes = ["research skipped by request"]
    else:
        candidates, research_evidence, research_notes = attach_research(candidates)
    for note in research_notes:
        log(note)
    cited = sum(1 for candidate in candidates if candidate.research_urls)
    ids = store.save_candidates(candidates, list(evidence) + list(research_evidence))
    log(f"Stored {len(ids)} idea(s); {cited} carry a verified source.")
    return {
        "preview": False,
        "evidence": len(evidence),
        "ideas": candidates,
        "ids": ids,
        "sources": len(research_evidence),
        "cited": cited,
    }


def ideas_from_store(store: Store, status: str | None = None) -> list[dict[str, object]]:
    """Return stored ideas shaped for the renderer and the dashboard."""
    ideas: list[dict[str, object]] = []
    for story in store.list_stories(status=status):
        candidate = StoryCandidate(
            title=story["title"],
            angle=story["angle"],
            rationale=story["rationale"],
            audience=story["audience"],
            evidence_ids=tuple(item["id"] for item in story.get("evidence", [])),
            confidence=float(story["confidence"]),
            fact=story.get("fact") or "",
            interpretation=story.get("interpretation") or "",
            research_urls=tuple(story.get("research_urls") or ()),
            channel_x=story.get("channel_x") or "",
            channel_linkedin=story.get("channel_linkedin") or "",
            research_query=story.get("research_query") or "",
        )
        idea = candidate.as_idea()
        idea["id"] = story["id"]
        idea["status"] = story["status"]
        idea["draft"] = story.get("draft")
        ideas.append(idea)
    return ideas
