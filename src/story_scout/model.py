"""Evidence-grounded model calls through the local OpenCode CLI."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Sequence

from story_scout.models import Evidence, StoryCandidate

DEFAULT_MODEL = "opencode-go/beam-free"
AGENT_NAME = "story-scout"
MAX_CANDIDATES = 3
MAX_DRAFT_CHARS = 5000


def _check_model(model: str) -> None:
    if model != DEFAULT_MODEL:
        raise ValueError(f"Story Scout V1 is pinned to the free model {DEFAULT_MODEL}.")


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
            if "can't call models" in details or "cannot call models" in details:
                message = (
                    "The stored OpenCode Go key cannot call models. Reconnect the Go "
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


def suggest_stories(
    evidence: Sequence[Evidence],
    *,
    model: str = DEFAULT_MODEL,
    timeout: int = 180,
) -> list[StoryCandidate]:
    if not evidence:
        return []
    known_ids = {item.id for item in evidence}
    payload = {"evidence": _evidence_payload(evidence)}
    prompt = (
        "Use only the attached evidence packet. Find zero to three specific story ideas "
        "that are surprising, useful, or show a real decision or change. Do not invent "
        "events, outcomes, audience reactions, research, or personal claims. Do not use "
        "web research or imply the user read anything. Return no idea when the evidence "
        "is weak. Each candidate must cite one or more exact evidence IDs from the packet. "
        "Mark uncertainty in the rationale. Do not write or publish a finished post. "
        "Return only strict JSON in this shape: "
        '{"candidates":[{"title":"...","angle":"...","rationale":"...","audience":"...",'
        '"evidence_ids":["..."],"confidence":0.0}]}'
    )
    response = _strip_fence(_run_opencode(payload, prompt, model=model, timeout=timeout))
    try:
        document = json.loads(response)
    except json.JSONDecodeError as exc:
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
        result.append(
            StoryCandidate(
                title=title,
                angle=angle,
                rationale=rationale,
                audience=audience,
                evidence_ids=evidence_ids,
                confidence=float(confidence),
            )
        )
    return result


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
