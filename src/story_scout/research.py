"""Collect public web research as evidence, with no third-party dependencies."""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import (
    parse_qs,
    parse_qsl,
    quote,
    quote_plus,
    urlencode,
    urljoin,
    urlsplit,
    urlunsplit,
)
from urllib.request import HTTPRedirectHandler, Request, build_opener

from story_scout.models import Evidence
from story_scout.redact import redact

SEARCH_ENDPOINT = "https://html.duckduckgo.com/html/"
HN_ENDPOINT = "https://hn.algolia.com/api/v1/search"
ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
WIKI_ENDPOINT = "https://en.wikipedia.org/w/api.php"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
MAX_BYTES = 400_000
DROPPED_PARAMS = frozenset({"ref", "fbclid"})
MANY_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "body",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)
SKIPPED_TAGS = frozenset({"iframe", "noscript", "script", "style", "svg", "template"})
BLOCKED_HOSTS = frozenset(
    {
        "0.0.0.0",
        "::",
        "::1",
        "[::1]",
        "ip6-localhost",
        "localhost",
        "localhost.localdomain",
    }
)
BLOCKED_SUFFIXES = (".internal", ".local", ".localhost")


@dataclass(frozen=True, slots=True)
class SearchHit:
    url: str
    title: str
    snippet: str


def search(query: str, *, limit: int = 5, timeout: float = 10.0) -> list[SearchHit]:
    """Return at most ``limit`` search hits, or an empty list on any failure.

    Providers are tried in order. The first one that returns usable hits wins,
    so a blocked or rate-limited provider degrades instead of failing the run.
    """
    text = (query or "").strip()
    if not text or limit <= 0:
        return []
    hits: list[SearchHit] = []
    for provider in (_search_hackernews, _search_arxiv, _search_duckduckgo):
        try:
            hits.extend(provider(text, limit=limit, timeout=timeout))
        except Exception:
            continue
    if not hits:
        try:
            hits.extend(_search_wikipedia(text, limit=limit, timeout=timeout))
        except Exception:
            pass
    if not hits:
        return []
    seen: set[str] = set()
    unique: list[SearchHit] = []
    for hit in hits:
        key = normalize_url(hit.url) or hit.url
        if key in seen:
            continue
        seen.add(key)
        unique.append(hit)
    return _rank_hits(unique, text)[:limit]


def _search_hackernews(query: str, *, limit: int, timeout: float) -> list[SearchHit]:
    """Query the public Hacker News search API. No key, stable JSON."""
    endpoint = (
        f"{HN_ENDPOINT}?tags=story&hitsPerPage={min(limit * 3, 20)}"
        f"&query={quote_plus(query)}"
    )
    raw = _read(endpoint, timeout=timeout)
    if not raw:
        return []
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    rows = payload.get("hits")
    if not isinstance(rows, list):
        return []
    hits: list[SearchHit] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = _collapse(str(row.get("title") or ""))
        target = str(row.get("url") or "").strip()
        if not target:
            object_id = row.get("objectID")
            if object_id:
                target = f"https://news.ycombinator.com/item?id={object_id}"
        if not title or not target:
            continue
        lowered_title = title.lower()
        if lowered_title.startswith("show hn") or lowered_title.startswith("ask hn"):
            continue
        points = row.get("points")
        comments = row.get("num_comments")
        snippet = f"{title}."
        if isinstance(points, int) and points:
            snippet += f" {points} points"
        if isinstance(comments, int) and comments:
            snippet += f", {comments} comments" if points else f" {comments} comments"
        hits.append(SearchHit(url=target, title=title, snippet=snippet))
    return hits


def _search_arxiv(query: str, *, limit: int, timeout: float) -> list[SearchHit]:
    """Query arXiv for research that speaks to the problem. No key needed."""
    terms = [word for word in re.findall(r"[A-Za-z0-9]{3,}", query)][:6]
    if not terms:
        return []
    search_query = " AND ".join(f"all:{term}" for term in terms)
    endpoint = (
        f"{ARXIV_ENDPOINT}?search_query={quote(search_query, safe='')}"
        f"&max_results={min(limit, 5)}&sortBy=relevance"
    )
    raw = _read(endpoint, timeout=timeout)
    if not raw:
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    hits: list[SearchHit] = []
    for entry in root.findall("atom:entry", namespace):
        title = _collapse(entry.findtext("atom:title", default="", namespaces=namespace))
        link = (entry.findtext("atom:id", default="", namespaces=namespace) or "").strip()
        summary = _collapse(entry.findtext("atom:summary", default="", namespaces=namespace))
        if title and link.startswith("http"):
            hits.append(SearchHit(url=link, title=title, snippet=summary[:400]))
    return hits


def _search_duckduckgo(query: str, *, limit: int, timeout: float) -> list[SearchHit]:
    """Query DuckDuckGo's HTML endpoint. It sometimes answers 202 with no results."""
    endpoint = f"{SEARCH_ENDPOINT}?q={quote_plus(query)}"
    raw = _read(endpoint, timeout=timeout)
    if not raw:
        return []
    return _parse_search_html(raw.decode("utf-8", errors="replace"))[:limit]


