from dataiku_mcp.setup_server import DATAIKU_BIRD_SVG, _page, _success_page


def test_setup_page_uses_dataiku_branding_and_accessible_states():
    page = _page(error="Check the URL.")

    assert DATAIKU_BIRD_SVG in page
    assert '<header class="brand">' in page
    assert "Connect to Dataiku" in page
    assert "Your credentials stay on this machine." in page
    assert 'role="alert"' in page
    assert "Check the URL." in page
    assert "prefers-reduced-motion:reduce" in page
    assert "gradient" not in page


def test_success_page_uses_dataiku_branding_and_escapes_instance_name():
    page = _success_page("<production>")

    assert DATAIKU_BIRD_SVG in page
    assert "Dataiku is connected" in page
    assert "&lt;production&gt;" in page
    assert "<production>" not in page
