"""Remove credential-shaped strings and home paths before storage or model calls.

One gate for every evidence source, so a rule cannot apply to agent turns and
quietly miss a markdown file or a Git subject.
"""

from __future__ import annotations

import re

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\b(?:sk|ghp|gho|ghu|ghs|github_pat|xoxb|xoxp|xoxa)[-_][A-Za-z0-9_\-]{10,}"),
        "[redacted-secret]",
    ),
    (re.compile(r"\bAKIA[0-9A-Z]{12,}\b"), "[redacted-secret]"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
            r"password|passwd|secret|token)\b\s*[:=]\s*[\"']?[^\s\"',}]{6,}"
        ),
        r"\1=[redacted]",
    ),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{10,}"), "Bearer [redacted]"),
    (
        re.compile(
            r"(?i)\b-{5}BEGIN [A-Z ]*PRIVATE KEY-{5}[\s\S]*?-{5}END [A-Z ]*PRIVATE KEY-{5}"
        ),
        "[redacted-private-key]",
    ),
)

_HOME_TEXT_PATTERN = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+")


def redact(text: str) -> str:
    """Return text with credential-shaped strings and home paths removed."""
    if not text:
        return ""
    cleaned = text
    for pattern, replacement in _SECRET_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    cleaned = _HOME_TEXT_PATTERN.sub("~", cleaned)
    return cleaned
