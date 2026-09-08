"""Compare the security-relevant structure of two captures.

Text and pixel diffing both miss the attacks that matter most for a compromised
site, because the payload is invisible: a `<script src>` added before `</body>`,
a hidden `<iframe>`, a `<form action>` repointed at someone else's collector, a
`meta refresh` redirect, or spam links buried in a `display: none` block. None of
those move a pixel, and `inner_text` skips hidden nodes entirely.

So instead of diffing the markup as prose — which drowns in per-request noise
from CSRF tokens, nonces and cache-busting query strings — this module extracts
a *set of facts* about the page and compares the sets. A set of script URLs does
not change between two loads unless something really changed.

The HTML parsed here is the artifact capture already stores, and `page.content()`
serialises the DOM *after* scripts have run, so JS-injected elements are
included. Nothing new is captured, and the comparison works on snapshots taken
before this module existed.
"""

import hashlib
import logging
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

__all__ = ["StructureDiff", "compare_structure", "extract_structure"]

# Facts are prefixed with their kind so a summary reads directly to a human and
# so an added script can never collide with an added iframe of the same URL.
KIND_SCRIPT = "script"
KIND_INLINE_SCRIPT = "inline-script"
KIND_IFRAME = "iframe"
KIND_FORM = "form"
KIND_STYLESHEET = "stylesheet"
KIND_META_REFRESH = "meta-refresh"
KIND_LINK_HOST = "link-host"


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def _normalise_host(host: str) -> str:
    host = host.strip().lower().lstrip(".")
    return host[4:] if host.startswith("www.") else host


def _is_allowed(host: str, allowed_hosts: Collection[str]) -> bool:
    """True when `host` is allowlisted, including as a parent domain.

    Allowlisting `example.com` covers `cdn.example.com`, because third parties
    routinely serve the same asset from rotating subdomains and flagging each
    one would bury the real findings.
    """
    if not host:
        return False
    host = _normalise_host(host)
    for allowed in allowed_hosts:
        allowed_host = _normalise_host(allowed)
        if not allowed_host:
            continue
        if host == allowed_host or host.endswith(f".{allowed_host}"):
            return True
    return False


class _StructureParser(HTMLParser):
    """Collects security-relevant elements from a serialised DOM.

    `html.parser` is used rather than a third-party parser to avoid adding a
    dependency to the component that handles hostile input.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.script_srcs: list[str] = []
        self.iframe_srcs: list[str] = []
        self.form_actions: list[str] = []
        self.stylesheet_hrefs: list[str] = []
        self.meta_refreshes: list[str] = []
        self.link_hrefs: list[str] = []
        self._inline_script_parts: list[str] = []
        self._in_inline_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): (value or "") for name, value in attrs}

        if tag == "script":
            src = attributes.get("src", "").strip()
            if src:
                self.script_srcs.append(src)
            else:
                self._in_inline_script = True
        elif tag == "iframe":
            src = attributes.get("src", "").strip()
            if src:
                self.iframe_srcs.append(src)
        elif tag == "form":
            # An empty action posts back to the current URL, which is not a change.
            action = attributes.get("action", "").strip()
            if action:
                self.form_actions.append(action)
        elif tag == "link":
            rel = attributes.get("rel", "").lower()
            href = attributes.get("href", "").strip()
            if href and "stylesheet" in rel:
                self.stylesheet_hrefs.append(href)
        elif tag == "meta":
            if attributes.get("http-equiv", "").lower() == "refresh":
                content = attributes.get("content", "").strip()
                if content:
                    self.meta_refreshes.append(content)
        elif tag == "a":
            href = attributes.get("href", "").strip()
            if href:
                self.link_hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_inline_script = False

    def handle_data(self, data: str) -> None:
        if self._in_inline_script and data.strip():
            self._inline_script_parts.append(data.strip())

    @property
    def inline_scripts(self) -> list[str]:
        return self._inline_script_parts


@dataclass(frozen=True)
class StructureDiff:
    score: float
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    summary: str = ""

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed)


def extract_structure(
    html: str,
    base_url: str = "",
    allowed_hosts: Collection[str] = (),
) -> set[str]:
    """Return the set of security-relevant facts about a page.

    Relative URLs are resolved against `base_url` so the same asset does not
    read as a change just because the markup spelled it differently. Anything
    served from an allowlisted host is dropped, which is what keeps expected
    third parties (analytics, tag managers, CDNs) from firing on every check.
    """
    parser = _StructureParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # A defaced page may well be malformed; keep whatever was parsed.
        logger.debug("HTML parsing ended early", exc_info=True)

    def resolve(value: str) -> str:
        if not base_url:
            return value
        try:
            return urljoin(base_url, value)
        except ValueError:
            return value

    def add_urls(facts: set[str], kind: str, values: Iterable[str]) -> None:
        for value in values:
            resolved = resolve(value)
            if _is_allowed(_host_of(resolved), allowed_hosts):
                continue
            facts.add(f"{kind}:{resolved}")

    facts: set[str] = set()
    add_urls(facts, KIND_SCRIPT, parser.script_srcs)
    add_urls(facts, KIND_IFRAME, parser.iframe_srcs)
    add_urls(facts, KIND_FORM, parser.form_actions)
    add_urls(facts, KIND_STYLESHEET, parser.stylesheet_hrefs)

    for content in parser.meta_refreshes:
        facts.add(f"{KIND_META_REFRESH}:{content}")

    # Inline scripts are identified by a content hash: the body is often large
    # and may itself contain secrets, so only the digest is kept.
    for body in parser.inline_scripts:
        digest = hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()[:16]
        facts.add(f"{KIND_INLINE_SCRIPT}:{digest}")

    # Links are recorded per external *host*, not per URL: a news site adds
    # article links constantly, but a new outbound host is what betrays an
    # injected link farm.
    own_host = _normalise_host(_host_of(base_url)) if base_url else ""
    for href in parser.link_hrefs:
        host = _normalise_host(_host_of(resolve(href)))
        if not host or host == own_host:
            continue
        if _is_allowed(host, allowed_hosts):
            continue
        facts.add(f"{KIND_LINK_HOST}:{host}")

    return facts


def compare_structure(baseline_facts: set[str], current_facts: set[str]) -> StructureDiff:
    """Score the difference between two fact sets and describe it.

    The score is the share of facts that are not common to both, so one new
    script among fifty unchanged facts scores small. It is deliberately not the
    thing that decides an alert: STRUCTURE_CHANGE_THRESHOLD defaults to zero, so
    *any* unexplained structural change is reported and the score only conveys
    how much moved.
    """
    added = tuple(sorted(current_facts - baseline_facts))
    removed = tuple(sorted(baseline_facts - current_facts))
    union = baseline_facts | current_facts

    score = round((len(added) + len(removed)) / len(union), 6) if union else 0.0

    return StructureDiff(
        score=score,
        added=added,
        removed=removed,
        summary=summarize_structure(added, removed),
    )


def summarize_structure(added: tuple[str, ...], removed: tuple[str, ...]) -> str:
    if not added and not removed:
        return "No structural changes detected."

    parts: list[str] = []
    if added:
        parts.append(f"added {len(added)}: {_preview(added)}")
    if removed:
        parts.append(f"removed {len(removed)}: {_preview(removed)}")
    return "Structural changes — " + "; ".join(parts)


def _preview(facts: tuple[str, ...], limit: int = 3) -> str:
    shown = ", ".join(facts[:limit])
    remaining = len(facts) - limit
    return f"{shown} (+{remaining} more)" if remaining > 0 else shown
