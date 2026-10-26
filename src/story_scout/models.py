"""Shared immutable records used by the Story Scout pipeline."""

from __future__ import annotations

from dataclasses import dataclass


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

    def public_dict(self) -> dict[str, object]:
        """Return only fields permitted in a remote model packet."""
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "excerpt": self.excerpt,
            "date": self.date,
            "commit": self.commit,
            "line_start": self.line_start,
            "line_end": self.line_end,
        }


@dataclass(frozen=True, slots=True)
class StoryCandidate:
    title: str
    angle: str
    rationale: str
    audience: str
    evidence_ids: tuple[str, ...]
    confidence: float