def _search_wikipedia(query: str, *, limit: int, timeout: float) -> list[SearchHit]:
    """Query Wikipedia's opensearch API as a last-resort background source."""
    endpoint = (
        f"{WIKI_ENDPOINT}?action=opensearch&format=json&limit={min(limit, 5)}"
        f"&search={quote_plus(query)}"
    )
    raw = _read(endpoint, timeout=timeout)
    if not raw:
        return []
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    if not isinstance(payload, list) or len(payload) < 4:
        return []
    titles, urls, snippets = payload[1], payload[2], payload[3]
    hits: list[SearchHit] = []
    for index, target in enumerate(urls if isinstance(urls, list) else []):
        title = titles[index] if isinstance(titles, list) and index < len(titles) else ""
        snippet = snippets[index] if isinstance(snippets, list) and index < len(snippets) else ""
        if isinstance(target, str) and target.startswith("http"):
            hits.append(SearchHit(url=target, title=str(title), snippet=str(snippet)))
    return hits


def _rank_hits(hits: Sequence[SearchHit], query: str) -> list[SearchHit]:
    """Stable ranking by query-word overlap, keeping provider order for ties.

    Repository READMEs and Show HN launch posts are real pages but weak
    perspectives, so they sort below articles and essays.
    """
    words = {word for word in re.findall(r"[a-z0-9]{3,}", query.lower())}
    if not words:
        return list(hits)

    def score(hit: SearchHit) -> int:
        haystack = f"{hit.title} {hit.snippet}".lower()
        value = sum(1 for word in words if word in haystack)
        domain = domain_of(hit.url)
        if domain.endswith("github.com") or domain == "news.ycombinator.com":
            value -= 2
        lowered = hit.title.lower()
        if lowered.startswith("show hn") or lowered.startswith("ask hn"):
            value -= 1
        return value

    indexed = list(enumerate(hits))
    indexed.sort(key=lambda pair: (-score(pair[1]), pair[0]))
    return [hit for _, hit in indexed]


def fetch_page(
    url: str, *, timeout: float = 15.0, max_chars: int = 4000
) -> tuple[str, str] | None:
    """Return ``(title, text)`` for a safe page, or ``None`` when unusable."""
    if not is_safe_url(url):
        return None
    try:
        raw = _read(url, timeout=timeout)
        if not raw:
            return None
        parser = _TextParser()
        parser.feed(raw.decode("utf-8", errors="replace"))
        parser.close()
        body = _collapse(parser.body_text())
    except Exception:
        return None
    if not body:
        return None
    title = _collapse(parser.title) or domain_of(url)
    return title, body[:max_chars].rstrip()


def collect_research(
    queries: Sequence[str],
    *,
    limit_per_query: int = 3,
    max_sources: int = 6,
    timeout: float = 10.0,
) -> tuple[list[Evidence], list[str]]:
    """Search each query, fetch each hit, and return deduped evidence plus omissions."""
    evidence: list[Evidence] = []
    omissions: list[str] = []
    seen: set[str] = set()
    capped = False

    for query in queries:
        if len(evidence) >= max_sources:
            break
        hits = search(query, limit=limit_per_query, timeout=timeout)
        if not hits:
            omissions.append(f"search failed for query: {query}")
            continue
        for hit in hits:
            if len(evidence) >= max_sources:
                capped = True
                break
            key = normalize_url(hit.url)
            if key is None:
                omissions.append(f"skipped {hit.url}: unsafe url")
                continue
            if key in seen:
                continue
            seen.add(key)
            page = fetch_page(hit.url, timeout=timeout)
            if page is None:
                omissions.append(f"skipped {hit.url}: fetch failed")
                continue
            title, text = page
            evidence.append(
                Evidence(
                    id=f"research:{slug_for(hit.url)}-{len(evidence) + 1}",
                    label=title or domain_of(hit.url) or hit.url,
                    kind="research",
                    excerpt=redact(text),
                    date=None,
                    local_path=None,
                    commit=None,
                    line_start=None,
                    line_end=None,
                    source="research",
                    url=hit.url,
                )
            )
        if capped:
            break

    if capped:
        omissions.append(f"omitted additional sources: source limit ({max_sources})")
    return evidence, omissions


def is_safe_url(url: str) -> bool:
    """Return True only for public http/https URLs that cannot reach this machine.

    A hostname is resolved and every returned address is checked, so shortcuts
    such as ``127.1``, ``0x7f.1``, and DNS names that map to loopback are
    rejected as well as literal private addresses.
    """
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return False
    if parts.scheme.lower() not in ("http", "https"):
        return False
    host = (parts.hostname or "").strip().lower().rstrip(".")
    if not host or host in BLOCKED_HOSTS:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        return not _address_is_blocked(address)
    if "." not in host:
        return False
    if host.endswith(BLOCKED_SUFFIXES):
        return False
    for candidate in _resolve_addresses(host):
        if _address_is_blocked(candidate):
            return False
    return True


