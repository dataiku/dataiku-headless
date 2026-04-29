"""Govern blueprint-designer mock builders for unit tests.

Extracted from `tests/conftest.py` so the Govern admin surface has a single
place where mocks live. The `mock_client` fixture calls `wire_designer_mocks`
to attach these to a govern_client mock — tests can then reach into the tree
via `patch_client.get_govern_client().get_blueprint_designer()...`.

Shape conventions match the real `dataikuapi` Govern admin API:
- `bp_designer.get_blueprint(id)` returns an `admin_bp_obj`
- `admin_bp_obj.get_version(vid)` returns an existing `bp_ver` mock
- `admin_bp_obj.create_version(id, name, origin_version_id)` returns a DRAFT
- `bp_ver.get_trace()` returns a trace mock with a `.status` property
- `bp_ver.list_signoff_configurations()` returns a list with one item
- `bp_ver.get_signoff_configuration(step)` returns a configurable mock

Tests that need different state can override individual return values on the
returned mock objects directly — the builders expose the mocks by reference.
"""

from __future__ import annotations

from unittest.mock import MagicMock


def build_admin_blueprint(
    blueprint_id: str = "bp.custom.my_bp",
    name: str = "My Blueprint",
) -> MagicMock:
    """Build an admin blueprint mock with a canonical empty definition."""
    admin_bp_obj = MagicMock()
    admin_bp_obj.blueprint_id = blueprint_id
    admin_bp_def = MagicMock()
    admin_bp_def.get_raw.return_value = {"id": blueprint_id, "name": name}
    admin_bp_obj.get_definition.return_value = admin_bp_def
    return admin_bp_obj


def build_draft_version(
    blueprint_id: str = "bp.custom.my_bp",
    version_id: str = "bv.v1",
    name: str = "Version 1",
) -> MagicMock:
    """Build a DRAFT blueprint version mock with an empty definition."""
    draft_ver = MagicMock()
    draft_ver.blueprint_id = blueprint_id
    draft_ver.version_id = version_id
    draft_ver_def = MagicMock()
    draft_ver_def.get_raw.return_value = {
        "id": {"blueprintId": blueprint_id, "versionId": version_id},
        "name": name,
        "fieldDefinitions": {},
        "workflowDefinition": {"stepDefinitions": []},
        "logicalHookList": [],
        "actions": {},
        "uiDefinition": {"views": {}, "uiStepDefinitions": {}},
        "iconMode": "INHERIT",
    }
    draft_ver.get_definition.return_value = draft_ver_def
    return draft_ver


def build_version_trace(
    blueprint_id: str = "bp.system.govern_project",
    version_id: str = "bv.system.default",
    status: str = "ACTIVE",
) -> MagicMock:
    """Build a version trace mock (get_trace() target). `.status` is a plain attr."""
    trace = MagicMock()
    trace.status = status
    trace.get_raw.return_value = {
        "blueprintVersionId": {
            "blueprintId": blueprint_id,
            "versionId": version_id,
        },
        "status": status,
    }
    return trace


def build_signoff_config(
    blueprint_id: str = "bp.system.govern_project",
    version_id: str = "bv.system.default",
    step_id: str = "review",
    title: str = "Review gate",
) -> tuple[MagicMock, MagicMock]:
    """Build paired (signoff_list_item, signoff_config_handle) mocks."""
    raw = {
        "id": {
            "blueprintVersionId": {
                "blueprintId": blueprint_id,
                "versionId": version_id,
            },
            "stepId": step_id,
        },
        "title": title,
        "mandatory": True,
        "feedbackUsersGroups": [{"id": "reviewers", "title": "Reviewers", "users": []}],
        "approvers": [],
        "recurrenceConfiguration": {
            "activated": False,
            "days": 0,
            "weeks": 0,
            "months": 0,
            "years": 0,
            "reloadConf": False,
        },
    }

    signoff_list_item = MagicMock()
    signoff_list_item.get_raw.return_value = raw

    signoff_cfg = MagicMock()
    signoff_cfg_def = MagicMock()
    signoff_cfg_def.get_raw.return_value = raw
    signoff_cfg.get_definition.return_value = signoff_cfg_def

    return signoff_list_item, signoff_cfg


def wire_designer_mocks(
    govern_client: MagicMock,
    bp_ver_item: MagicMock,
    bp_ver: MagicMock,
) -> MagicMock:
    """Attach the full blueprint-designer mock tree to a govern_client mock.

    Returns the bp_designer mock so individual tests can override any node.

    `bp_ver_item` and `bp_ver` are the non-admin version mocks already wired
    by the main conftest fixture — we reuse them here so admin tests that
    exercise `list-versions` / `get-version` / `fields` via the designer path
    see the same shape as the non-admin path.
    """
    bp_designer = MagicMock()
    admin_bp_obj = build_admin_blueprint()
    bp_designer.create_blueprint.return_value = admin_bp_obj
    bp_designer.get_blueprint.return_value = admin_bp_obj

    # list_versions / get_version go through the shared non-admin mocks so
    # DRAFT authoring tests see the same `bp_ver` the original fixture set up.
    admin_bp_obj.list_versions.return_value = [bp_ver_item]
    admin_bp_obj.get_version.return_value = bp_ver

    # Version authoring — create_version returns a fresh DRAFT handle.
    admin_bp_obj.create_version.return_value = build_draft_version()

    # Trace hanging off the existing bp_ver
    bp_ver.get_trace.return_value = build_version_trace()

    # Signoff configs on bp_ver
    signoff_item, signoff_cfg = build_signoff_config()
    bp_ver.list_signoff_configurations.return_value = [signoff_item]
    bp_ver.get_signoff_configuration.return_value = signoff_cfg
    bp_ver.create_signoff_configuration.return_value = signoff_cfg

    govern_client.get_blueprint_designer.return_value = bp_designer
    return bp_designer
