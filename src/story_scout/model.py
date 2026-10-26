"""Evidence-grounded model calls through the local OpenCode CLI."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Sequence

from story_scout.models import Evidence, StoryCandidate

DEFAULT_MODEL = "opencode-go/beam-free"
FREE_MODELS = frozenset(
    {
        "opencode-go/beam-free",
        "opencode/deepseek-v4.1-flash-free",
    }
)
AGENT_NAME = "story-scout"
MAX_CANDIDATES = 5
MAX_QUERIES = 5
MAX_DRAFT_CHARS = 5000


def _check_model(model: str) -> None:
    if model not in FREE_MODELS:
        raise ValueError(
            f"Tell is pinned to the free model set {', '.join(sorted(FREE_MODELS))}; "
            f"{model!r} is not one of them."
        )


def _extract_text(stdout: str) -> str:
    text_parts: list[str] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "text":
            continue
        part = event.get("part")
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            text_parts.append(part["text"])
    return "".join(text_parts).strip()


def _strip_fence(text: str) -> str:
    value = text.strip()
    if value.startswith("```") and value.endswith("```"):
        lines = value.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return value


def _load_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object, tolerating prose or fences around it."""
    candidate = _strip_fence(text)
    try:
        value = json.loads(candidate)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end > start:
        try:
            value = json.loads(candidate[start : end + 1])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
    raise ValueError("The model did not return a JSON object.")


def _run_opencode(payload: dict[str, Any], prompt: str, *, model: str, timeout: int) -> str:
    _check_model(model)
    project_root = Path(__file__).resolve().parents[2]
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            prefix="story-scout-",
            delete=False,
        ) as temporary:
            json.dump(payload, temporary, ensure_ascii=False)
            temporary_path = Path(temporary.name)

        command = [
            "opencode",
            "run",
            "--agent",
            AGENT_NAME,
            "--model",
            model,
            "--format",
            "json",
            "--file",
            str(temporary_path),
            prompt,
        ]
        try:
            result = subprocess.run(
                command,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("OpenCode CLI was not found on PATH.") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"OpenCode model call timed out after {timeout} seconds.") from exc

        if result.returncode != 0:
            details = (result.stdout + "\n" + result.stderr).lower()
            if "free usage limit" in details or "freeusage" in details or "free-limit" in details:
                message = (
                    "The free model has reached its usage limit. Wait for the limit to "
                    "reset, or connect an OpenCode Go model, then retry --remote."
                )
            elif "can't call models" in details or "cannot call models" in details:
                message = (
                    "The stored OpenCode key cannot call models. Reconnect the Go "
                    "provider in OpenCode before using --remote."
                )
            elif "can only be used from within opencode" in details:
                message = (
                    "This free model only works inside the OpenCode app. Connect an "
                    "OpenCode Go model for CLI scans."
                )
            else:
                message = (
                    f"OpenCode model call failed with exit code {result.returncode}. "
                    "Check OpenCode model access and try again."
                )
            raise RuntimeError(message)
        response = _extract_text(result.stdout)
        if not response:
            raise ValueError("OpenCode returned no text response.")
        return response
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _evidence_payload(evidence: Sequence[Evidence]) -> list[dict[str, Any]]:
    return [item.public_dict() for item in evidence]


def _required_text(candidate: dict[str, Any], field: str, max_length: int) -> str:
    value = candidate.get(field)
    if not isinstance(value, str):
        raise ValueError(f"Model candidate field {field!r} must be text.")
    value = value.strip()
    if not value or len(value) > max_length:
        raise ValueError(f"Model candidate field {field!r} is empty or too long.")
    return value


def _optional_text(candidate: dict[str, Any], field: str, max_length: int) -> str:
    value = candidate.get(field)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"Model candidate field {field!r} must be text.")
    return value.strip()[:max_length]


# Fallback query words that describe the recurring shape of a builder story.
_STOPWORDS = frozenset(
    """
    the a an and or but if then than that this these those for with without from into
    over under about after before while during between because so not no yes do does did
    done is are was were be been being have has had can could should would will just
    also more most less very much many some any all one two three new old use used using
    add adds added fix fixes fixed update updates updated file files code test tests
    chore feat docs refactor build chore commit changed changes
    """.split()
)
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+_-]{3,}")


