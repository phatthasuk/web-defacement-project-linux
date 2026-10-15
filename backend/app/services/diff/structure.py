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
KIND_IFRAME_SRCDOC = "iframe-srcdoc"
KIND_BASE = "base"
KIND_FORM = "form"
KIND_STYLESHEET = "stylesheet"
KIND_META_REFRESH = "meta-refresh"
KIND_LINK_HOST = "link-host"
KIND_EVENT_HANDLER = "event-handler"
KIND_JAVASCRIPT_URL = "javascript-url"
KIND_FORMACTION = "formaction"
_EXECUTABLE_URL_ATTRIBUTES = {"href", "src", "action", "formaction", "xlink:href"}

# Script classification follows the HTML "prepare the script element" rules: the
# same body is inert as `text/plain` and live as `text/javascript`.
SCRIPT_CLASSIC = "classic"
SCRIPT_MODULE = "module"
SCRIPT_IMPORTMAP = "importmap"
SCRIPT_SPECULATIONRULES = "speculationrules"
SCRIPT_INERT = "inert"
_JAVASCRIPT_MIME_ESSENCES = frozenset(
    {
        "application/ecmascript",
        "application/javascript",
        "application/x-ecmascript",
        "application/x-javascript",
        "text/ecmascript",
        "text/javascript",
        "text/javascript1.0",
        "text/javascript1.1",
        "text/javascript1.2",
        "text/javascript1.3",
        "text/javascript1.4",
        "text/javascript1.5",
        "text/jscript",
        "text/livescript",
        "text/x-ecmascript",
        "text/x-javascript",
    }
)
_URL_STRIP_CHARS = "".join(chr(code) for code in range(0x21))  # C0 controls and space
_URL_REMOVED_CHARS = str.maketrans("", "", "\t\n\r")


def _normalise_url_value(value: str) -> str:
    """Normalise an attribute value the way a browser's URL parser does.

    Chromium drops leading/trailing C0 controls and spaces and removes every
    ASCII tab and newline anywhere in the string, so `java<TAB>script:` is still
    a `javascript:` URL.
    """
    return value.strip(_URL_STRIP_CHARS).translate(_URL_REMOVED_CHARS)


def _is_javascript_url(value: str) -> bool:
    return _normalise_url_value(value).lower().startswith("javascript:")


def classify_script(attributes: dict[str, str]) -> str:
    """Classify a `<script>` according to its HTML script type."""
    if "type" in attributes:
        type_string = attributes["type"]
    elif attributes.get("language", ""):
        type_string = f"text/{attributes['language']}"
    else:
        type_string = ""
    if not type_string:
        return SCRIPT_CLASSIC
    # A JavaScript MIME essence match is an exact type string match, ignoring
    # ASCII case. Parameters make it a data block in an HTML script type value.
    if type_string.strip(_URL_STRIP_CHARS).lower() in _JAVASCRIPT_MIME_ESSENCES:
        return SCRIPT_CLASSIC
    token = type_string.lower()
    if token == SCRIPT_MODULE:
        return SCRIPT_MODULE
    if token == SCRIPT_IMPORTMAP:
        return SCRIPT_IMPORTMAP
    if token == SCRIPT_SPECULATIONRULES:
        return SCRIPT_SPECULATIONRULES
    return SCRIPT_INERT


def _is_form_submitter(tag: str, attributes: dict[str, str]) -> bool:
    """Return whether a button/input type can use its `formaction` attribute."""
    control_type = attributes.get("type", "").lower()
    if tag == "button":
        # Missing and invalid button types use the submit state.
        return control_type not in {"button", "reset"}
    # An input's missing or invalid type defaults to text; only these two
    # states are submit buttons and honor `formaction`.
    return control_type in {"submit", "image"}


