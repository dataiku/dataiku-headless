"""Tests for semantic-model commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helper: simulate name-based resolution (ID fails, name lookup succeeds)
# ---------------------------------------------------------------------------


def _setup_name_resolution(patch_client):
    """Configure mocks so get_semantic_model raises for non-ID args, enabling name fallback."""
    proj = patch_client.get_project("PROJ1")
    sm_mock = proj.get_semantic_model.return_value  # the default mock

    def _get_sm(ref):
        if ref == "sm1":
            return sm_mock
        bad = MagicMock()
        bad._get_definition.side_effect = Exception("Object not found: sm_ref")
        return bad

    proj.get_semantic_model.side_effect = _get_sm
    return proj, sm_mock


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list(patch_client):
    result = runner.invoke(app, ["semantic-model", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "sm1" in result.output


def test_list_json(patch_client):
    result = runner.invoke(
        app, ["semantic-model", "list", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "sm1"
    assert parsed[0]["name"] == "My Semantic Model"


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


def test_create(patch_client):
    result = runner.invoke(
        app,
        ["semantic-model", "create", "My Semantic Model", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").create_semantic_model.assert_called_once_with(
        "My Semantic Model"
    )


def test_create_if_not_exists_when_exists(patch_client):
    """--if-not-exists silently skips when SM already exists."""
    proj = patch_client.get_project("PROJ1")
    proj.create_semantic_model.side_effect = Exception("Semantic model already exists")
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "create",
            "My Semantic Model",
            "--if-not-exists",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "already exists" in result.output.lower()


def test_create_if_not_exists_when_new(patch_client):
    """--if-not-exists creates normally when SM doesn't exist."""
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "create",
            "My Semantic Model",
            "--if-not-exists",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").create_semantic_model.assert_called_once()


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


