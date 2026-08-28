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

"""Tests for complete MIRA public API access."""

import asyncio
import json

import pytest

from dataiku_mcp.tools import mira
from tests.utils.fakes import FakeContext


EXPECTED_OPERATION_IDS = {
    "abort_agent_operation",
    "abort_infra_operation",
    "compute_risk_taxonomy_replacement_impact",
    "create_business_kpi",
    "create_external_agent",
    "create_infra",
    "create_mira_agent",
    "create_topic_family",
    "delete_business_kpi",
    "delete_infra",
    "delete_mira_agent",
    "delete_mira_tag",
    "delete_topic_family",
    "download_agent_risk_evidence",
    "fetch_agent_logs",
    "fetch_agent_operational_metrics",
    "generate_agent_briefing",
    "get_agent_operation",
    "get_agent_operation_result",
    "get_agent_risk_assessment",
    "get_business_kpi",
    "get_default_risk_taxonomy",
    "get_infra",
    "get_infra_operation",
    "get_infra_operation_result",
    "get_infra_settings",
    "get_mira_agent",
    "get_mira_agent_history",
    "get_mira_agent_metrics",
    "get_mira_agent_settings",
    "get_mira_agent_status",
    "get_mira_agent_topic_modeling",
    "get_mira_agent_uptime_results",
    "get_mira_settings",
    "get_risk_exposure",
    "get_risk_taxonomy",
    "get_topic_family",
    "list_agent_operations",
    "list_business_kpis",
    "list_infra_operations",
    "list_infras",
    "list_mira_agents",
    "list_mira_tags",
    "list_topic_families",
    "remove_agent_risk_sign_off",
    "rename_mira_tag",
    "run_infra_uptime_tests",
    "scan_infra",
    "setup_agent_log_fetch_dataset",
    "sign_off_agent_risk_assessment",
    "update_agent_risk_assessment",
    "update_business_kpi",
    "update_infra_settings",
    "update_mira_agent_settings",
    "update_mira_settings",
    "update_mira_tag",
    "update_risk_taxonomy",
    "update_topic_family",
}


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content
        self.headers = {
            "Content-Type": "application/pdf",
            "Content-Disposition": 'attachment; filename="evidence.pdf"',
        }
        self.closed = False

    def iter_content(self, chunk_size: int):
        assert chunk_size > 0
        yield self.content[:3]
        yield self.content[3:]

    def close(self):
        self.closed = True


class FakeMiraClient:
    def __init__(self):
        self.json_calls = []
        self.raw_calls = []
        self.response = FakeResponse(b"evidence")

    def _perform_json(self, method, path, **kwargs):
        files = kwargs.get("files") or []
        self.json_calls.append(
            {
                "method": method,
                "path": path,
                "params": kwargs.get("params"),
                "body": kwargs.get("body"),
                "raw_body": kwargs.get("raw_body"),
                "files": [
                    (field, metadata[0], metadata[1].read())
                    for field, metadata in files
                ],
            }
        )
        return {"ok": True}

    def _perform_raw(self, method, path, **kwargs):
        self.raw_calls.append(
            {"method": method, "path": path, "params": kwargs.get("params")}
        )
        return self.response


def _call(coro):
    return json.loads(asyncio.run(coro))


def test_operation_catalog_pins_every_public_controller_operation():
    assert set(mira.MIRA_OPERATIONS) == EXPECTED_OPERATION_IDS
    assert len(mira.MIRA_OPERATIONS) == 58
    assert {operation.domain for operation in mira.MIRA_OPERATIONS.values()} == {
        "infrastructures",
        "agents",
        "operations",
        "risk",
        "settings",
        "tags",
    }
    assert all(
        operation.path.startswith("/mira/")
        for operation in mira.MIRA_OPERATIONS.values()
    )
    assert (
        len(
            {
                (operation.method, operation.path)
                for operation in mira.MIRA_OPERATIONS.values()
            }
        )
        == 58
    )


def test_capabilities_can_be_filtered_without_hiding_input_shapes():
    result = _call(mira.get_mira_api_capabilities(FakeContext(), "tags"))

    assert result["count"] == 4
    assert {operation["operation_id"] for operation in result["operations"]} == {
        "list_mira_tags",
        "update_mira_tag",
        "rename_mira_tag",
        "delete_mira_tag",
    }
    update = next(
        operation
        for operation in result["operations"]
        if operation["operation_id"] == "update_mira_tag"
    )
    assert update["method"] == "PUT"
    assert update["path_params"] == ["tag_name"]
    assert update["body"] == "required"


