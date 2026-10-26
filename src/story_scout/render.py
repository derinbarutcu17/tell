"""Render the local, self-contained Tell inbox as one HTML file.

Everything written here is local: no server, no JavaScript, no external
assets. All dynamic text is escaped and every link is scheme-checked.
"""

from __future__ import annotations

import html
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ALLOWED_URL_SCHEMES = frozenset({"http", "https"})

_STYLE = """
:root {
  color-scheme: light;
  --ink: #14161a;
  --muted: #5c6169;
  --line: #d9dad5;
  --paper: #ffffff;
  --page: #f6f6f3;
  --accent: #0b5294;
  --fact-bg: #f8f8f5;
  --note-bg: #fdf5e6;
  --note-line: #b0741a;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  padding: 40px 24px 72px;
  background: var(--page);
  color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 16px;
  line-height: 1.55;
}
.wrap { max-width: 1000px; margin: 0 auto; }
.page-header {
  border-bottom: 1px solid var(--line);
  padding-bottom: 20px;
  margin-bottom: 28px;
}
.page-header h1 {
  margin: 0;
  font-size: 26px;
  line-height: 1.2;
  letter-spacing: -0.01em;
}
.generated {
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 13px;
}
.card {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 28px;
  margin: 0 0 20px;
}
.card-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}
.index {
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  color: var(--muted);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 2px 7px;
}
.card-head h2 {
  margin: 0;
  font-size: 20px;
  line-height: 1.3;
  flex: 1 1 320px;
}
.confidence {
  font-size: 12px;
  letter-spacing: 0.02em;
  color: var(--muted);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 2px 8px;
  white-space: nowrap;
}
.angle {
  margin: 0 0 20px;
  font-size: 17px;
  color: #23262b;
}
.block { margin: 0 0 18px; }
.block:last-child { margin-bottom: 0; }
h3 {
  margin: 0 0 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--muted);
}
.block p { margin: 0; }
.split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin: 0 0 18px;
}
.split > section { padding: 14px 16px; border-radius: 6px; }
.split h3 { margin-bottom: 8px; }
.split p { margin: 0; }
.fact {
  background: var(--fact-bg);
  border: 1px solid #e3e3dd;
}
.interpretation {
  background: var(--note-bg);
  border: 1px solid #ecd9b4;
  border-left: 4px solid var(--note-line);
}
.interpretation h3 { color: #7d4f0c; }
.note {
  display: block;
  margin: 0 0 6px;
  font-size: 12px;
  color: #7d4f0c;
}
.columns { grid-template-columns: 1fr 1fr; }
.channel {
  background: var(--paper);
  border: 1px solid var(--line);
}
ul { margin: 0; padding: 0; list-style: none; }
li { margin: 0 0 4px; }
a {
  color: var(--accent);
  text-decoration: underline;
  text-underline-offset: 2px;
  overflow-wrap: anywhere;
}
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  background: #f1f1ec;
  border: 1px solid #e2e2db;
  border-radius: 6px;
  padding: 2px 7px;
  margin: 0;
  overflow-wrap: anywhere;
}
.empty {
  background: var(--paper);
  border: 1px dashed #c8c9c3;
  border-radius: 8px;
  padding: 44px 28px;
  text-align: center;
}
.empty h2 { margin: 0 0 8px; font-size: 19px; }
.empty p { margin: 0; color: var(--muted); }
@media (max-width: 720px) {
  body { padding: 28px 16px 56px; }
  .card { padding: 20px; }
  .split, .columns { grid-template-columns: 1fr; }
}
@media print {
  body { background: #ffffff; padding: 0; font-size: 11.5pt; }
  .card { break-inside: avoid; page-break-inside: avoid; margin-bottom: 14pt; }
  a { color: #000000; }
  .empty { border-style: solid; }
}
"""


def _escape(value: object) -> str:
    """Escape any value for safe use as HTML text."""
    return html.escape(str(value), quote=True)


def _text(value: object) -> str:
    """Escape text and keep intentional line breaks."""
    escaped = _escape(value)
    return escaped.replace("\r\n", "\n").replace("\n", "<br>")


def _plain(value: object) -> str:
    """Return trimmed text, or an empty string for non-text values."""
    if isinstance(value, str):
        return value.strip()
    return ""


def _safe_url(value: object) -> str | None:
    """Return the URL only when it is an absolute http(s) URL."""
    candidate = _plain(value)
    if not candidate:
        return None
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return None
    if parts.scheme.lower() not in ALLOWED_URL_SCHEMES:
        return None
    if not parts.netloc:
        return None
    if any(character.isspace() or ord(character) < 0x21 for character in candidate):
        return None
    return candidate


