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

"""Plugin future follow-up must not expose settings or Git error output."""

import asyncio
import json
from unittest.mock import patch

import pytest
from dataikuapi import DSSClient
from dataikuapi.utils import DataikuException

from dataiku_mcp.tools import jobs
from tests.utils.fakes import FakeContext


@pytest.mark.parametrize("fetch_result", [False, True])
@pytest.mark.parametrize("failure", [False, True])
def test_plugin_future_redacts_logs_errors_and_settings(fetch_result, failure):
    client = DSSClient("https://synthetic.example.com", "synthetic-key")

    def response(*args, **kwargs):
        return {
            "jobId": "F",
            "alive": False,
            "hasResult": True,
            "payload": {"action": "plugin_install", "targets": ["SYNTHETIC_SECRET"]},
            "log": "SYNTHETIC_SECRET",
            "result": {
                "success": not failure,
                "needsReload": True,
                "pluginDesc": {"desc": {"id": "fixture", "version": "1.0"}},
                "settings": {"token": "SYNTHETIC_SECRET"},
                **(
                    {
                        "installationError": {
                            "message": "https://user:SYNTHETIC_SECRET@example.com/repo"
                        }
                    }
                    if failure
                    else {}
                ),
            },
        }

    with (
        patch.object(client, "_perform_json", side_effect=response),
        patch.object(jobs, "get_dss_client", return_value=client),
    ):
        result = json.loads(
            asyncio.run(
                jobs.get_future_status("F", FakeContext(), fetch_result=fetch_result)
            )
        )
    assert "SYNTHETIC_SECRET" not in json.dumps(result)
    receipt = result["state"]["result"]
    assert receipt["success"] is not failure
    assert receipt["pluginDesc"]["desc"]["id"] == "fixture"
    assert ("error" in receipt) is failure


@pytest.mark.parametrize("stage", ["peek", "get"])
def test_future_transport_error_cannot_expose_git_output(stage):
    client = DSSClient("https://synthetic.example.com", "synthetic-key")

    def response(*args, **kwargs):
        if stage == "peek" or not kwargs["params"]["peek"]:
            raise DataikuException("Git failed: SYNTHETIC_SECRET")
        return {"payload": {"action": "plugin_install"}}

    with (
        patch.object(client, "_perform_json", side_effect=response),
        patch.object(jobs, "get_dss_client", return_value=client),
        pytest.raises(RuntimeError) as error,
    ):
        asyncio.run(jobs.get_future_status("F", FakeContext(), fetch_result=True))
    assert "SYNTHETIC_SECRET" not in str(error.value)


def test_other_future_results_are_preserved():
    client = DSSClient("https://synthetic.example.com", "synthetic-key")
    state = {"payload": {"action": "other"}, "result": {"value": 42}}
    with (
        patch.object(client, "_perform_json", return_value=state),
        patch.object(jobs, "get_dss_client", return_value=client),
    ):
        result = json.loads(
            asyncio.run(jobs.get_future_status("F", FakeContext(), fetch_result=True))
        )
    assert result["state"] == state
