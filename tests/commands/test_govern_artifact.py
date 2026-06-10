"""Tests for dku govern-artifact commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_artifact_list(patch_client):
    result = runner.invoke(app, ["govern", "artifact", "list"])
    assert result.exit_code == 0
    assert "ar.5" in result.output
    assert "Test Project" in result.output


def test_artifact_list_json(patch_client):
    result = runner.invoke(app, ["govern", "artifact", "list", "-o", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["id"] == "ar.5"
    assert data[0]["blueprint"] == "bp.system.govern_project"


def test_artifact_list_with_blueprint_filter(patch_client):
    result = runner.invoke(
        app,
        ["govern", "artifact", "list", "--blueprint", "bp.system.govern_project"],
    )
    assert result.exit_code == 0
    assert "ar.5" in result.output


def test_artifact_list_with_page_size(patch_client):
    result = runner.invoke(app, ["govern", "artifact", "list", "--page-size", "10"])
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    req = gov.new_artifact_search_request.return_value
    req.fetch_next_batch.assert_called_with(page_size=10)


def test_artifact_list_with_field_filter(patch_client):
    """--field KEY=VALUE adds a field-value filter and surfaces the value."""
    result = runner.invoke(
        app,
        [
            "govern",
            "artifact",
            "list",
            "-b",
            "bp.system.govern_project",
            "--field",
            "sensitive_data=Yes",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    # matched field value is surfaced as a column
    assert data[0]["sensitive_data"] == "Yes"
    # the EQUALS field-value filter reached the search query
    gov = patch_client.get_govern_client()
    query = gov.new_artifact_search_request.call_args.args[0]
    built = [f.build() for f in query.artifact_filters]
    assert any(
        f.get("type") == "field"
        and f.get("fieldId") == "sensitive_data"
        and f.get("condition") == "Yes"
        and f.get("conditionType") == "EQUALS"
        for f in built
    )


def test_artifact_list_field_filter_requires_equals(patch_client):
    """--field without '=' is a prescriptive error, not a silent miss."""
    result = runner.invoke(
        app,
        ["govern", "artifact", "list", "--field", "sensitive_data"],
    )
    assert result.exit_code != 0
    assert "expected KEY=VALUE" in result.output


def test_artifact_get(patch_client):
    result = runner.invoke(app, ["govern", "artifact", "get", "ar.5"])
    assert result.exit_code == 0
    assert "ar.5" in result.output


def test_artifact_get_json(patch_client):
    result = runner.invoke(app, ["govern", "artifact", "get", "ar.5", "-o", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "ar.5"
    assert data["name"] == "Test Project"


def test_artifact_create(patch_client):
    defn = json.dumps(
        {
            "name": "New Artifact",
            "blueprintVersionId": {"blueprintId": "bp.swag", "versionId": "bv.1"},
        }
    )
    result = runner.invoke(app, ["govern", "artifact", "create", "--definition", defn])
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.create_artifact.assert_called_once()


def test_artifact_delete_requires_confirm(patch_client):
    result = runner.invoke(app, ["govern", "artifact", "delete", "ar.5"])
    combined = result.output + (result.stderr or "")
    assert result.exit_code == 77
    assert "blocked" in combined.lower()


def test_artifact_delete_with_confirm(patch_client):
    result = runner.invoke(app, ["govern", "artifact", "delete", "ar.5", "--confirm"])
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.get_artifact.return_value.delete.assert_called_once()


def test_artifact_set_definition(patch_client):
    new_def = json.dumps({"name": "Updated", "fields": {"description": "New desc"}})
    result = runner.invoke(
        app,
        ["govern", "artifact", "set-definition", "ar.5", "--definition", new_def],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.get_artifact.return_value.get_definition.return_value.save.assert_called_once()


def test_artifact_create_ergonomic(patch_client):
    """Test --blueprint + --name + --field flags (no raw JSON)."""
    result = runner.invoke(
        app,
        [
            "govern",
            "artifact",
            "create",
            "-b",
            "bp.system.govern_project",
            "-n",
            "My Project",
            "-f",
            "description=A test project",
            "-f",
            "cost_rating=High",
        ],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    call_args = gov.create_artifact.call_args[0][0]
    assert call_args["name"] == "My Project"
    assert call_args["fields"]["description"] == "A test project"
    assert call_args["fields"]["cost_rating"] == "High"
    assert call_args["blueprintVersionId"]["blueprintId"] == "bp.system.govern_project"


def test_artifact_create_ergonomic_json_array_field(patch_client):
    """Test --field with JSON array value for list fields."""
    result = runner.invoke(
        app,
        [
            "govern",
            "artifact",
            "create",
            "-b",
            "bp.system.govern_project",
            "-n",
            "Test",
            "-f",
            'countries=["France","Germany"]',
        ],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    call_args = gov.create_artifact.call_args[0][0]
    assert call_args["fields"]["countries"] == ["France", "Germany"]


def test_artifact_create_requires_blueprint_or_definition(patch_client):
    """Test error when neither --blueprint nor --definition provided."""
    result = runner.invoke(app, ["govern", "artifact", "create"])
    assert result.exit_code != 0
    output = result.output + (result.stderr or "")
    assert "blueprint" in output.lower() or "definition" in output.lower()


def test_artifact_set_field(patch_client):
    """Test set-field updates a single field."""
    result = runner.invoke(
        app,
        ["govern", "artifact", "set-field", "ar.5", "cost_rating", "High"],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    defn = gov.get_artifact.return_value.get_definition.return_value
    assert defn.definition["fields"]["cost_rating"] == "High"
    defn.save.assert_called()


def test_artifact_set_field_json_array(patch_client):
    """Test set-field with JSON array value."""
    result = runner.invoke(
        app,
        [
            "govern",
            "artifact",
            "set-field",
            "ar.5",
            "countries",
            '["France","Germany"]',
        ],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    defn = gov.get_artifact.return_value.get_definition.return_value
    assert defn.definition["fields"]["countries"] == ["France", "Germany"]


def test_artifact_list_with_name_filter(patch_client):
    """Test --name filter on list."""
    result = runner.invoke(app, ["govern", "artifact", "list", "--name", "Test"])
    assert result.exit_code == 0
    assert "ar.5" in result.output


def test_artifact_list_all_pages(patch_client):
    """Test --all fetches multiple pages."""
    result = runner.invoke(app, ["govern", "artifact", "list", "--all", "-o", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1  # Only 1 hit before empty page stops iteration


def test_artifact_list_warns_on_truncation(patch_client):
    """Without --all, fetching exactly page_size hits + a non-empty peek
    triggers a 'Showing N (more available)' warning footer."""
    from unittest.mock import MagicMock

    gov = patch_client.get_govern_client()

    # Build a full page of hits at page_size=2.
    def _hit(art_id):
        h = MagicMock()
        h.get_raw.return_value = {
            "artifact": {
                "id": art_id,
                "name": f"Artifact {art_id}",
                "blueprintVersionId": {"blueprintId": "bp.t"},
                "status": {"archived": False},
            },
        }
        return h

    full_page = MagicMock()
    full_page.get_response_hits.return_value = [_hit("ar.1"), _hit("ar.2")]
    peek_with_more = MagicMock()
    peek_with_more.get_response_hits.return_value = [_hit("ar.3")]

    req = MagicMock()
    req.fetch_next_batch.side_effect = [full_page, peek_with_more]
    gov.new_artifact_search_request.return_value = req

    result = runner.invoke(app, ["govern", "artifact", "list", "--page-size", "2"])
    assert result.exit_code == 0, result.output
    assert "Showing 2 (more available)" in result.output
    assert "--all" in result.output


def test_artifact_list_no_warning_when_results_fit(patch_client):
    """Below page-size cap → no truncation warning."""
    result = runner.invoke(app, ["govern", "artifact", "list"])
    assert result.exit_code == 0
    assert "more available" not in result.output


def test_artifact_list_no_warning_in_json_mode(patch_client):
    """JSON output is consumed by jq pipelines — never inject warnings."""
    from unittest.mock import MagicMock

    gov = patch_client.get_govern_client()

    def _hit(art_id):
        h = MagicMock()
        h.get_raw.return_value = {
            "artifact": {
                "id": art_id,
                "name": "X",
                "blueprintVersionId": {},
                "status": {"archived": False},
            },
        }
        return h

    full_page = MagicMock()
    full_page.get_response_hits.return_value = [_hit("ar.1")]
    peek_with_more = MagicMock()
    peek_with_more.get_response_hits.return_value = [_hit("ar.2")]
    req = MagicMock()
    req.fetch_next_batch.side_effect = [full_page, peek_with_more]
    gov.new_artifact_search_request.return_value = req

    result = runner.invoke(
        app,
        [
            "govern",
            "artifact",
            "list",
            "--page-size",
            "1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    # JSON consumers must not see warning text mixed into the array.
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert "more available" not in result.output


# ---------------------------------------------------------------------------
# REFERENCE field pre-validation — catch `-f owner=admin` before the server does
# ---------------------------------------------------------------------------


def test_artifact_create_rejects_non_artifact_id_reference(patch_client):
    """`-f business_initiative=oops` should be rejected with a prescriptive error."""
    result = runner.invoke(
        app,
        [
            "govern",
            "artifact",
            "create",
            "-b",
            "bp.system.govern_project",
            "-n",
            "My Project",
            "-f",
            "business_initiative=oops",
        ],
    )
    assert result.exit_code != 0
    out = result.output + (result.stderr or "")
    assert "REFERENCE field 'business_initiative'" in out
    assert "artifact ID" in out
    assert "bp.system.business_initiative" in out
    assert "artifact list --blueprint bp.system.business_initiative" in out
    # Should NOT have called create_artifact — validation blocks pre-POST
    gov = patch_client.get_govern_client()
    gov.create_artifact.assert_not_called()


def test_artifact_create_accepts_valid_artifact_id_reference(patch_client):
    """`-f business_initiative=ar.10` should pass through without error."""
    result = runner.invoke(
        app,
        [
            "govern",
            "artifact",
            "create",
            "-b",
            "bp.system.govern_project",
            "-n",
            "My Project",
            "-f",
            "business_initiative=ar.10",
        ],
    )
    assert result.exit_code == 0, result.output
    gov = patch_client.get_govern_client()
    call_args = gov.create_artifact.call_args[0][0]
    assert call_args["fields"]["business_initiative"] == "ar.10"


def test_artifact_create_rejects_non_artifact_id_in_reference_list(patch_client):
    """Lists of REFERENCE values must all be artifact IDs."""
    # The fixture's govern_models is COMPUTE, so use business_initiative which is STORE.
    # A list-of-string that contains a non-ar.N value should be caught.
    result = runner.invoke(
        app,
        [
            "govern",
            "artifact",
            "create",
            "-b",
            "bp.system.govern_project",
            "-n",
            "My Project",
            "-f",
            'business_initiative=["ar.10","not_an_id"]',
        ],
    )
    assert result.exit_code != 0
    out = result.output + (result.stderr or "")
    assert "REFERENCE field 'business_initiative'" in out


def test_artifact_create_skips_validation_when_schema_fetch_fails(patch_client):
    """If we can't fetch the field definitions, fall back to server-side validation."""
    # Make get_definition raise so _get_version_field_defs returns {}
    gov = patch_client.get_govern_client()
    gov.get_blueprint.return_value.get_version.return_value.get_definition.side_effect = RuntimeError(
        "schema fetch broken"
    )
    result = runner.invoke(
        app,
        [
            "govern",
            "artifact",
            "create",
            "-b",
            "bp.system.govern_project",
            "-n",
            "My Project",
            "-f",
            "business_initiative=oops",
        ],
    )
    # Should reach the server (not blocked locally)
    # In the mock, create_artifact is still called and succeeds
    assert gov.create_artifact.called or result.exit_code == 0


