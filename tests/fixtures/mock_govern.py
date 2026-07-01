"""Govern mock setup for the shared CLI DSS client fixture."""

from __future__ import annotations

from unittest.mock import MagicMock


def configure_govern_client(client):
    """Attach Govern client mocks to the shared DSS client fixture."""
    # ── Govern client mock ──────────────────────────────────────────────
    govern_client = MagicMock()
    govern_client.get_auth_info.return_value = {
        "authSource": "CONFIGURABLE_API_KEY_GLOBAL",
        "authIdentifier": "api:govern_key",
    }
    govern_instance = MagicMock()
    govern_instance.node_id = "govern_node"
    govern_instance.node_name = "IKU"
    govern_instance.node_type = "GOVERN"
    govern_client.get_instance_info.return_value = govern_instance

    # Blueprints
    bp_item = MagicMock()
    bp_item.get_raw.return_value = {
        "blueprint": {
            "id": "bp.system.govern_project",
            "name": "Govern project",
            "icon": "account_balance_wallet",
            "color": "#1e75b3",
        },
    }
    govern_client.list_blueprints.return_value = [bp_item]

    bp_obj = MagicMock()
    bp_def = MagicMock()
    bp_def.get_raw.return_value = {
        "id": "bp.system.govern_project",
        "name": "Govern project",
    }
    bp_obj.get_definition.return_value = bp_def

    bp_ver_item = MagicMock()
    bp_ver_item.get_raw.return_value = {
        "blueprint": {
            "id": "bp.system.govern_project",
            "name": "Govern project",
        },
        "blueprintVersion": {
            "id": {
                "blueprintId": "bp.system.govern_project",
                "versionId": "bv.system.default",
            },
            "name": "Default",
        },
        "blueprintVersionTrace": {
            "status": "ACTIVE",
        },
    }
    bp_obj.list_versions.return_value = [bp_ver_item]

    bp_ver = MagicMock()
    bp_ver_def = MagicMock()
    bp_ver_def.get_raw.return_value = {
        "id": {
            "blueprintId": "bp.system.govern_project",
            "versionId": "bv.system.default",
        },
        "name": "Default",
        "fieldDefinitions": {
            "description": {
                "label": "Description",
                "fieldType": "TEXT",
                "sourceType": "STORE",
                "required": False,
            },
            "cost_rating": {
                "label": "Cost rating",
                "fieldType": "CATEGORY",
                "sourceType": "STORE",
                "required": False,
                "categories": ["Low", "Medium low", "Medium high", "High"],
            },
            "countries": {
                "label": "Countries",
                "fieldType": "CATEGORY",
                "sourceType": "STORE",
                "required": False,
                "listConfig": {"cardinalityMin": 0},
                "categories": ["Global", "France", "Germany"],
            },
            "start_date": {
                "label": "Start date",
                "fieldType": "DATE",
                "sourceType": "STORE",
                "required": False,
            },
            "business_initiative": {
                "label": "Business initiative",
                "fieldType": "REFERENCE",
                "sourceType": "STORE",
                "required": False,
                "allowedBlueprints": ["bp.system.business_initiative"],
            },
            "govern_models": {
                "label": "Governed models",
                "fieldType": "REFERENCE",
                "sourceType": "COMPUTE",
                "required": False,
            },
        },
    }
    bp_ver.get_definition.return_value = bp_ver_def
    bp_obj.get_version.return_value = bp_ver
    govern_client.get_blueprint.return_value = bp_obj

    # Artifacts — search
    search_req = MagicMock()
    search_resp = MagicMock()
    search_hit = MagicMock()
    search_hit.get_raw.return_value = {
        "artifact": {
            "id": "ar.5",
            "name": "Test Project",
            "blueprintVersionId": {
                "blueprintId": "bp.system.govern_project",
                "versionId": "bv.system.default",
            },
            "status": {"archived": False},
            "workflow": {
                "steps": {"exploration": {"status": "ONGOING", "visible": True}},
            },
            # Field values surfaced by `govern artifact list --field KEY=VALUE`.
            "fields": {"sensitive_data": "Yes"},
        },
    }
    search_resp.get_response_hits.return_value = [search_hit]
    # Second fetch returns empty to stop --all pagination
    search_resp_empty = MagicMock()
    search_resp_empty.get_response_hits.return_value = []
    search_req.fetch_next_batch.side_effect = [search_resp, search_resp_empty]
    govern_client.new_artifact_search_request.return_value = search_req

    # Artifact CRUD
    artifact_obj = MagicMock()
    artifact_def = MagicMock()
    artifact_def.get_raw.return_value = {
        "id": "ar.5",
        "name": "Test Project",
        "blueprintVersionId": {
            "blueprintId": "bp.system.govern_project",
            "versionId": "bv.system.default",
        },
        "fields": {"description": "A test project"},
    }
    artifact_obj.get_definition.return_value = artifact_def
    artifact_obj.delete.return_value = None
    artifact_obj.artifact_id = "ar.5"

    # Sign-offs
    signoff_item = MagicMock()
    signoff_item.get_raw.return_value = {
        "signoffId": {"stepId": "exploration"},
        "status": "ONGOING",
    }
    artifact_obj.list_signoffs.return_value = [signoff_item]

    signoff_obj = MagicMock()
    signoff_def = MagicMock()
    signoff_def.get_raw.return_value = {"status": "NOT_STARTED", "configuration": {}}
    signoff_obj.get_definition.return_value = signoff_def
    signoff_details = MagicMock()
    signoff_details.get_raw.return_value = {
        "feedbackGroups": [],
        "approvers": [],
    }
    signoff_obj.get_details.return_value = signoff_details
    signoff_obj.update_status.return_value = None
    signoff_obj.add_feedback.return_value = MagicMock()
    signoff_obj.add_approval.return_value = MagicMock()
    signoff_obj.delegate_feedback.return_value = None
    signoff_obj.delegate_approval.return_value = None

    # Feedbacks on signoff
    feedback_item = MagicMock()
    feedback_item.get_raw.return_value = {
        "id": "fb.1",
        "status": "APPROVED",
        "groupId": "business_reviewers",
        "user": "alice",
    }
    signoff_obj.list_feedbacks.return_value = [feedback_item]
    feedback_obj = MagicMock()
    feedback_def = MagicMock()
    feedback_def.get_raw.return_value = {
        "id": "fb.1",
        "status": "APPROVED",
        "groupId": "business_reviewers",
        "user": "alice",
        "comment": "Looks good",
    }
    feedback_obj.get_definition.return_value = feedback_def
    signoff_obj.get_feedback.return_value = feedback_obj

    # Approval on signoff
    approval_obj = MagicMock()
    approval_def = MagicMock()
    approval_def.get_raw.return_value = {
        "status": "APPROVED",
        "user": "bob",
        "comment": "Ship it",
    }
    approval_obj.get_definition.return_value = approval_def
    signoff_obj.get_approval.return_value = approval_obj

    artifact_obj.get_signoff.return_value = signoff_obj
    artifact_obj.create_signoff.return_value = signoff_obj

    govern_client.get_artifact.return_value = artifact_obj
    govern_client.create_artifact.return_value = artifact_obj

    # Roles
    roles_handler = MagicMock()
    role_item = MagicMock()
    role_item.get_raw.return_value = {
        "id": "ro.project_manager",
        "label": "Project manager",
        "description": "Manage and govern projects",
    }
    roles_handler.list_roles.return_value = [role_item]
    role_obj = MagicMock()
    role_def = MagicMock()
    role_def.get_raw.return_value = {
        "id": "ro.project_manager",
        "label": "Project manager",
        "description": "Manage and govern projects",
    }
    role_obj.get_definition.return_value = role_def
    roles_handler.get_role.return_value = role_obj

    # Role assignments — `dku govern role-assignment list/get/set/delete`.
    # One existing record: bp.system.govern_project binds role ro.reviewer.
    ra_item = MagicMock()
    ra_item.get_raw.return_value = {
        "blueprintId": "bp.system.govern_project",
        "roleAssignmentsRules": {
            "ro.reviewer": [{"criteria": [], "userContainers": [], "fieldIds": []}]
        },
    }
    roles_handler.list_role_assignments.return_value = [ra_item]
    ra_def = MagicMock()
    ra_def.get_raw.return_value = {
        "blueprintId": "bp.system.govern_project",
        "roleAssignmentsRules": {
            "ro.reviewer": [{"criteria": [], "userContainers": [], "fieldIds": []}]
        },
    }
    ra_record = MagicMock()
    ra_record.get_definition.return_value = ra_def
    roles_handler.get_role_assignments.return_value = ra_record

    govern_client.get_roles_permissions_handler.return_value = roles_handler

    # Custom pages
    page_item = MagicMock()
    page_item.get_raw.return_value = {
        "type": "standard-page",
        "id": "cp.system.governable-items",
        "name": "Governable Items",
        "icon": "",
        "visible": True,
    }
    govern_client.list_custom_pages.return_value = [page_item]
    page_obj = MagicMock()
    page_def = MagicMock()
    page_def.get_raw.return_value = {
        "type": "standard-page",
        "id": "cp.system.governable-items",
        "name": "Governable Items",
    }
    page_obj.get_definition.return_value = page_def
    govern_client.get_custom_page.return_value = page_obj

    # Custom pages handler (admin)
    custom_pages_handler = MagicMock()
    admin_page_item = MagicMock()
    admin_page_item.get_raw.return_value = {
        "id": "cp.system.governable-items",
        "name": "Governable Items",
    }
    custom_pages_handler.list_custom_pages.return_value = [admin_page_item]
    admin_page_obj = MagicMock()
    admin_page_obj.custom_page_id = "cp.system.governable-items"
    admin_page_def = MagicMock()
    admin_page_def.get_raw.return_value = {
        "id": "cp.system.governable-items",
        "name": "Governable Items",
    }
    admin_page_obj.get_definition.return_value = admin_page_def
    custom_pages_handler.get_custom_page.return_value = admin_page_obj
    custom_pages_handler.create_custom_page.return_value = admin_page_obj
    govern_client.get_custom_pages_handler.return_value = custom_pages_handler

    # Blueprint designer (admin) — wired via tests.fixtures.govern_designer
    from tests.fixtures.govern_designer import wire_designer_mocks

    wire_designer_mocks(govern_client, bp_ver_item, bp_ver)

    # Role create (admin)
    admin_role_obj = MagicMock()
    admin_role_obj.role_id = "ro.custom_role"
    roles_handler.create_role.return_value = admin_role_obj

    # Users
    govern_client.list_users.return_value = [
        {
            "login": "alice",
            "displayName": "Alice Smith",
            "email": "alice@example.com",
            "groups": ["data_team"],
            "enabled": True,
        }
    ]
    user_obj = MagicMock()
    user_settings = MagicMock()
    user_settings.get_raw.return_value = {
        "login": "alice",
        "displayName": "Alice Smith",
        "email": "alice@example.com",
        "groups": ["data_team"],
        "enabled": True,
    }
    user_obj.get_settings.return_value = user_settings
    govern_client.get_user.return_value = user_obj
    govern_client.create_user.return_value = user_obj
    govern_client.create_users.return_value = [
        {"login": "bob", "status": "SUCCESS", "error": ""}
    ]
    govern_client.edit_users.return_value = [
        {"login": "alice", "status": "SUCCESS", "error": ""}
    ]
    govern_client.delete_users.return_value = [
        {"login": "alice", "status": "SUCCESS", "error": ""}
    ]

    # Own user
    own_user_obj = MagicMock()
    own_user_settings = MagicMock()
    own_user_settings.get_raw.return_value = {
        "login": "me",
        "displayName": "Current User",
        "email": "me@example.com",
    }
    own_user_obj.get_settings.return_value = own_user_settings
    govern_client.get_own_user.return_value = own_user_obj

    # Users activity
    user_activity = MagicMock()
    user_activity.login = "alice"
    user_activity.get_raw.return_value = {
        "login": "alice",
        "lastSuccessfulLogin": 1700000000000,
        "lastFailedLogin": 0,
        "lastSessionActivity": 1700000000000,
    }
    govern_client.list_users_activity.return_value = [user_activity]

    # Groups
    govern_client.list_groups.return_value = [
        {"name": "data_team", "description": "Data team", "sourceType": "LOCAL"}
    ]
    group_obj = MagicMock()
    group_obj.get_definition.return_value = {
        "name": "data_team",
        "description": "Data team",
        "sourceType": "LOCAL",
    }
    govern_client.get_group.return_value = group_obj
    govern_client.create_group.return_value = group_obj

    # Time series
    ts_obj = MagicMock()
    ts_obj.time_series_id = "ts.1"
    ts_obj.get_values.return_value = [{"timestamp": 1700000000000, "value": 42}]
    govern_client.create_time_series.return_value = ts_obj
    govern_client.get_time_series.return_value = ts_obj

    # Uploaded files
    uploaded_file_obj = MagicMock()
    uploaded_file_obj.uploaded_file_id = "uf.1"
    uploaded_file_obj.get_description.return_value = {
        "id": "uf.1",
        "name": "report.pdf",
        "fileName": "report.pdf",
        "contentType": "application/pdf",
    }
    from io import BytesIO

    uploaded_file_obj.download.return_value = BytesIO(b"fake file content")
    govern_client.upload_file.return_value = uploaded_file_obj
    govern_client.get_uploaded_file.return_value = uploaded_file_obj

    client.get_govern_client.return_value = govern_client
