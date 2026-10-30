# Copyright 2026 Dataiku SAS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import asyncio
import json
from types import SimpleNamespace

import pytest

from dataiku_mcp.config import stdio
from dataiku_mcp.tools import deployer
from tests.test_instance_policy import _instance
from tests.test_operations import _call

SECRET = "do-not-return-this-secret"


def test_deployer_future_status_does_not_fetch_results(monkeypatch):
    monkeypatch.setattr(stdio, "_current_instance", _instance("deployer"))
    captured = []

    def perform(method, path, **kwargs):
        captured.append((method, path, kwargs))
        return {"hasResult": True, "result": {"password": SECRET}}

    monkeypatch.setattr(
        deployer, "get_dss_client", lambda: SimpleNamespace(_perform_json=perform)
    )
    result = asyncio.run(
        _call(
            "run_read_operation",
            operation_id="deployer.get_future_status",
            arguments={"future_id": "future"},
        )
    )
    assert result["result"]["state"] == {"hasResult": True}
    assert captured == [("GET", "/futures/future", {"params": {"peek": True}})]


@pytest.mark.parametrize(
    "value",
    [
        {"apiKeys": [SECRET]},
        {"passwords": [SECRET]},
        {"url": "https://user:" + SECRET + "@example.com/path?api_key=" + SECRET},
    ],
)
def test_operation_redaction_covers_secret_containers_and_url_credentials(value):
    from dataiku_mcp.tools.utils.redaction import redact_sensitive_data

    assert SECRET not in json.dumps(redact_sensitive_data(value))
