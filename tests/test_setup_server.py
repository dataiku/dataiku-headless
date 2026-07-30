import pytest

from dataiku_mcp.setup_server import INSTANCE_URL_PATTERN, _page, _validate_form


def _form(url: str) -> dict[str, list[str]]:
    return {
        "name": ["sandbox"],
        "url": [url],
        "api_key": ["secret"],
        "description": [""],
    }


@pytest.mark.parametrize(
    ("submitted_url", "saved_url"),
    [
        (
            "https://chrispersonal.se-platform.dataiku-sandbox.io",
            "https://chrispersonal.se-platform.dataiku-sandbox.io",
        ),
        (
            "https://chrispersonal.se-platform.dataiku-sandbox.io/",
            "https://chrispersonal.se-platform.dataiku-sandbox.io",
        ),
        (
            "https://chrispersonal.se-platform.dataiku-sandbox.io/home",
            "https://chrispersonal.se-platform.dataiku-sandbox.io",
        ),
        (
            "https://chrispersonal.se-platform.dataiku-sandbox.io/home/",
            "https://chrispersonal.se-platform.dataiku-sandbox.io",
        ),
        ("http://localhost:11200/home", "http://localhost:11200"),
    ],
)
def test_validate_form_normalizes_instance_landing_urls(submitted_url, saved_url):
    assert _validate_form(_form(submitted_url))["url"] == saved_url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/projects",
        "https://example.com/home/projects",
        "https://example.com/?from=setup",
        "https://example.com/#section",
        "https://user@example.com",
    ],
)
def test_validate_form_rejects_non_instance_root_urls(url):
    with pytest.raises(ValueError):
        _validate_form(_form(url))


def test_setup_page_url_pattern_matches_server_validation():
    page = _page()

    assert f'pattern="{INSTANCE_URL_PATTERN}"' in page
    assert "The saved URL will not include /home or a trailing slash." in page
