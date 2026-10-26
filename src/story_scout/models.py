"""Shared immutable records used by the Tell pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Evidence:
    id: str
    label: str
    kind: str
    excerpt: str
    date: str | None = None
    local_path: str | None = None
    commit: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    source: str = "file"
    url: str | None = None

    def public_dict(self) -> dict[str, object]:
        """Return only fields permitted in a remote model packet."""
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "source": self.source,
            "excerpt": self.excerpt,
            "date": self.date,
            "commit": self.commit,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "url": self.url,
        }


@dataclass(frozen=True, slots=True)
class StoryCandidate:
    title: str
    angle: str
    rationale: str
    audience: str
    evidence_ids: tuple[str, ...]
    confidence: float
    fact: str = ""
    interpretation: str = ""
    research_urls: tuple[str, ...] = ()
    channel_x: str = ""
    channel_linkedin: str = ""

    def as_idea(self) -> dict[str, object]:
        """Return the plain mapping the inbox renderer expects."""
        return {
            "title": self.title,
            "angle": self.angle,
            "why": self.rationale,
            "fact": self.fact,
            "interpretation": self.interpretation,
            "audience": self.audience,
            "confidence": self.confidence,
            "work_evidence_ids": list(self.evidence_ids),
            "research_urls": list(self.research_urls),
            "channels": {"x": self.channel_x, "linkedin": self.channel_linkedin},
        }