def test_get(patch_client):
    result = runner.invoke(app, ["semantic-model", "get", "sm1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "sm1" in result.output


def test_get_json(patch_client):
    result = runner.invoke(
        app, ["semantic-model", "get", "sm1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "sm1"
    assert parsed["activeVersionId"] == "v1"


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete(patch_client):
    result = runner.invoke(
        app, ["semantic-model", "delete", "sm1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_semantic_model(
        "sm1"
    ).delete.assert_called_once()


# ---------------------------------------------------------------------------
# versions
# ---------------------------------------------------------------------------


def test_versions(patch_client):
    result = runner.invoke(
        app, ["semantic-model", "versions", "sm1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "v1" in result.output
    assert "True" in result.output  # active marker


def test_versions_json(patch_client):
    result = runner.invoke(
        app,
        ["semantic-model", "versions", "sm1", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "v1"
    assert parsed[0]["active"] == "True"


# ---------------------------------------------------------------------------
# get-version
# ---------------------------------------------------------------------------


def test_get_version(patch_client):
    result = runner.invoke(
        app, ["semantic-model", "get-version", "sm1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "v1" in result.output


def test_get_version_json(patch_client):
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "get-version",
            "sm1",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "v1"
    assert "entities" in parsed


def test_get_version_explicit(patch_client):
    """Passing --version explicitly uses that version."""
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "get-version",
            "sm1",
            "--version",
            "v1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_semantic_model(
        "sm1"
    ).get_version.assert_called_with("v1")


def test_get_version_uninitialized_existing_version(patch_client):
    """A listed version with missing settings gets a prescriptive error."""
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    sm.get_version.return_value.get_settings.side_effect = Exception(
        "NotFoundException: Version v2 not found"
    )
    sm.list_versions_ids.return_value = ["v1", "v2"]

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "get-version",
            "sm1",
            "--version",
            "v2",
            "--project",
            "PROJ1",
        ],
    )

    assert result.exit_code == 3
    assert "exists but has no settings yet" in result.output
    sm.list_versions_ids.assert_called_once()


# ---------------------------------------------------------------------------
# create-version
# ---------------------------------------------------------------------------


def test_create_version(patch_client):
    result = runner.invoke(
        app,
        ["semantic-model", "create-version", "sm1", "v2", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    sm.new_version.assert_called_once_with("v2", duplicate_of=None)
    sm.new_version.return_value.save.assert_called_once()


def test_create_version_duplicate(patch_client):
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "create-version",
            "sm1",
            "v2",
            "--duplicate-of",
            "v1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    sm.new_version.assert_called_once_with("v2", duplicate_of="v1")
    sm.new_version.return_value.save.assert_called_once()


# ---------------------------------------------------------------------------
# set-version
# ---------------------------------------------------------------------------


def test_set_version(patch_client):
    """set-version merges JSON into version settings and saves."""
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "set-version",
            "sm1",
            "--definition",
            '{"description": "Updated"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    version = sm.get_version("v1")
    settings = version.get_settings()
    raw = settings.get_raw()
    assert raw["description"] == "Updated"
    settings.save.assert_called_once()


# ---------------------------------------------------------------------------
# set-active-version
# ---------------------------------------------------------------------------


def test_set_active_version(patch_client):
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "set-active-version",
            "sm1",
            "v1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_semantic_model(
        "sm1"
    ).set_active_version_id.assert_called_once_with("v1")


# ---------------------------------------------------------------------------
# distinct-values
# ---------------------------------------------------------------------------


def test_distinct_values(patch_client):
    result = runner.invoke(
        app,
        ["semantic-model", "distinct-values", "sm1", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "entity1" in result.output


def test_distinct_values_json(patch_client):
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "distinct-values",
            "sm1",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "entity1" in parsed


def test_distinct_values_attribute(patch_client):
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "distinct-values",
            "sm1",
            "--entity",
            "entity1",
            "--attribute",
            "attr1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    sm.get_version("v1").get_basic_distinct_values_for_attribute.assert_called_with(
        "entity1", "attr1", max_values=1000
    )


def test_distinct_values_entity_without_attribute(patch_client):
    """Passing --entity without --attribute gives an error."""
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "distinct-values",
            "sm1",
            "--entity",
            "entity1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "--entity" in result.output or "--attribute" in result.output


# ---------------------------------------------------------------------------
# update-index
# ---------------------------------------------------------------------------


def test_update_index(patch_client):
    result = runner.invoke(
        app,
        ["semantic-model", "update-index", "sm1", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    sm.get_version("v1").start_update_distinct_values.assert_called_once()


def test_update_index_wait(patch_client):
    result = runner.invoke(
        app,
        ["semantic-model", "update-index", "sm1", "--wait", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    future = sm.get_version("v1").start_update_distinct_values()
    future.wait_for_result.assert_called()


# ---------------------------------------------------------------------------
# Name-to-ID resolution tests
# ---------------------------------------------------------------------------


def test_get_by_name(patch_client):
    """Passing a name instead of ID should resolve via list_semantic_models."""
    proj, sm_mock = _setup_name_resolution(patch_client)
    result = runner.invoke(
        app,
        ["semantic-model", "get", "My Semantic Model", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    proj.list_semantic_models.assert_called_once()


def test_delete_by_name(patch_client):
    """Delete command resolves by name."""
    proj, sm_mock = _setup_name_resolution(patch_client)
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "delete",
            "My Semantic Model",
            "--project",
            "PROJ1",
            "--yes",
        ],
    )
    assert result.exit_code == 0
    sm_mock.delete.assert_called_once()


def test_not_found(patch_client):
    """Unknown name/ID gives prescriptive error listing available SMs."""
    proj, _ = _setup_name_resolution(patch_client)
    result = runner.invoke(
        app,
        ["semantic-model", "get", "nonexistent", "--project", "PROJ1"],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
    assert "sm1" in result.output  # should list available SMs


# ---------------------------------------------------------------------------
# Splice-level commands: add-entity, remove-entity,
# add-relationship, remove-relationship,
# add-glossary-term, remove-glossary-term,
# list-entities, list-relationships, list-glossary
# ---------------------------------------------------------------------------


def _configure_dataset_schema(patch_client, columns):
    """Set the mock dataset's schema to the provided columns list."""
    ds_mock = patch_client.get_project("PROJ1").get_dataset.return_value
    ds_mock.get_definition.return_value = {"schema": {"columns": columns}}
    return ds_mock


def test_add_entity_from_dataset(patch_client):
    """add-entity pulls schema columns and splices a new entity."""
    _configure_dataset_schema(
        patch_client,
        [
            {"name": "CustomerID", "type": "string", "description": "PK"},
            {"name": "Name", "type": "string"},
            {"name": "Age", "type": "bigint"},
        ],
    )
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-entity",
            "sm1",
            "--from-dataset",
            "Customers",
            "--name",
            "customer",
            "--pk",
            "CustomerID",
            "--index-values",
            "Name",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    assert len(raw["entities"]) == 1
    entity = raw["entities"][0]
    assert entity["name"] == "customer"
    assert entity["datasetRef"] == "PROJ1.Customers"
    assert entity["primaryKey"]["attributes"] == ["CustomerID"]
    assert len(entity["attributes"]) == 3
    by_name = {a["name"]: a for a in entity["attributes"]}
    assert by_name["Name"]["indexDistinctValues"] is True
    assert by_name["Name"]["resolveInUserRequests"] is True
    assert by_name["Age"]["indexDistinctValues"] is False


def test_add_entity_requires_from_dataset(patch_client):
    """Omitting --from-dataset is an error with prescriptive message."""
    result = runner.invoke(
        app,
        ["semantic-model", "add-entity", "sm1", "--name", "x", "--project", "PROJ1"],
    )
    assert result.exit_code != 0
    assert "from-dataset" in result.output


def test_add_entity_duplicate_errors(patch_client):
    """Adding an entity with an existing name errors."""
    _configure_dataset_schema(patch_client, [{"name": "id", "type": "string"}])
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["entities"] = [{"name": "customer"}]

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-entity",
            "sm1",
            "--from-dataset",
            "Customers",
            "--name",
            "customer",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "already exists" in result.output.lower()


def test_add_entity_if_not_exists(patch_client):
    """--if-not-exists silently skips on duplicate."""
    _configure_dataset_schema(patch_client, [{"name": "id", "type": "string"}])
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["entities"] = [{"name": "customer"}]

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-entity",
            "sm1",
            "--from-dataset",
            "Customers",
            "--name",
            "customer",
            "--if-not-exists",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "skipping" in result.output.lower()


def test_remove_entity(patch_client):
    """remove-entity splices the entity and cleans up referring relationships."""
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["entities"] = [{"name": "a"}, {"name": "b"}]
    raw["relationships"] = [
        {"firstEntity": "a", "secondEntity": "b", "pseudoSQLExpression": "x"},
        {"firstEntity": "c", "secondEntity": "d", "pseudoSQLExpression": "y"},
    ]

    result = runner.invoke(
        app,
        ["semantic-model", "remove-entity", "sm1", "a", "--project", "PROJ1"],
    )
    assert result.exit_code == 0, result.output
    assert len(raw["entities"]) == 1
    assert raw["entities"][0]["name"] == "b"
    assert len(raw["relationships"]) == 1  # a<->b was removed


def test_remove_entity_not_found(patch_client):
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    sm.get_version("v1").get_settings().get_raw()["entities"] = []

    result = runner.invoke(
        app,
        ["semantic-model", "remove-entity", "sm1", "ghost", "--project", "PROJ1"],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_add_relationship_on_column(patch_client):
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["entities"] = [{"name": "a"}, {"name": "b"}]
    raw["relationships"] = []

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-relationship",
            "sm1",
            "--from",
            "a",
            "--to",
            "b",
            "--on",
            "CustomerID",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert raw["relationships"] == [
        {
            "firstEntity": "a",
            "secondEntity": "b",
            "pseudoSQLExpression": "left.CustomerID = right.CustomerID",
        }
    ]


def test_add_relationship_composite_on(patch_client):
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["entities"] = [{"name": "a"}, {"name": "b"}]
    raw["relationships"] = []

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-relationship",
            "sm1",
            "--from",
            "a",
            "--to",
            "b",
            "--on",
            "ACCOUNT_SK,MONTH",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    expr = raw["relationships"][0]["pseudoSQLExpression"]
    assert "left.ACCOUNT_SK = right.ACCOUNT_SK" in expr
    assert " AND " in expr
    assert "left.MONTH = right.MONTH" in expr


def test_add_relationship_expression(patch_client):
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["entities"] = [{"name": "a"}, {"name": "b"}]
    raw["relationships"] = []

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-relationship",
            "sm1",
            "--from",
            "a",
            "--to",
            "b",
            "--expression",
            "LOWER(left.email) = LOWER(right.email)",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert (
        raw["relationships"][0]["pseudoSQLExpression"]
        == "LOWER(left.email) = LOWER(right.email)"
    )


def test_add_relationship_mutually_exclusive_on_expression(patch_client):
    """Passing both --on and --expression errors."""
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-relationship",
            "sm1",
            "--from",
            "a",
            "--to",
            "b",
            "--on",
            "X",
            "--expression",
            "left.X = right.X",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "--on" in result.output or "--expression" in result.output


def test_add_relationship_missing_entity(patch_client):
    """Relationship referencing an entity not in the version errors."""
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["entities"] = [{"name": "a"}]

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-relationship",
            "sm1",
            "--from",
            "a",
            "--to",
            "ghost",
            "--on",
            "x",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_add_relationship_duplicate(patch_client):
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["entities"] = [{"name": "a"}, {"name": "b"}]
    raw["relationships"] = [
        {"firstEntity": "a", "secondEntity": "b", "pseudoSQLExpression": "x"}
    ]

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-relationship",
            "sm1",
            "--from",
            "a",
            "--to",
            "b",
            "--on",
            "y",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "already exists" in result.output.lower()


def test_remove_relationship_either_direction(patch_client):
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["relationships"] = [
        {"firstEntity": "a", "secondEntity": "b", "pseudoSQLExpression": "x"},
        {"firstEntity": "c", "secondEntity": "d", "pseudoSQLExpression": "y"},
    ]

    # Remove specifying reversed order — should still match
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "remove-relationship",
            "sm1",
            "--from",
            "b",
            "--to",
            "a",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(raw["relationships"]) == 1
    assert raw["relationships"][0]["firstEntity"] == "c"


def test_remove_relationship_not_found(patch_client):
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    sm.get_version("v1").get_settings().get_raw()["relationships"] = []

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "remove-relationship",
            "sm1",
            "--from",
            "x",
            "--to",
            "y",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


def test_add_glossary_term(patch_client):
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["glossaryTerms"] = []

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-glossary-term",
            "sm1",
            "--term",
            "ARR",
            "--description",
            "Annual Recurring Revenue",
            "--synonyms",
            "annual recurring revenue,subscription revenue",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(raw["glossaryTerms"]) == 1
    t = raw["glossaryTerms"][0]
    assert t["term"] == "ARR"
    assert t["description"] == "Annual Recurring Revenue"
    assert t["source"] == "MANUAL"
    assert t["userModified"] is True
    assert t["synonyms"] == ["annual recurring revenue", "subscription revenue"]
    assert t["id"]  # UUID set


def test_add_glossary_term_duplicate(patch_client):
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["glossaryTerms"] = [{"term": "ARR", "description": "existing"}]

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-glossary-term",
            "sm1",
            "--term",
            "ARR",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


def test_remove_glossary_term(patch_client):
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["glossaryTerms"] = [
        {"term": "ARR", "description": ""},
        {"term": "CX", "description": ""},
    ]

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "remove-glossary-term",
            "sm1",
            "--term",
            "ARR",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert [t["term"] for t in raw["glossaryTerms"]] == ["CX"]


def test_list_entities(patch_client):
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["entities"] = [
        {
            "name": "customer",
            "datasetRef": "PROJ1.Customers",
            "primaryKey": {"attributes": ["CustomerID"]},
            "attributes": [{"name": "a"}, {"name": "b"}],
        }
    ]

    result = runner.invoke(
        app,
        ["semantic-model", "list-entities", "sm1", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["name"] == "customer"
    assert parsed[0]["dataset"] == "PROJ1.Customers"
    assert parsed[0]["attributes"] == "2"
    assert parsed[0]["primary_key"] == "CustomerID"


def test_list_relationships(patch_client):
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["relationships"] = [
        {
            "firstEntity": "a",
            "secondEntity": "b",
            "pseudoSQLExpression": "left.x = right.x",
        }
    ]

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "list-relationships",
            "sm1",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["first_entity"] == "a"
    assert parsed[0]["second_entity"] == "b"
    assert parsed[0]["expression"] == "left.x = right.x"


def test_list_glossary(patch_client):
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["glossaryTerms"] = [
        {
            "term": "ARR",
            "description": "Annual Recurring Revenue",
            "synonyms": ["annual recurring revenue"],
        }
    ]

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "list-glossary",
            "sm1",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["term"] == "ARR"
    assert parsed[0]["description"] == "Annual Recurring Revenue"
    assert "annual recurring revenue" in parsed[0]["synonyms"]


# ---------------------------------------------------------------------------
# Metric / filter / manual-values / golden-query verbs
# ---------------------------------------------------------------------------


def _seed_entity(
    patch_client, name="customer", attributes=None, metrics=None, filters=None
):
    """Seed a single entity on the mock version for entity-scoped tests."""
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["entities"] = [
        {
            "name": name,
            "attributes": attributes or [],
            "metrics": metrics or [],
            "filters": filters or [],
        }
    ]
    return raw


def test_add_metric(patch_client):
    raw = _seed_entity(patch_client)
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-metric",
            "sm1",
            "--entity",
            "customer",
            "--name",
            "Total",
            "--expression",
            "COUNT(CustomerID)",
            "--description",
            "Total customers",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    metrics = raw["entities"][0]["metrics"]
    assert len(metrics) == 1
    assert metrics[0]["name"] == "Total"
    assert metrics[0]["pseudoSQLExpression"] == "COUNT(CustomerID)"
    assert metrics[0]["description"] == "Total customers"
    assert metrics[0]["created"] == {}


def test_add_metric_duplicate(patch_client):
    _seed_entity(patch_client, metrics=[{"name": "Total"}])
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-metric",
            "sm1",
            "--entity",
            "customer",
            "--name",
            "Total",
            "--expression",
            "COUNT(*)",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "already exists" in result.output.lower()


def test_add_metric_missing_entity(patch_client):
    _seed_entity(patch_client)
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-metric",
            "sm1",
            "--entity",
            "ghost",
            "--name",
            "x",
            "--expression",
            "COUNT(*)",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_remove_metric(patch_client):
    raw = _seed_entity(
        patch_client,
        metrics=[{"name": "A", "pseudoSQLExpression": "COUNT(*)"}, {"name": "B"}],
    )
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "remove-metric",
            "sm1",
            "--entity",
            "customer",
            "--name",
            "A",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert [m["name"] for m in raw["entities"][0]["metrics"]] == ["B"]


def test_list_metrics(patch_client):
    _seed_entity(
        patch_client,
        metrics=[
            {
                "name": "Total",
                "pseudoSQLExpression": "COUNT(*)",
                "description": "count",
            }
        ],
    )
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "list-metrics",
            "sm1",
            "--entity",
            "customer",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["name"] == "Total"
    assert parsed[0]["expression"] == "COUNT(*)"


def test_add_filter(patch_client):
    raw = _seed_entity(patch_client)
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-filter",
            "sm1",
            "--entity",
            "customer",
            "--name",
            "Subscribed",
            "--expression",
            "Subscribed = 'true'",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    f = raw["entities"][0]["filters"][0]
    assert f["name"] == "Subscribed"
    assert f["pseudoSQLExpression"] == "Subscribed = 'true'"


def test_remove_filter(patch_client):
    raw = _seed_entity(patch_client, filters=[{"name": "A"}, {"name": "B"}])
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "remove-filter",
            "sm1",
            "--entity",
            "customer",
            "--name",
            "A",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert [f["name"] for f in raw["entities"][0]["filters"]] == ["B"]


def test_remove_filter_not_found(patch_client):
    _seed_entity(patch_client)
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "remove-filter",
            "sm1",
            "--entity",
            "customer",
            "--name",
            "ghost",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_list_filters(patch_client):
    _seed_entity(
        patch_client,
        filters=[{"name": "A", "pseudoSQLExpression": "x=1", "description": ""}],
    )
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "list-filters",
            "sm1",
            "--entity",
            "customer",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["name"] == "A"
    assert parsed[0]["expression"] == "x=1"


def test_set_manual_values(patch_client):
    raw = _seed_entity(
        patch_client,
        attributes=[
            {
                "name": "RiskTolerance",
                "dssType": "string",
                "distinctValuesHandlingMode": "NONE",
                "manualValues": [],
                "indexDistinctValues": False,
                "resolveInUserRequests": False,
            }
        ],
    )
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "set-manual-values",
            "sm1",
            "--entity",
            "customer",
            "--attribute",
            "RiskTolerance",
            "--values",
            "Low,Medium,High",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    attr = raw["entities"][0]["attributes"][0]
    assert attr["distinctValuesHandlingMode"] == "MANUAL"
    assert attr["manualValues"] == ["Low", "Medium", "High"]
    assert attr["indexDistinctValues"] is True
    assert attr["resolveInUserRequests"] is True


def test_set_manual_values_clear(patch_client):
    raw = _seed_entity(
        patch_client,
        attributes=[
            {
                "name": "RiskTolerance",
                "dssType": "string",
                "distinctValuesHandlingMode": "MANUAL",
                "manualValues": ["Low", "High"],
                "indexDistinctValues": True,
                "resolveInUserRequests": True,
            }
        ],
    )
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "set-manual-values",
            "sm1",
            "--entity",
            "customer",
            "--attribute",
            "RiskTolerance",
            "--clear",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    attr = raw["entities"][0]["attributes"][0]
    assert attr["distinctValuesHandlingMode"] == "NONE"
    assert attr["manualValues"] == []


def test_set_manual_values_both_flags_error(patch_client):
    _seed_entity(patch_client)
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "set-manual-values",
            "sm1",
            "--entity",
            "customer",
            "--attribute",
            "x",
            "--values",
            "a,b",
            "--clear",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "--values" in result.output or "--clear" in result.output


def test_set_manual_values_missing_attribute(patch_client):
    _seed_entity(patch_client, attributes=[{"name": "other"}])
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "set-manual-values",
            "sm1",
            "--entity",
            "customer",
            "--attribute",
            "ghost",
            "--values",
            "a",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_add_golden_query(patch_client):
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["goldenQueries"] = []

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-golden-query",
            "sm1",
            "--name",
            "monthly",
            "--question",
            "What was revenue last month?",
            "--sql",
            "SELECT SUM(amount) FROM orders",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    q = raw["goldenQueries"][0]
    assert q["name"] == "monthly"
    assert q["question"] == "What was revenue last month?"
    assert q["generatedSql"] == "SELECT SUM(amount) FROM orders"
    assert q["created"] == {}


def test_remove_golden_query(patch_client):
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["goldenQueries"] = [{"name": "A"}, {"name": "B"}]

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "remove-golden-query",
            "sm1",
            "--name",
            "A",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert [q["name"] for q in raw["goldenQueries"]] == ["B"]


def test_list_golden_queries(patch_client):
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["goldenQueries"] = [
        {
            "name": "monthly",
            "question": "What was revenue?",
            "generatedSql": "SELECT SUM(x) FROM y",
        }
    ]

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "list-golden-queries",
            "sm1",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["name"] == "monthly"
    assert parsed[0]["question"] == "What was revenue?"
    assert parsed[0]["sql"] == "SELECT SUM(x) FROM y"


# ---------------------------------------------------------------------------
# Edge-case bug regression tests
# ---------------------------------------------------------------------------


def test_add_entity_pk_column_must_exist(patch_client):
    """--pk referencing a column not in the dataset schema is rejected."""
    _configure_dataset_schema(patch_client, [{"name": "CustomerID", "type": "string"}])
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-entity",
            "sm1",
            "--from-dataset",
            "Customers",
            "--pk",
            "FakeColumn",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "--pk" in result.output
    assert "FakeColumn" in result.output


def test_add_entity_pk_case_sensitive(patch_client):
    """--pk case-mismatch with schema column is rejected."""
    _configure_dataset_schema(patch_client, [{"name": "CustomerID", "type": "string"}])
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-entity",
            "sm1",
            "--from-dataset",
            "Customers",
            "--pk",
            "customerid",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "customerid" in result.output


def test_add_entity_multicol_pk_one_missing(patch_client):
    _configure_dataset_schema(patch_client, [{"name": "CustomerID", "type": "string"}])
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-entity",
            "sm1",
            "--from-dataset",
            "Customers",
            "--pk",
            "CustomerID,Ghost",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Ghost" in result.output


def test_add_entity_index_values_column_must_exist(patch_client):
    """--index-values referencing a fake column is rejected (no silent no-op)."""
    _configure_dataset_schema(patch_client, [{"name": "id", "type": "string"}])
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-entity",
            "sm1",
            "--from-dataset",
            "Customers",
            "--index-values",
            "Nope",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "--index-values" in result.output
    assert "Nope" in result.output


def test_add_entity_resolve_values_column_must_exist(patch_client):
    _configure_dataset_schema(patch_client, [{"name": "id", "type": "string"}])
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-entity",
            "sm1",
            "--from-dataset",
            "Customers",
            "--resolve-values",
            "Nope",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "--resolve-values" in result.output


def test_add_entity_whitespace_name_falls_back(patch_client):
    """Whitespace-only --name falls back to dataset-lowered, not saved as whitespace."""
    _configure_dataset_schema(patch_client, [{"name": "id", "type": "string"}])
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-entity",
            "sm1",
            "--from-dataset",
            "CustomersDS",
            "--name",
            "   ",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    # Must not be whitespace — falls back to lowered dataset name
    assert raw["entities"][0]["name"] == "customersds"


def test_add_metric_whitespace_name_rejected(patch_client):
    _seed_entity(patch_client)
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-metric",
            "sm1",
            "--entity",
            "customer",
            "--name",
            "   ",
            "--expression",
            "COUNT(*)",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "empty" in result.output.lower() or "whitespace" in result.output.lower()


def test_add_filter_whitespace_name_rejected(patch_client):
    _seed_entity(patch_client)
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-filter",
            "sm1",
            "--entity",
            "customer",
            "--name",
            "   ",
            "--expression",
            "x=1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


def test_add_glossary_term_empty_rejected(patch_client):
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-glossary-term",
            "sm1",
            "--term",
            "",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


def test_add_glossary_term_whitespace_rejected(patch_client):
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-glossary-term",
            "sm1",
            "--term",
            "   ",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


def test_add_golden_query_whitespace_name_rejected(patch_client):
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-golden-query",
            "sm1",
            "--name",
            "   ",
            "--question",
            "q",
            "--sql",
            "SELECT 1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


def test_add_relationship_duplicate_on_cols_deduped(patch_client):
    """--on 'X,X' dedupes to 'left.X = right.X' (not 'AND left.X = right.X')."""
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["entities"] = [{"name": "a"}, {"name": "b"}]
    raw["relationships"] = []

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-relationship",
            "sm1",
            "--from",
            "a",
            "--to",
            "b",
            "--on",
            "X,X,X",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert raw["relationships"][0]["pseudoSQLExpression"] == "left.X = right.X"


def test_add_relationship_expression_whitespace_rejected(patch_client):
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["entities"] = [{"name": "a"}, {"name": "b"}]

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-relationship",
            "sm1",
            "--from",
            "a",
            "--to",
            "b",
            "--expression",
            "   ",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


def test_add_entity_pk_duplicate_cols_deduped(patch_client):
    """--pk 'CustomerID,CustomerID' is deduped to a single-column PK."""
    _configure_dataset_schema(patch_client, [{"name": "CustomerID", "type": "string"}])
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-entity",
            "sm1",
            "--from-dataset",
            "Customers",
            "--pk",
            "CustomerID,CustomerID",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    assert raw["entities"][0]["primaryKey"]["attributes"] == ["CustomerID"]


def test_add_entity_unicode_everywhere(patch_client):
    """Unicode names / descriptions / dataset refs round-trip correctly."""
    _configure_dataset_schema(
        patch_client,
        [
            {"name": "id", "type": "string"},
            {"name": "Müller", "type": "string"},
        ],
    )
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-entity",
            "sm1",
            "--from-dataset",
            "Kunden",
            "--name",
            "kunden_🚀",
            "--description",
            "Deutsche Kunden",
            "--index-values",
            "Müller",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    ent = raw["entities"][0]
    assert ent["name"] == "kunden_🚀"
    assert ent["description"] == "Deutsche Kunden"
    muller = next(a for a in ent["attributes"] if a["name"] == "Müller")
    assert muller["indexDistinctValues"] is True


def test_add_filter_preserves_quotes_in_expression(patch_client):
    """Quotes in pseudoSQL round-trip exactly."""
    _seed_entity(patch_client)
    expr = "col = 'it\\'s fine' AND col2 = \"quoted\""
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-filter",
            "sm1",
            "--entity",
            "customer",
            "--name",
            "weird",
            "--expression",
            expr,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    assert raw["entities"][0]["filters"][0]["pseudoSQLExpression"] == expr


def test_remove_entity_cleans_multiple_relationships(patch_client):
    """Removing an entity referenced in N relationships removes all N."""
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["entities"] = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
    raw["relationships"] = [
        {"firstEntity": "a", "secondEntity": "b", "pseudoSQLExpression": "x"},
        {"firstEntity": "c", "secondEntity": "a", "pseudoSQLExpression": "y"},
        {"firstEntity": "b", "secondEntity": "c", "pseudoSQLExpression": "z"},
    ]
    result = runner.invoke(
        app,
        ["semantic-model", "remove-entity", "sm1", "a", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    # Only b<->c remains
    assert len(raw["relationships"]) == 1
    assert raw["relationships"][0]["firstEntity"] == "b"
    assert "2 relationship(s)" in result.output


def test_remove_relationship_removes_duplicates(patch_client):
    """If the same (A,B) relationship exists twice, remove-relationship removes both."""
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["relationships"] = [
        {"firstEntity": "a", "secondEntity": "b", "pseudoSQLExpression": "x"},
        {"firstEntity": "a", "secondEntity": "b", "pseudoSQLExpression": "y"},
    ]
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "remove-relationship",
            "sm1",
            "--from",
            "a",
            "--to",
            "b",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert raw["relationships"] == []
    assert "2 relationship" in result.output


def test_add_relationship_self_referential_allowed(patch_client):
    """Self-join (A → A) is a valid pattern for hierarchical data."""
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["entities"] = [{"name": "employee"}]
    raw["relationships"] = []

    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-relationship",
            "sm1",
            "--from",
            "employee",
            "--to",
            "employee",
            "--expression",
            "left.ID = right.ManagerID",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert len(raw["relationships"]) == 1


def test_add_golden_query_preserves_newlines(patch_client):
    raw = (
        patch_client.get_project("PROJ1")
        .get_semantic_model("sm1")
        .get_version("v1")
        .get_settings()
        .get_raw()
    )
    raw["goldenQueries"] = []
    sql = "SELECT *\nFROM t\nWHERE x = 1"
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "add-golden-query",
            "sm1",
            "--name",
            "multiline",
            "--question",
            "?",
            "--sql",
            sql,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert raw["goldenQueries"][0]["generatedSql"] == sql


def test_add_glossary_term_unique_uuids(patch_client):
    """Each add-glossary-term gets a distinct UUID (even for similar terms)."""
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    raw = sm.get_version("v1").get_settings().get_raw()
    raw["glossaryTerms"] = []

    for term in ["A", "B", "C"]:
        r = runner.invoke(
            app,
            [
                "semantic-model",
                "add-glossary-term",
                "sm1",
                "--term",
                term,
                "--project",
                "PROJ1",
            ],
        )
        assert r.exit_code == 0

    ids = [t["id"] for t in raw["glossaryTerms"]]
    assert len(ids) == 3
    assert len(set(ids)) == 3  # all unique


def test_set_manual_values_empty_values_rejected(patch_client):
    """--values with only whitespace/commas is rejected."""
    _seed_entity(
        patch_client,
        attributes=[
            {
                "name": "x",
                "distinctValuesHandlingMode": "NONE",
                "manualValues": [],
            }
        ],
    )
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "set-manual-values",
            "sm1",
            "--entity",
            "customer",
            "--attribute",
            "x",
            "--values",
            " , , ",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