def _confidence(value: object) -> str | None:
    """Render a 0..1 confidence as a whole percentage, or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        return None
    return f"{round(number * 100)}%"


def _string_list(value: object) -> list[str]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        return []
    items: list[str] = []
    for item in value:
        text = _plain(item)
        if text:
            items.append(text)
    return items


def _section(label: str, body: str, extra_class: str = "") -> str:
    classes = f"block {extra_class}".strip()
    return (
        f'      <section class="{classes}">\n'
        f"        <h3>{_escape(label)}</h3>\n"
        f"        <p>{body}</p>\n"
        "      </section>\n"
    )


def _card(idea: Mapping[str, Any], number: int) -> str:
    title = _plain(idea.get("title")) or "Untitled idea"
    angle = _plain(idea.get("angle"))
    why = _plain(idea.get("why"))
    fact = _plain(idea.get("fact"))
    interpretation = _plain(idea.get("interpretation"))
    audience = _plain(idea.get("audience"))

    head = [
        '    <article class="card">\n',
        '      <div class="card-head">\n',
        f'        <span class="index">{number}</span>\n',
        f"        <h2>{_escape(title)}</h2>\n",
    ]
    confidence = _confidence(idea.get("confidence"))
    if confidence:
        head.append(f'        <span class="confidence">{_escape(confidence)} confidence</span>\n')
    head.append("      </div>\n")
    parts = ["".join(head)]

    if angle:
        parts.append(f'      <p class="angle">{_text(angle)}</p>\n')
    if why:
        parts.append(_section("Why it may matter", _text(why)))

    if fact or interpretation:
        parts.append('      <div class="split">\n')
        fact_body = _text(fact) if fact else "No work evidence was captured for this idea."
        parts.append(
            '        <section class="fact">\n'
            "          <h3>Fact from your work</h3>\n"
            f"          <p>{fact_body}</p>\n"
            "        </section>\n"
        )
        note = '<span class="note">Inferred, not observed</span>' if interpretation else ""
        interpretation_body = (
            _text(interpretation)
            if interpretation
            else "No interpretation was recorded for this idea."
        )
        parts.append(
            '        <section class="interpretation">\n'
            "          <h3>Interpretation</h3>\n"
            f"          {note}\n"
            f"          <p>{interpretation_body}</p>\n"
            "        </section>\n"
        )
        parts.append("      </div>\n")

    if audience:
        parts.append(_section("Audience", _text(audience)))

    links: list[str] = []
    seen_urls: set[str] = set()
    for raw in _string_list(idea.get("research_urls")):
        url = _safe_url(raw)
        if url is None or url in seen_urls:
            continue
        seen_urls.add(url)
        links.append(
            '          <li><a href="'
            + _escape(url)
            + '" target="_blank" rel="noopener noreferrer">'
            + _escape(url)
            + "</a></li>\n"
        )
    if links:
        parts.append(
            '      <section class="block">\n'
            "        <h3>Research</h3>\n"
            '        <ul class="links">\n' + "".join(links) + "        </ul>\n"
            "      </section>\n"
        )

    chips = []
    seen_ids: set[str] = set()
    for evidence_id in _string_list(idea.get("work_evidence_ids")):
        if evidence_id in seen_ids:
            continue
        seen_ids.add(evidence_id)
        chips.append(f'          <li class="chip">{_escape(evidence_id)}</li>\n')
    if chips:
        parts.append(
            '      <section class="block">\n'
            "        <h3>Work evidence</h3>\n"
            '        <ul class="chips">\n' + "".join(chips) + "        </ul>\n"
            "      </section>\n"
        )

    channels = idea.get("channels")
    if isinstance(channels, Mapping):
        x_text = _plain(channels.get("x"))
        linkedin_text = _plain(channels.get("linkedin"))
        if x_text or linkedin_text:
            x_body = _text(x_text) if x_text else "No framing yet."
            linkedin_body = _text(linkedin_text) if linkedin_text else "No framing yet."
            parts.append('      <div class="split columns">\n')
            parts.append(
                '        <section class="channel">\n'
                "          <h3>On X</h3>\n"
                f"          <p>{x_body}</p>\n"
                "        </section>\n"
            )
            parts.append(
                '        <section class="channel">\n'
                "          <h3>On LinkedIn</h3>\n"
                f"          <p>{linkedin_body}</p>\n"
                "        </section>\n"
            )
            parts.append("      </div>\n")

    parts.append("    </article>\n")
    return "".join(parts)


def _empty_state() -> str:
    return (
        '    <section class="empty">\n'
        "      <h2>Nothing yet</h2>\n"
        "      <p>No ideas have been collected. Add a source and scan it to see "
        "evidence-backed ideas here.</p>\n"
        "    </section>\n"
    )


def render_inbox(
    ideas: Sequence[Mapping[str, object]],
    path: str | Path,
    *,
    generated_at: str | None = None,
    title: str = "Tell",
) -> Path:
    """Write a self-contained HTML inbox to `path` and return the Path."""
    destination = Path(path)
    page_title = _plain(title) or "Tell"

    document = [
        "<!DOCTYPE html>\n",
        '<html lang="en">\n',
        "<head>\n",
        '<meta charset="utf-8">\n',
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n',
        '<meta name="color-scheme" content="light">\n',
        f"<title>{_escape(page_title)}</title>\n",
        "<style>",
        _STYLE,
        "</style>\n",
        "</head>\n",
        "<body>\n",
        '  <main class="wrap">\n',
        '    <header class="page-header">\n',
        f"      <h1>{_escape(page_title)}</h1>\n",
    ]
    stamp = _plain(generated_at)
    if stamp:
        document.append(f'      <p class="generated">{_escape(stamp)}</p>\n')
    document.append("    </header>\n")

    body: list[str] = []
    if isinstance(ideas, Mapping):
        rows: list[object] = []
    else:
        try:
            rows = list(ideas)
        except TypeError:
            rows = []
    for idea in rows:
        if not isinstance(idea, Mapping):
            continue
        body.append(_card(idea, len(body) + 1))
    if not body:
        document.append(_empty_state())
    else:
        document.extend(body)

    document.extend(["  </main>\n", "</body>\n", "</html>\n"])
    html_text = "".join(document)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html_text, encoding="utf-8")
    return destination
