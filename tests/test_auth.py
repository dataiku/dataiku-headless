"""Authentication tests for Dataiku client construction."""

import pytest

from dataiku_mcp.config import DSSInstance
from dataiku_mcp.tools.utils import auth


def _instance(api_key: str, no_check_certificate: bool = False) -> DSSInstance:
    return DSSInstance(
        name="test-instance",
        url="https://dss.example.com",
        api_key=api_key,
        no_check_certificate=no_check_certificate,
        source="test",
    )


def test_get_dss_client_requires_selected_instance_api_key(monkeypatch):
    monkeypatch.setattr(auth.config, "get_current_instance", lambda: _instance(""))

    with pytest.raises(ValueError):
        auth.get_dss_client()
