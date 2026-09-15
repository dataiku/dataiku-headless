---
name: govern
description: Operate Dataiku Govern through the single govern tool, with task guides for artifacts, blueprints, signoffs, and supporting objects.
---

# Govern

Govern runs on a separate node. Its records are artifacts described by blueprint
versions, with workflow steps and signoffs. A governed project is an artifact;
it is not a DSS project containing datasets and recipes.

Use the `govern` tool for every Govern read and write. It wraps the public Govern
Python SDK behind a fixed catalog of 86 operations. Do not fall back to Python,
`dataikuapi`, or REST calls; if an operation is missing, report the gap.
DSS project work still uses the other MCP tools and Cobuild.

## The tool

`govern(operation, params, domain)`:

- Empty `operation` returns the catalog: every operation with its domain, kind
  (`read`, `write`, `delete`), parameters, and the SDK method it wraps. Set
  `domain` to filter: `artifacts`, `signoffs`, `blueprints`, `roles`,
  `custom_pages`, `time_series`, `files`, `users`, `instance`.
- `operation` plus `params` runs one operation. `params` is one flat JSON object
  holding identifiers, payloads, and options exactly as the catalog names them.
  Unknown keys and missing required keys are rejected before any call.
- Results are the SDK raw dictionaries: definitions, list items, or a small
  status object for deletions.

## Connect

The Govern node needs its own URL and API key. The tool reads them from
`DKU_GOVERN_URL` and `DKU_GOVERN_API_KEY` in the MCP server environment
(`DKU_GOVERN_NO_CHECK_CERTIFICATE` is optional), and otherwise from the Govern
node fields of the active instance profile, entered through `configure_instance`.
Environment variables win. `get_current_instance` shows `govern_url` and whether a
Govern key is present; it never shows the key.

Start a Govern task with `get_instance_info`: it confirms the node type is
`GOVERN` and reports the server version. Then `get_auth_info` tells which identity
signs the work. A global API key has no user behind it: `get_own_user` fails and
decisions are recorded under the key identity; a personal API key records them
under that user. If the tool reports a missing Govern configuration or a
permission error, report that specific blocker; do not repurpose DSS credentials.

Blueprint design and custom page administration need the Govern Blueprint Designer
license option. Without it the server answers "Your license does not allow you to
use the Govern Blueprint Designer" for `create_blueprint`, version and signoff
configuration writes, and custom page writes and ordering. Report that as a
licensing blocker, not as a tool gap.

## Workflow

1. Call `govern` with an empty `operation` for the relevant `domain` when the
   parameters of an operation are not in context. Never guess an operation id.
2. Discover identifiers through `list_blueprints`, `list_blueprint_versions`,
   `search_artifacts`, `list_roles`, `list_custom_pages`, `list_users`, and
   `list_groups`. Do not invent IDs.
3. Read the full target before changing it: `get_artifact`,
   `get_blueprint_version`, `get_signoff`, `get_role`, `get_custom_page_definition`.
4. Run the write with the exact `operation` and `params`. Update operations
   replace the complete definition unless the guide says merge.
5. Re-read after every write. The tool returns the persisted state, but compare it
   with the intended change; a successful save does not prove the values held.
6. For multi-step work, verify each unit and retain the created IDs. After an
   uncertain write, inspect before retrying a create.

## Parameter rules

- `update_artifact`, `update_blueprint`, `update_blueprint_version`,
  `update_signoff_configuration`, `update_role`, `update_role_assignments`,
  `update_blueprint_permissions`, `update_default_blueprint_permissions`,
  `update_custom_page`, and `update_signoff_recurrence` replace the whole
  definition. Send the full object read from the matching get operation with only
  the requested keys changed.
- `update_artifact_fields`, `update_user`, and `update_group` merge the given
  keys into the current definition and preserve the rest.
- `create_*` payloads never contain an `id`; the server derives it from
  `new_identifier` or the parent.
- Users containers in signoff configurations and role rules are
  `{"type": "user", "login": ...}`, `{"type": "group", "groupName": ...}`,
  `{"type": "role", "roleId": ...}`, or `{"type": "global-api-key", "globalAPIKeyId": ...}`.
  The type is lowercase. The `users_container` param of the two delegation
  operations accepts the `user` form only.
- `update_signoff_status` notifies every configured reviewer or approver when
  `users_to_notify` is omitted. Pass `[]` unless the task authorizes notifications.
- `update_blueprint_version` refuses a save that removes a field or changes its
  type on a version with artifacts. `danger_zone_accepted: true` discards that
  data everywhere; use it only after an explicit user decision.
- `search_artifacts` returns at most `max_results` hits (default 100) and
  `has_more`. Raise `max_results` or narrow the filters for a complete inventory,
  and say so when a result is a sample.

