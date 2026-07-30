import re

import pytest

from dataiku_mcp.setup_server import INSTANCE_URL_PATTERN, _page, _validate_form

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
    ("http://localhost:11200/home", "http://localhost:11200"),
    ("https://[::1]:11200/home", "https://[::1]:11200"),
)

PATTERN_INVALID_URLS = (
    "https://example.com/projects",
    "https://example.com/home/projects",
    "https://example.com/?from=setup",
    "https://example.com/#section",
    "https://user@example.com",
    "https://example.com:abc/home",
    "https://example.com/home;extra",
    "https://example.com\\home",
)
SERVER_INVALID_URLS = (
    *PATTERN_INVALID_URLS,
    "https://example.com:99999/home",
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
def test_validate_form_normalizes_instance_landing_urls(submitted_url, saved_url):
    assert _validate_form(_form(submitted_url))["url"] == saved_url


@pytest.mark.parametrize("url", SERVER_INVALID_URLS)
def test_validate_form_rejects_non_instance_root_urls(url):
    with pytest.raises(ValueError):
        _validate_form(_form(url))


def test_setup_page_includes_url_pattern_and_normalization_help():
    page = _page()

    assert f'pattern="{INSTANCE_URL_PATTERN}"' in page
    assert "The saved URL will not include /home or a trailing slash." in page


@pytest.mark.parametrize(
    "url",
    [submitted_url for submitted_url, _ in NORMALIZED_URLS],
)
def test_instance_url_pattern_accepts_supported_urls(url):
    assert re.fullmatch(INSTANCE_URL_PATTERN, url)


@pytest.mark.parametrize("url", PATTERN_INVALID_URLS)
def test_instance_url_pattern_rejects_unsupported_urls(url):
    assert re.fullmatch(INSTANCE_URL_PATTERN, url) is None