def fallback_queries(evidence: Sequence[Evidence], *, limit: int = MAX_QUERIES) -> list[str]:
    """Derive plain search queries from work evidence without a model call."""
    counts: dict[str, int] = {}
    for item in evidence:
        for word in _WORD.findall(f"{item.label} {item.excerpt[:600]}"):
            lowered = word.lower().strip("-_")
            if lowered in _STOPWORDS or len(lowered) < 4:
                continue
            counts[lowered] = counts.get(lowered, 0) + 1
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    queries: list[str] = []
    top = [word for word, _ in ranked[:12]]
    for index in range(0, min(len(top), limit * 2), 2):
        pair = " ".join(top[index : index + 2])
        if pair.strip():
            queries.append(pair)
        if len(queries) >= limit:
            break
    return queries


def suggest_queries(
    evidence: Sequence[Evidence],
    *,
    model: str = DEFAULT_MODEL,
    timeout: int = 120,
) -> list[str]:
    """Ask the model for research queries grounded in the work evidence."""
    if not evidence:
        return []
    payload = {"evidence": _evidence_payload(evidence)}
    prompt = (
        "You are choosing research directions for one builder's public writing. "
        "Read the attached work evidence, which comes from that builder's own project "
        "files, commits, and agent conversations. "
        "Propose up to five short web search queries that would find real, checkable "
        "writing (essays, reports, news, documentation, research) that connects to the "
        "concrete problem, decision, or change visible in the evidence. "
        "Each query must be 2 to 5 plain keywords. Name a general concept a stranger "
        "would search for, never an internal function name, file name, or acronym from "
        "the code. Use no site: operator, no quotes, and no hypothetical wording. "
        'Return only strict JSON: {"queries":["...","..."]}'
    )
    raw = _run_opencode(payload, prompt, model=model, timeout=timeout)
    try:
        document = _load_json_object(raw)
    except ValueError:
        return fallback_queries(evidence)
    rows = document.get("queries")
    if not isinstance(rows, list):
        return fallback_queries(evidence)
    queries = [str(row).strip() for row in rows if isinstance(row, str) and str(row).strip()]
    cleaned = [query[:120] for query in queries if 2 <= len(query.split()) <= 8]
    return cleaned[:MAX_QUERIES] or fallback_queries(evidence)