def test_json_calls_use_catalog_method_encoded_path_query_and_body(monkeypatch):
    client = FakeMiraClient()
    monkeypatch.setattr(mira, "get_dss_client", lambda: client)

    result = _call(
        mira.call_mira_api(
            "update_mira_agent_settings",
            FakeContext(),
            path_params={"infra_id": "bedrock/demo", "agent_id": "agent one"},
            body={"expectedRevision": "rev", "displayName": "Updated"},
        )
    )

    assert result == {"ok": True}
    assert client.json_calls == [
        {
            "method": "PUT",
            "path": "/mira/infras/bedrock%2Fdemo/agents/agent%20one/settings",
            "params": None,
            "body": {"expectedRevision": "rev", "displayName": "Updated"},
            "raw_body": None,
            "files": [],
        }
    ]


def test_read_call_passes_only_documented_query_parameters(monkeypatch):
    client = FakeMiraClient()
    monkeypatch.setattr(mira, "get_dss_client", lambda: client)

    _call(
        mira.call_mira_api(
            "get_mira_agent_metrics",
            FakeContext(),
            path_params={"infra_id": "infra", "agent_id": "agent"},
            query_params={"family": "performance", "timezone": "UTC"},
        )
    )

    assert client.json_calls[0]["method"] == "GET"
    assert client.json_calls[0]["params"] == {
        "family": "performance",
        "timezone": "UTC",
    }


def test_multipart_risk_assessment_pairs_evidence_ids_and_files(monkeypatch, tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("one")
    second.write_text("two")
    client = FakeMiraClient()
    monkeypatch.setattr(mira, "get_dss_client", lambda: client)

    _call(
        mira.call_mira_api(
            "update_agent_risk_assessment",
            FakeContext(),
            path_params={"infra_id": "infra", "agent_id": "agent"},
            form_params={
                "assessment": '{"items":[]}',
                "expectedRevision": "rev",
                "documentEvidenceIds": ["evidence-1", "evidence-2"],
            },
            file_paths=[str(first), str(second)],
        )
    )

    call = client.json_calls[0]
    assert call["method"] == "PUT"
    assert call["raw_body"]["expectedRevision"] == "rev"
    assert call["files"] == [
        ("documents", "first.txt", b"one"),
        ("documents", "second.txt", b"two"),
    ]


def test_binary_evidence_download_is_explicit_and_non_overwriting(
    monkeypatch, tmp_path
):
    client = FakeMiraClient()
    monkeypatch.setattr(mira, "get_dss_client", lambda: client)
    destination = tmp_path / "evidence.pdf"

    result = _call(
        mira.call_mira_api(
            "download_agent_risk_evidence",
            FakeContext(),
            path_params={
                "infra_id": "infra",
                "agent_id": "agent",
                "evidence_id": "evidence",
            },
            output_path=str(destination),
        )
    )

    assert destination.read_bytes() == b"evidence"
    assert result["output_path"] == str(destination)
    assert result["size_bytes"] == 8
    assert result["content_type"] == "application/pdf"
    assert client.response.closed is True
    with pytest.raises(FileExistsError, match="overwrite=true"):
        _call(
            mira.call_mira_api(
                "download_agent_risk_evidence",
                FakeContext(),
                path_params={
                    "infra_id": "infra",
                    "agent_id": "agent",
                    "evidence_id": "evidence",
                },
                output_path=str(destination),
            )
        )


@pytest.mark.parametrize(
    ("operation_id", "kwargs", "message"),
    [
        ("missing", {}, "Unknown MIRA operation"),
        ("get_infra", {}, "Missing path parameters"),
        (
            "get_infra",
            {"path_params": {"infra_id": "infra"}, "query_params": {"guess": 1}},
            "Unexpected query parameters",
        ),
        ("create_infra", {}, "requires a JSON body"),
        (
            "list_infras",
            {"body": {"unexpected": True}},
            "does not accept a JSON body",
        ),
    ],
)
def test_invalid_or_speculative_calls_fail_before_network(
    monkeypatch, operation_id, kwargs, message
):
    client = FakeMiraClient()
    monkeypatch.setattr(mira, "get_dss_client", lambda: client)

    with pytest.raises(ValueError, match=message):
        _call(mira.call_mira_api(operation_id, FakeContext(), **kwargs))

    assert client.json_calls == []
    assert client.raw_calls == []