def test_artifact_create_definition_json_validates_references(patch_client):
    """Raw --definition JSON path also validates REFERENCE fields."""
    payload = {
        "blueprintVersionId": {
            "blueprintId": "bp.system.govern_project",
            "versionId": "bv.system.default",
        },
        "name": "Test",
        "fields": {"business_initiative": "not_an_artifact_id"},
    }
    result = runner.invoke(
        app,
        [
            "govern",
            "artifact",
            "create",
            "--definition",
            json.dumps(payload),
        ],
    )
    assert result.exit_code != 0
    out = result.output + (result.stderr or "")
    assert "REFERENCE field 'business_initiative'" in out


def test_artifact_set_field_rejects_non_artifact_id_reference(patch_client):
    """set-field on a REFERENCE field must also validate artifact-ID shape."""
    result = runner.invoke(
        app,
        [
            "govern",
            "artifact",
            "set-field",
            "ar.5",
            "business_initiative",
            "admin",
        ],
    )
    assert result.exit_code != 0
    out = result.output + (result.stderr or "")
    assert "REFERENCE field 'business_initiative'" in out
    # Should NOT have saved
    gov = patch_client.get_govern_client()
    defn = gov.get_artifact.return_value.get_definition.return_value
    # save may have been called by earlier tests; check it wasn't called AFTER reset
    # by verifying our bad value didn't land
    assert (
        "business_initiative" not in defn.definition.get("fields", {})
        or defn.definition["fields"].get("business_initiative") != "admin"
    )


def test_artifact_set_field_accepts_valid_reference(patch_client):
    """set-field with a valid ar.N REFERENCE passes."""
    result = runner.invoke(
        app,
        [
            "govern",
            "artifact",
            "set-field",
            "ar.5",
            "business_initiative",
            "ar.42",
        ],
    )
    assert result.exit_code == 0, result.output
    gov = patch_client.get_govern_client()
    defn = gov.get_artifact.return_value.get_definition.return_value
    assert defn.definition["fields"]["business_initiative"] == "ar.42"
