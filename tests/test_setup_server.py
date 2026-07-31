import pytest

from dataiku_mcp.setup_server import _page, _validate_form

NORMALIZED_URLS = (
    (
        "https://sandbox.se-platform.dataiku-sandbox.io",
        "https://sandbox.se-platform.dataiku-sandbox.io",
    ),
    (
        "https://sandbox.se-platform.dataiku-sandbox.io/",
        "https://sandbox.se-platform.dataiku-sandbox.io",
    ),
    (
        "https://sandbox.se-platform.dataiku-sandbox.io/home",
        "https://sandbox.se-platform.dataiku-sandbox.io",
    ),
    (
        "https://sandbox.se-platform.dataiku-sandbox.io/home/",
        "https://sandbox.se-platform.dataiku-sandbox.io",
    ),
    (
        "https://sandbox.se-platform.dataiku-sandbox.io/flow",
        "https://sandbox.se-platform.dataiku-sandbox.io",
    ),
    (
        "https://sandbox.se-platform.dataiku-sandbox.io/projects/DEMO/flow"
        "?view=all#selection",
        "https://sandbox.se-platform.dataiku-sandbox.io",
    ),
    ("http://localhost:11200/home", "http://localhost:11200"),
    ("https://[::1]:11200/home", "https://[::1]:11200"),
)

INVALID_URLS = (
    "ftp://example.com/projects",
    "https:///projects",
    "https://user@example.com",
    "https://example.com:abc/home",
    "https://example.com:/home",
    "https://example.com:0/home",
    "https://example.com:99999/home",
    "https://example.com\\home",
    "https://example.com/a path",
    "https://example.com/\x00flow",
    "https://[::1/home",
)


def _form(url: str) -> dict[str, list[str]]:
    return {
        "name": ["sandbox"],
        "url": [url],
        "api_key": ["secret"],
        "description": [""],
    }


@pytest.mark.parametrize(
    ("submitted_url", "saved_url"),
    NORMALIZED_URLS,
)
def test_validate_form_normalizes_dataiku_page_urls(submitted_url, saved_url):
    assert _validate_form(_form(submitted_url))["url"] == saved_url


@pytest.mark.parametrize("url", INVALID_URLS)
def test_validate_form_rejects_malformed_or_unsafe_urls(url):
    with pytest.raises(ValueError):
        _validate_form(_form(url))


def test_setup_page_explains_instance_url():
    page = _page()

    assert "Enter the URL of your Dataiku instance." in page