def _address_is_blocked(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def _resolve_addresses(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve a hostname to addresses. A failed lookup yields an empty list."""
    try:
        records = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError):
        return []
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for record in records:
        try:
            addresses.append(ipaddress.ip_address(record[4][0]))
        except (ValueError, IndexError, TypeError):
            continue
    return addresses


class _SafeRedirectHandler(HTTPRedirectHandler):
    """Refuse a redirect whose destination is not a public URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        if not is_safe_url(newurl):
            raise HTTPError(newurl, code, "blocked redirect to a non-public address", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = build_opener(_SafeRedirectHandler())


def urlopen(request: Request, *, timeout: float):
    """Fetch through an opener that re-checks every redirect destination."""
    return _OPENER.open(request, timeout=timeout)


def normalize_url(url: str) -> str | None:
    """Return a stable dedupe key, or None when the URL is unusable or unsafe."""
    if not is_safe_url(url):
        return None
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        return None
    netloc = host
    default_port = 443 if scheme == "https" else 80
    if port is not None and port != default_port:
        netloc = f"{host}:{port}"
    kept = [
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _dropped_param(name)
    ]
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, urlencode(kept), ""))


def domain_of(url: str) -> str:
    """Return the lowercased host without a leading ``www.``."""
    try:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def slug_for(url: str) -> str:
    """Return a short readable slug based on the site's first host label."""
    host = domain_of(url)
    first = host.split(".")[0] if host else ""
    slug = re.sub(r"[^a-z0-9]+", "-", first.lower()).strip("-")
    return slug or "source"


def _dropped_param(name: str) -> bool:
    lower = name.lower()
    return lower.startswith("utm_") or lower in DROPPED_PARAMS


def _read(url: str, *, timeout: float) -> bytes | None:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    response = urlopen(request, timeout=timeout)
    try:
        status = getattr(response, "status", None)
        if status is None:
            status = getattr(response, "code", None)
        if status is not None and not 200 <= int(status) < 300:
            return None
        return response.read(MAX_BYTES)
    finally:
        close = getattr(response, "close", None)
        if close is not None:
            close()


def _collapse(text: str) -> str:
    return " ".join(text.split())


class _SearchParser(HTMLParser):
    """Collect result title and snippet anchors from DuckDuckGo's HTML page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[list[object]] = []
        self._current: list[object] | None = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        kind = _anchor_kind(classes)
        if kind is None:
            self._current = None
            return
        self._current = [kind, attributes.get("href") or "", []]
        self.items.append(self._current)

    def handle_endtag(self, tag):
        if tag.lower() == "a":
            self._current = None

    def handle_data(self, data):
        if self._current is None:
            return
        chunks = self._current[2]
        if isinstance(chunks, list):
            chunks.append(data)


def _anchor_kind(classes: list[str]) -> str | None:
    for name in classes:
        if name == "result__a":
            return "title"
        if name in ("result__snippet", "result-snippet"):
            return "snippet"
    return None


def _parse_search_html(html: str) -> list[SearchHit]:
    parser = _SearchParser()
    parser.feed(html)
    parser.close()
    rows: list[list[str]] = []
    for kind, href, chunks in parser.items:
        text = _collapse("".join(chunks))
        if kind == "title":
            target = _unwrap_redirect(str(href))
            if not target:
                continue
            rows.append([target, text, ""])
        elif rows:
            rows[-1][2] = text
    hits: list[SearchHit] = []
    for url, title, snippet in rows:
        if not is_safe_url(url):
            continue
        hits.append(SearchHit(url=url, title=title or domain_of(url), snippet=snippet))
    return hits


def _unwrap_redirect(href: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    if href.startswith("//"):
        href = f"https:{href}"
    elif href.startswith("/"):
        href = urljoin(SEARCH_ENDPOINT, href)
    try:
        parts = urlsplit(href)
    except ValueError:
        return ""
    if "duckduckgo.com" in parts.netloc.lower():
        target = parse_qs(parts.query).get("uddg")
        if target:
            return target[0].strip()
    return href


class _TextParser(HTMLParser):
    """Extract the title and readable body text from an HTML document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._body: list[str] = []
        self._skip_depth = 0
        self._head_depth = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in SKIPPED_TAGS:
            self._skip_depth += 1
        elif tag == "head":
            self._head_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in MANY_BLOCK_TAGS:
            self._body.append(" ")

    def handle_startendtag(self, tag, attrs):
        if tag.lower() in MANY_BLOCK_TAGS:
            self._body.append(" ")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in SKIPPED_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag == "head":
            self._head_depth = max(0, self._head_depth - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in MANY_BLOCK_TAGS:
            self._body.append(" ")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._skip_depth or self._head_depth:
            return
        else:
            self._body.append(data)

    def body_text(self) -> str:
        return "".join(self._body)
