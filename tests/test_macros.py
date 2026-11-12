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

"""Focused macro discovery and run-lifecycle tests; no live instance required."""

import asyncio
import base64
from io import BytesIO
import json
import threading
from unittest.mock import MagicMock

import pytest
from dataikuapi.utils import DataikuException

from dataiku_mcp.tools import macros


@pytest.fixture
def sdk(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(macros, "get_dss_client", lambda: client)
    return (
        client.get_project.return_value,
        client.get_project.return_value.get_macro.return_value,
    )


def call(coro):
    return json.loads(asyncio.run(coro))


def test_discovery_and_definition(sdk):
    project, macro = sdk
    definition = {
        "runnableType": "example",
        "ownerPluginId": "plugin",
        "meta": {"label": "Example"},
        "permissions": ["ADMIN"],
        "requiresGlobalAdmin": True,
        "params": [{"name": "limit", "type": "INT", "defaultValue": 5}],
        "adminParams": [{"name": "options", "params": [{"defaultValue": "example"}]}],
    }
    project.list_macros.return_value = [definition]
    macro.get_definition.return_value = definition
    result = call(macros.list_macros("PROJECT"))
    assert result["macros"]["rows"][0][:3] == ["example", "plugin", "Example"]
    result = call(macros.get_macro_definition("PROJECT", "example"))
    assert result["permissions"] == ["ADMIN"]
    assert result["params"] == definition["params"]
    assert result["adminParams"] == definition["adminParams"]


def test_run_lifecycle_is_nonblocking_and_polling_does_not_consume(sdk):
    _, macro = sdk
    main_thread = threading.get_ident()

    def start(**kwargs):
        assert threading.get_ident() != main_thread
        assert kwargs == {"params": {"limit": 5}, "admin_params": None, "wait": False}
        return "RUN"

    macro.run.side_effect = start
    started = call(macros.run_macro("PROJECT", "example", params={"limit": 5}))
    assert started == {
        "project_key": "PROJECT",
        "macro_id": "example",
        "run_id": "RUN",
        "status": "started",
    }
    macro.get_status.return_value = {"exists": True, "running": True}
    assert call(macros.get_macro_result("PROJECT", "example", "RUN"))["state"][
        "running"
    ]
    macro.get_status.return_value = {
        "exists": True,
        "running": False,
        "type": "RESULT_TABLE",
    }
    call(macros.get_macro_status("PROJECT", "example", "RUN"))
    macro.get_result.assert_not_called()
    macro.get_result.return_value = BytesIO(b'{"records":[[1]]}')
    result = call(macros.get_macro_result("PROJECT", "example", "RUN"))
    assert result["result"] == {"records": [[1]]}
    assert result["encoding"] == "json" and result["run_consumed"] is True
    assert (
        call(macros.abort_macro_run("PROJECT", "example", "RUN"))["status"]
        == "abort_requested"
    )
    macro.abort.assert_called_once_with("RUN")
    assert macro.run.call_count == 1


@pytest.mark.parametrize(
    "content,encoding", [(b"hello", "utf-8"), (b"\xff\x00", "base64")]
)
def test_result_preserves_text_and_binary(sdk, content, encoding):
    _, macro = sdk
    macro.get_status.return_value = {"exists": True, "running": False, "type": "FILE"}
    macro.get_result.return_value = BytesIO(content)
    result = call(macros.get_macro_result("PROJECT", "example", "RUN"))
    assert result["encoding"] == encoding
    decoded = (
        base64.b64decode(result["result"])
        if encoding == "base64"
        else result["result"].encode()
    )
    assert decoded == content


def test_follow_up_requires_nonempty_run_id(sdk):
    _, macro = sdk
    for tool in (
        macros.get_macro_status,
        macros.get_macro_result,
        macros.abort_macro_run,
    ):
        with pytest.raises(ValueError):
            call(tool("PROJECT", "example", " "))
    macro.run.assert_not_called()
    macro.get_status.assert_not_called()
    macro.abort.assert_not_called()


def test_failed_or_missing_run_does_not_fetch_result(sdk):
    _, macro = sdk
    macro.get_status.return_value = {
        "exists": True,
        "running": False,
        "storedError": {"message": "Input dataset is missing"},
        "resultError": {"message": "Macro execution failed"},
        "progress": {"states": [{"name": "Reading input", "cur": 1, "target": 2}]},
    }
    status = call(macros.get_macro_status("PROJECT", "example", "RUN"))
    assert status["state"]["error_reported"] is True
    assert status["state"]["storedError"] == {"message": "Input dataset is missing"}
    assert status["state"]["resultError"] == {"message": "Macro execution failed"}
    assert status["state"]["progress"] == macro.get_status.return_value["progress"]
    result = call(macros.get_macro_result("PROJECT", "example", "RUN"))
    assert result == status
    macro.get_status.return_value = {"exists": False}
    assert (
        call(macros.get_macro_result("PROJECT", "example", "RUN"))["state"]["exists"]
        is False
    )
    macro.get_result.assert_not_called()


def test_sdk_errors_are_safe_and_warn_against_duplicate_execution(sdk):
    _, macro = sdk
    macro.run.side_effect = RuntimeError("credential=secret")
    with pytest.raises(RuntimeError, match="may have started a run") as error:
        call(macros.run_macro("PROJECT", "example"))
    assert "secret" not in str(error.value)
    macro.get_status.side_effect = RuntimeError("credential=secret")
    with pytest.raises(RuntimeError, match="do not restart") as error:
        call(macros.get_macro_status("PROJECT", "example", "RUN"))
    assert "secret" not in str(error.value)


def test_result_preserves_execution_error_when_status_has_no_error(sdk):
    _, macro = sdk
    macro.get_status.return_value = {"exists": True, "running": False}

    def consume_and_fail(run_id):
        macro.get_status.return_value = {"exists": False}
        raise DataikuException("Python macro failed: ValueError: missing input column")

    macro.get_result.side_effect = consume_and_fail
    with pytest.raises(RuntimeError) as error:
        call(macros.get_macro_result("PROJECT", "example", "RUN"))

    message = str(error.value)
    assert "Python macro failed: ValueError: missing input column" in message
    assert "may already have removed the run" in message
    assert "do not restart the macro" in message
    macro.get_result.assert_called_once_with("RUN")
    macro.get_status.assert_called_once_with("RUN")
    macro.run.assert_not_called()


def test_result_failure_is_preserved_without_claiming_execution_failure(sdk):
    _, macro = sdk
    macro.get_status.return_value = {
        "exists": True,
        "running": False,
        "type": "JSON_OBJECT",
    }
    payload = {"ok": False, "error": "Python code environment does not exist"}
    macro.get_result.return_value = BytesIO(json.dumps(payload).encode())

    status = call(macros.get_macro_status("PROJECT", "example", "RUN"))
    assert status["state"]["error_reported"] is False
    assert "failed" not in status["state"]
    result = call(macros.get_macro_result("PROJECT", "example", "RUN"))
    assert result["state"] == status["state"]
    assert result["result"] == payload
    assert result["encoding"] == "json"
    assert result["run_consumed"] is True