## Operations

| Domain | Operations |
| --- | --- |
| artifacts | `search_artifacts`, `get_artifact`, `create_artifact`, `update_artifact`, `update_artifact_fields`, `delete_artifact` |
| signoffs | `list_signoffs`, `get_signoff`, `get_signoff_details`, `create_signoff`, `update_signoff_status`, `list_signoff_feedbacks`, `get_signoff_feedback`, `add_signoff_feedback`, `update_signoff_feedback`, `delete_signoff_feedback`, `delegate_signoff_feedback`, `get_signoff_approval`, `add_signoff_approval`, `update_signoff_approval`, `delete_signoff_approval`, `delegate_signoff_approval`, `get_signoff_recurrence`, `update_signoff_recurrence` |
| blueprints | `list_blueprints`, `get_blueprint`, `list_blueprint_versions`, `get_blueprint_version`, `create_blueprint`, `update_blueprint`, `delete_blueprint`, `create_blueprint_version`, `update_blueprint_version`, `set_blueprint_version_status`, `delete_blueprint_version`, `list_signoff_configurations`, `get_signoff_configuration`, `create_signoff_configuration`, `update_signoff_configuration`, `delete_signoff_configuration` |
| roles | `list_roles`, `get_role`, `create_role`, `update_role`, `delete_role`, `list_role_assignments`, `get_role_assignments`, `create_role_assignments`, `update_role_assignments`, `delete_role_assignments`, `get_default_blueprint_permissions`, `update_default_blueprint_permissions`, `list_blueprint_permissions`, `get_blueprint_permissions`, `create_blueprint_permissions`, `update_blueprint_permissions`, `delete_blueprint_permissions` |
| custom_pages | `list_custom_pages`, `get_custom_page`, `get_custom_page_definition`, `create_custom_page`, `update_custom_page`, `delete_custom_page`, `get_custom_pages_order`, `update_custom_pages_order` |
| time_series | `create_time_series`, `get_time_series_values`, `push_time_series_values`, `delete_time_series_values` |
| files | `upload_file`, `get_uploaded_file`, `download_uploaded_file`, `delete_uploaded_file` |
| users | `list_users`, `get_user`, `create_user`, `update_user`, `delete_user`, `get_own_user`, `list_groups`, `get_group`, `create_group`, `update_group`, `delete_group` |
| instance | `get_instance_info`, `get_auth_info` |

Blueprint version import, bulk user provisioning, API keys, licensing, logs, and
identity-provider settings are not in the catalog. Report them as gaps and hand off
to the Govern UI.

## Choose the task guide

| Task | Read next |
| --- | --- |
| Discover, create, or update governed records; inspect field schemas | [Artifacts](./govern/artifacts.md) |
| Design blueprint versions, fields, workflow, views, or hooks | [Blueprints](./govern/blueprints.md) |
| Configure review gates or work with feedback, approvals, and workflow state | [Signoffs](./govern/signoffs.md) |
| Manage roles, permissions, custom pages, users, groups, files, or time series | [Supporting objects](./govern/supporting-objects.md) |

## Design the governance process

For process design, identify the item being governed, its parent, required evidence,
responsible roles, and the decision that each review gate records. Reuse a suitable
standard blueprint before designing a custom item type. Derive risk criteria and
approval rules from the user's policy; a plausible template is not an established policy.

Synced Dataiku assets and their governance layer are distinct. Discover an asset's
existing Govern record before creating another; a Govern project may also exist
before it is linked to a Dataiku project. A parent must be governed before its
children can be governed. Hiding a parent hides its children in Govern; it does
not delete them. See [Govern items](https://doc.dataiku.com/dss/latest/governance/types-govern-items.html)
and [governance actions](https://doc.dataiku.com/dss/latest/governance/governance-features.html).

Workflow progress, signoff approval, and deployment authorization are separate.
Use the configured signoff to record a decision. For deployment eligibility, inspect
the [Deployer infrastructure policy](https://doc.dataiku.com/dss/latest/governance/deployment-policies.html);
an `approved` field or a finished workflow step is not a deployment gate.

## Safety

- Every `write` and `delete` operation is a mutation. Let the harness obtain user
  confirmation before running one.
- Deleting a blueprint version requires deleting its artifacts first. Do not
  cascade-delete artifacts to unblock a schema change.
- Decisions (`add_signoff_feedback`, `add_signoff_approval`) are recorded under the
  authenticated identity. Do not alter reviewer membership to bypass a permission
  error; delegation changes who reviews and is not impersonation.
- Keep local paths explicit for `upload_file` and `download_uploaded_file`. Never
  expose API keys in payloads or responses.