def suggest_stories(
    evidence: Sequence[Evidence],
    *,
    model: str = DEFAULT_MODEL,
    timeout: int = 240,
    warnings: list[str] | None = None,
) -> list[StoryCandidate]:
    """Return up to five evidence-backed ideas, each with its own research query."""
    if not evidence:
        return []
    notes = warnings if warnings is not None else []
    known_ids = {item.id for item in evidence}
    payload = {"work_evidence": _evidence_payload(evidence)}
    prompt = (
        "You are the editor for one builder's public writing. Use ONLY the attached "
        "work_evidence, which comes from that builder's own projects: agent "
        "conversations, commits, and notes.\n\n"
        "Return zero to five ideas, best first. Quality beats count. Each idea must:\n"
        "1. Be a specific new angle, not a summary of a document. Name the actual "
        "moment, decision, tension, or change. Quote or closely paraphrase the "
        "smallest phrase from the work evidence that proves it.\n"
        "2. Separate `fact` (only what the evidence literally shows) from "
        "`interpretation` (what you infer). Never blur them.\n"
        "3. Set `evidence_ids` to ids that exist in work_evidence.\n"
        "4. Set `research_query` to 2 to 5 plain keywords that would find a real, "
        "checkable article, essay, or paper giving this idea a wider perspective. "
        "Name a general concept a stranger would search for, never an internal file "
        "name, function name, or acronym.\n"
        "5. Set `research_urls` to an empty list. Tell fetches and verifies sources "
        "itself and never accepts a citation it did not fetch.\n"
        "6. Give one `channel_x` framing under 280 characters and one "
        "`channel_linkedin` framing of two to four sentences.\n"
        "7. Never invent outcomes, numbers, users, quotes, sources, or personal "
        "claims. Never say the builder read something. Do not write the finished "
        "post.\n"
        "8. Prefer evidence whose source is \"agent\": that is the builder's own "
        "working conversation. Project plans and product documents are supporting "
        "context only. An idea that mainly restates a planning document is a summary, "
        "not a story. Drop it.\n"
        "9. `fact` must describe something that happened: a bug, a change, a "
        "measurement, a reaction. A statement of intent or a plan is not a fact.\n"
        "Return no idea when the evidence is weak.\n"
        'Return only strict JSON: {"candidates":[{"title":"...","angle":"...",'
        '"rationale":"...","audience":"...","fact":"...","interpretation":"...",'
        '"evidence_ids":["..."],"research_query":"...","research_urls":[],'
        '"channel_x":"...","channel_linkedin":"...","confidence":0.0}]}'
    )
    response = _strip_fence(_run_opencode(payload, prompt, model=model, timeout=timeout))
    try:
        document = json.loads(response)
    except json.JSONDecodeError:
        try:
            document = _load_json_object(response)
        except ValueError as exc:
            raise ValueError("OpenCode returned invalid JSON for story candidates.") from exc
    if not isinstance(document, dict) or not isinstance(document.get("candidates"), list):
        raise ValueError("OpenCode story response must contain a candidates list.")
    rows = document["candidates"]
    if len(rows) > MAX_CANDIDATES:
        raise ValueError(f"OpenCode returned more than {MAX_CANDIDATES} candidates.")

    result: list[StoryCandidate] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("OpenCode returned a candidate that is not an object.")
        title = _required_text(row, "title", 160)
        angle = _required_text(row, "angle", 600)
        rationale = _required_text(row, "rationale", 600)
        audience = _required_text(row, "audience", 240)
        refs = row.get("evidence_ids")
        if not isinstance(refs, list) or not refs or not all(isinstance(ref, str) for ref in refs):
            raise ValueError("Each candidate must cite one or more evidence IDs.")
        evidence_ids = tuple(dict.fromkeys(ref.strip() for ref in refs))
        if any(not ref or ref not in known_ids for ref in evidence_ids):
            raise ValueError("OpenCode cited an evidence ID that was not in the packet.")
        confidence = row.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValueError("Candidate confidence must be a number from 0 to 1.")
        if not 0 <= float(confidence) <= 1:
            raise ValueError("Candidate confidence must be a number from 0 to 1.")
        claim = row.get("research_urls")
        if isinstance(claim, list) and any(url for url in claim if isinstance(url, str)):
            notes.append(
                f"ignored model-supplied citation(s) for {title!r}: Tell only cites what it fetched"
            )

        result.append(
            StoryCandidate(
                title=title,
                angle=angle,
                rationale=rationale,
                audience=audience,
                evidence_ids=evidence_ids,
                confidence=float(confidence),
                fact=_optional_text(row, "fact", 400),
                interpretation=_optional_text(row, "interpretation", 400),
                research_urls=(),
                channel_x=_optional_text(row, "channel_x", 400),
                channel_linkedin=_optional_text(row, "channel_linkedin", 900),
                research_query=_optional_text(row, "research_query", 120),
            )
        )
    return result


def check_connection(model: str = DEFAULT_MODEL, *, timeout: int = 60) -> tuple[bool, str]:
    """Send one tiny prompt and report whether the provider answers."""
    if model not in FREE_MODELS:
        return False, "Only free models are allowed. Pick one from the list."
    try:
        reply = _run_opencode(
            {"probe": "connection check"},
            "Reply with the single word ok. Do not add anything else.",
            model=model,
            timeout=timeout,
        )
    except (RuntimeError, ValueError) as error:
        return False, str(error)
    snippet = " ".join(reply.split())[:80]
    return True, f"Connected to {model}. Reply: {snippet!r}"


def draft_story(
    candidate: StoryCandidate,
    evidence: Sequence[Evidence],
    *,
    model: str = DEFAULT_MODEL,
    timeout: int = 180,
) -> str:
    selected_ids = set(candidate.evidence_ids)
    selected = [item for item in evidence if item.id in selected_ids]
    if not selected or {item.id for item in selected} != selected_ids:
        raise ValueError("The kept candidate's evidence is missing.")
    payload = {
        "candidate": {
            "title": candidate.title,
            "angle": candidate.angle,
            "rationale": candidate.rationale,
            "audience": candidate.audience,
            "evidence_ids": list(candidate.evidence_ids),
        },
        "evidence": _evidence_payload(selected),
    }
    prompt = (
        "Draft one concise social post based only on the attached kept candidate and "
        "evidence. Do not add facts, outcomes, citations, or claims that the evidence "
        "does not support. Do not say the user read a source unless the evidence says so. "
        "Return only the draft text. Do not publish it."
    )
    draft = _run_opencode(payload, prompt, model=model, timeout=timeout).strip()
    if len(draft) > MAX_DRAFT_CHARS:
        raise ValueError(f"OpenCode draft exceeded {MAX_DRAFT_CHARS} characters.")
    return draft