def _script_kind_label(kind: str) -> str:
    return "" if kind == SCRIPT_CLASSIC else f"[{kind}]"


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
        self.script_srcs: list[tuple[str, str]] = []
        self.form_submitters: list[str] = []
        self.iframe_srcs: list[str] = []
        self.iframe_srcdocs: list[str] = []
        self.base_href: str | None = None
        self.form_actions: list[str] = []
        self.stylesheet_hrefs: list[str] = []
        self.meta_refreshes: list[str] = []
        self.link_hrefs: list[str] = []
        self.executable_attributes: list[tuple[str, str, str]] = []
        self.inline_scripts: list[tuple[str, str]] = []
        self._current_inline_chunks: list[str] = []
        self._current_inline_kind = SCRIPT_CLASSIC
        self._in_inline_script = False

    def _flush_inline_script(self) -> None:
        if self._in_inline_script:
            body = "".join(self._current_inline_chunks).strip()
            if body:
                self.inline_scripts.append((self._current_inline_kind, body))
            self._current_inline_chunks = []
            self._in_inline_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): (value or "") for name, value in attrs}

        for name, value in attributes.items():
            if name.startswith("on") and len(name) > 2 and value.strip():
                self.executable_attributes.append((tag.lower(), name, value.strip()))
            elif name in _EXECUTABLE_URL_ATTRIBUTES and _is_javascript_url(value):
                # Browsers strip tabs/newlines from URLs before parsing, so do the
                # same; the body keeps its inner spaces because they can matter.
                normalized = _normalise_url_value(value)[len("javascript:") :]
                self.executable_attributes.append((tag.lower(), name, f"javascript:{normalized}"))

        if tag == "script":
            kind = classify_script(attributes)
            src = attributes.get("src", "").strip()
            if src:
                self.script_srcs.append((kind, src))
            else:
                self._flush_inline_script()
                self._in_inline_script = True
                self._current_inline_kind = kind
                self._current_inline_chunks = []
        elif tag == "iframe":
            if "srcdoc" in attributes:
                self.iframe_srcdocs.append(attributes["srcdoc"])
            src = attributes.get("src", "").strip()
            if src:
                self.iframe_srcs.append(src)
        elif tag == "base":
            # The first base with an href wins, even if that href is empty.
            if self.base_href is None and "href" in attributes:
                self.base_href = attributes["href"].strip()
        elif tag == "form":
            # An empty action posts back to the current URL, which is not a change.
            action = attributes.get("action", "").strip()
            if action:
                self.form_actions.append(action)
        elif tag in ("button", "input") and _is_form_submitter(tag, attributes):
            # `formaction` overrides the owning form's action for that submit
            # control. An explicit empty value targets the document URL, so keep
            # it distinct from an absent attribute and from the form's action.
            if "formaction" in attributes:
                formaction = attributes["formaction"].strip()
                if not _is_javascript_url(formaction):
                    self.form_submitters.append(formaction)
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
            self._flush_inline_script()

    def handle_data(self, data: str) -> None:
        if self._in_inline_script:
            self._current_inline_chunks.append(data)

    def close(self) -> None:
        super().close()
        self._flush_inline_script()


@dataclass(frozen=True)
class StructureDiff:
    score: float
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    summary: str = ""
    available: bool = True

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed)


def extract_structure(
    html: str,
    base_url: str = "",
    allowed_hosts: Collection[str] = (),
) -> set[str]:
    """Return the set of security-relevant facts about a page.

    Relative URLs are resolved against the first document base href (itself
    resolved against `base_url`), or `base_url` when absent, so an asset does not
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

    effective_base = base_url
    if parser.base_href is not None:
        try:
            effective_base = urljoin(base_url, parser.base_href)
        except ValueError:
            pass

    def resolve(value: str) -> str:
        if not effective_base:
            return value
        try:
            return urljoin(effective_base, value)
        except ValueError:
            return value

    def add_urls(facts: set[str], kind: str, values: Iterable[str]) -> None:
        for value in values:
            resolved = resolve(value)
            if _is_allowed(_host_of(resolved), allowed_hosts):
                continue
            facts.add(f"{kind}:{resolved}")

    facts: set[str] = set()
    if parser.base_href is not None:
        # Track the base independently, including changes on allowlisted hosts.
        facts.add(f"{KIND_BASE}:{effective_base}")
    for kind, src in parser.script_srcs:
        add_urls(facts, f"{KIND_SCRIPT}{_script_kind_label(kind)}", [src])
    add_urls(facts, KIND_IFRAME, parser.iframe_srcs)
    add_urls(facts, KIND_FORM, parser.form_actions)
    for formaction in parser.form_submitters:
        # An explicit empty formaction resolves to the current document URL,
        # whereas a non-empty value resolves against the effective base URL.
        resolved = base_url if not formaction else resolve(formaction)
        if not _is_allowed(_host_of(resolved), allowed_hosts):
            facts.add(f"{KIND_FORMACTION}:{resolved}")
    add_urls(facts, KIND_STYLESHEET, parser.stylesheet_hrefs)

    # srcdoc overrides src and may execute even in an invisible iframe. Hash
    # the decoded attribute verbatim; do not expose inline content in summaries
    # or suppress it because the iframe's fallback src is allowlisted.
    for body in parser.iframe_srcdocs:
        digest = hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()
        facts.add(f"{KIND_IFRAME_SRCDOC}:{digest}")

    for content in parser.meta_refreshes:
        facts.add(f"{KIND_META_REFRESH}:{content}")

    # Inline scripts are identified by a content hash: the body is often large
    # and may itself contain secrets, so only the digest is kept.
    # The script kind is part of the fact so that flipping a block between inert
    # and executable is a change even when the body is byte-for-byte identical.
    for kind, body in parser.inline_scripts:
        digest = hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()[:16]
        facts.add(f"{KIND_INLINE_SCRIPT}{_script_kind_label(kind)}:{digest}")

    # Handler bodies and javascript: URLs can execute without changing visible
    # text or pixels. Hash content so summaries never expose inline code.
    for tag, attribute, value in parser.executable_attributes:
        digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:16]
        kind = KIND_EVENT_HANDLER if attribute.startswith("on") else KIND_JAVASCRIPT_URL
        facts.add(f"{kind}:{tag}.{attribute}:{digest}")

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
