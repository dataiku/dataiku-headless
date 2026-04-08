# Dataiku Govern — CLI Reference & Patterns

Dataiku Govern is a standalone governance platform for tracking AI/ML projects through structured workflows. It manages **artifacts** (governed items) that follow **blueprints** (schemas), progress through **workflow steps**, and require **sign-offs** (reviews and approvals) at each stage.

Govern is accessed through a DSS instance that has Govern integration enabled. The `dku` CLI uses `DSSClient.get_govern_client()` under the hood — this requires an admin API key on the DSS side.

## Concepts

| Concept | What it is | Example |
|---------|-----------|---------|
| **Blueprint** | Schema template defining fields, workflow steps, and signoff rules | `bp.system.govern_project` — the built-in Govern Project blueprint |
| **Blueprint Version** | Versioned snapshot of a blueprint definition | `bv.system.default` — always exists |
| **Artifact** | An instance of a blueprint — the actual governed item | `ar.100` — a specific project being governed |
| **Workflow Step** | A named stage in the artifact lifecycle | `exploration`, `qualification`, `progress`, `rollout`, `delivery` |
| **Sign-off** | Review+approval gate on a workflow step | Feedback from reviewers + final approval from approver |
| **Role** | Permission template assignable to users on artifacts | `ro.project_manager`, `ro.contributor`, `ro.reader` |
| **Custom Page** | A custom view/dashboard in the Govern UI | `cp.system.governable-items` |
| **Time Series** | Timestamped data points attached to artifacts | Metrics tracking over time |
| **Uploaded File** | File attachment on an artifact | Progress documents, qualification docs |

## Command Groups Overview

```
govern              # Instance info: whoami, info
govern artifact     # CRUD on governed items: list, get, create, delete, set-field, set-definition
govern blueprint    # Schema discovery: list, get, list-versions, get-version, fields, create, set-definition
govern signoff      # Workflow gates: create, list, get, update-status, add-feedback, add-approval, delegate-feedback, delegate-approval, list-feedbacks, get-feedback, get-approval
govern role         # Access control: list, get, create, set-definition, delete
govern custom-page  # UI pages: list, get, create, set-definition, delete
govern user         # User admin: list, get, create, create-bulk, edit-bulk, delete-bulk, get-own, list-activity
govern group        # Group admin: list, get, create, delete
govern time-series  # Metrics: create, get, push-values, delete
govern file         # Attachments: upload, get, download
```

---

## Quick Start — Common Workflows

### 1. Discover what's in Govern

```bash
# Who am I?
dku govern whoami

# What blueprints exist?
dku govern blueprint list

# What fields does a blueprint have? (agents MUST run this before creating artifacts)
dku govern blueprint fields bp.system.govern_project

# What artifacts exist?
dku govern artifact list -b bp.system.govern_project

# What roles exist?
dku govern role list
```

### 2. Create and manage an artifact

```bash
# Discover fields first
dku govern blueprint fields bp.system.govern_project

# Create with flags (ergonomic — no JSON needed)
dku govern artifact create \
  -b bp.system.govern_project \
  -n "Customer Churn Prediction" \
  -f description="ML model to predict customer churn" \
  -f cost_rating=High \
  -f sensitive_data=Yes \
  -f countries='["France","Germany"]'

# Update a single field
dku govern artifact set-field ar.100 cost_rating "Medium low"

# Get full artifact definition
dku govern artifact get ar.100 -o json
```

### 3. Run a sign-off workflow

```bash
# List signoffs on an artifact
dku govern signoff list ar.100

# Get signoff details (shows who needs to review)
dku govern signoff get ar.100 exploration -o json

# Move to feedback phase
dku govern signoff update-status ar.100 exploration WAITING_FOR_FEEDBACK

# Delegate feedback to a user
dku govern signoff delegate-feedback ar.100 exploration \
  --group-id reviewer_grp \
  --users-container '{"type": "user", "login": "alice"}'

# Add feedback
dku govern signoff add-feedback ar.100 exploration \
  --group-id reviewer_grp \
  --status APPROVED \
  --comment "Exploration looks solid"

# List all feedbacks
dku govern signoff list-feedbacks ar.100 exploration

# Move to approval phase
dku govern signoff update-status ar.100 exploration WAITING_FOR_APPROVAL

# Add final approval
dku govern signoff add-approval ar.100 exploration \
  --status APPROVED \
  --comment "Ship it"
```

### 4. Manage users and groups

```bash
# List users
dku govern user list

# Create a user
dku govern user create alice --password "SecurePass123!" \
  --display-name "Alice Smith" \
  --email "alice@company.com" \
  --group data_team --group reviewers

# Bulk create
dku govern user create-bulk --definition '[
  {"login": "bob", "password": "Pass1!", "displayName": "Bob", "groups": ["data_team"]},
  {"login": "carol", "password": "Pass2!", "displayName": "Carol", "email": "carol@co.com"}
]'

# Bulk edit
dku govern user edit-bulk --definition '[
  {"login": "bob", "displayName": "Bob Updated", "groups": ["data_team", "reviewers"]}
]'

# Bulk delete (requires --confirm)
dku govern user delete-bulk --definition '["bob", "carol"]' --confirm

# Create a group
dku govern group create ml_reviewers --description "ML model reviewers"
```

---

## Detailed Command Reference

### govern

```bash
dku govern whoami [-o FORMAT]        # Show authenticated Govern user/API key
dku govern info [-o FORMAT]          # Show Govern node info (id, name, type)
```

### govern artifact

```bash
# Search/list
dku govern artifact list [-b BLUEPRINT_ID] [-n NAME_FILTER] [--archived|--no-archived] [--page-size N] [--all] [-o FORMAT]

# CRUD
dku govern artifact get ARTIFACT_ID [-o FORMAT]
dku govern artifact create -b BLUEPRINT_ID -n NAME [-f key=value ...] [-o FORMAT]
dku govern artifact create --definition JSON [-o FORMAT]
dku govern artifact delete ARTIFACT_ID --confirm

# Field updates
dku govern artifact set-field ARTIFACT_ID FIELD_ID VALUE
dku govern artifact set-definition ARTIFACT_ID --definition JSON
```

**Create modes:**

1. **Ergonomic** (flags): `create -b bp.system.govern_project -n "Name" -f key=value`
2. **Raw JSON**: `create --definition '{"blueprintVersionId": {...}, "name": "...", "fields": {...}}'`

**Field value formats:**

| Field Type | Value format | Example |
|-----------|-------------|---------|
| TEXT | Plain string | `-f description="Some text"` |
| CATEGORY | Category value (must match allowed values) | `-f cost_rating=High` |
| NUMBER | Numeric | `-f qualification_risk_score=7.5` |
| DATE | ISO 8601 string | `-f start_date="2025-01-15T00:00:00.000Z"` |
| REFERENCE | Artifact ID | `-f business_initiative=ar.10` |
| UPLOADED_FILE | File ID | `-f progress_docs='["uf.1"]'` |
| List field | JSON array (even for single value) | `-f countries='["France","Germany"]'` |

**Search filters:**

- `-b bp.system.govern_project` — filter by blueprint
- `-n "churn"` — filter by name (contains, case-insensitive)
- `--archived` / `--no-archived` — filter by archive status
- `--all` — fetch all pages (default: first page only, 50 results)

### govern blueprint

```bash
# Discovery (no admin needed)
dku govern blueprint list [-o FORMAT]
dku govern blueprint get BLUEPRINT_ID [-o FORMAT]
dku govern blueprint list-versions BLUEPRINT_ID [-o FORMAT]
dku govern blueprint get-version BLUEPRINT_ID VERSION_ID [-o FORMAT]
dku govern blueprint fields BLUEPRINT_ID [--version VERSION_ID] [-o FORMAT]

# Admin/architect commands
dku govern blueprint create IDENTIFIER --definition JSON [-o FORMAT]
dku govern blueprint set-definition BLUEPRINT_ID --definition JSON
```

**`fields` command output columns:**

| Column | Meaning |
|--------|---------|
| FIELD ID | The key to use in `--field` or `set-field` |
| TYPE | TEXT, CATEGORY, NUMBER, DATE, REFERENCE, UPLOADED_FILE |
| LIST | `*` if field accepts arrays |
| REQ | `*` if field is required |
| LABEL | Human-readable label |
| CATEGORIES / ALLOWED REFS | Valid values for CATEGORY fields; allowed blueprint IDs for REFERENCE fields |

Fields with sourceType `COMPUTE` are auto-calculated and hidden from the output (agents can't set them).

**Creating a blueprint (admin):**

```bash
dku govern blueprint create my_custom_bp --definition '{
  "name": "My Custom Blueprint",
  "icon": "science",
  "color": "#ff6600"
}'
```

The `IDENTIFIER` becomes `bp.<identifier>`. Allowed characters: letters, digits, hyphen, underscore.

### govern signoff

```bash
# Lifecycle
dku govern signoff create ARTIFACT_ID STEP_ID
dku govern signoff list ARTIFACT_ID [-o FORMAT]
dku govern signoff get ARTIFACT_ID STEP_ID [-o FORMAT]
dku govern signoff update-status ARTIFACT_ID STEP_ID STATUS

# Feedback
dku govern signoff add-feedback ARTIFACT_ID STEP_ID -g GROUP_ID -s STATUS [-c COMMENT]
dku govern signoff list-feedbacks ARTIFACT_ID STEP_ID [-o FORMAT]
dku govern signoff get-feedback ARTIFACT_ID STEP_ID FEEDBACK_ID [-o FORMAT]
dku govern signoff delegate-feedback ARTIFACT_ID STEP_ID -g GROUP_ID --users-container JSON

# Approval
dku govern signoff add-approval ARTIFACT_ID STEP_ID -s STATUS [-c COMMENT]
dku govern signoff get-approval ARTIFACT_ID STEP_ID [-o FORMAT]
dku govern signoff delegate-approval ARTIFACT_ID STEP_ID --users-container JSON
```

**Sign-off status state machine:**

```
NOT_STARTED → WAITING_FOR_FEEDBACK → WAITING_FOR_APPROVAL → APPROVED
                                                           → REJECTED
                                                           → ABANDONED
WAITING_FOR_FEEDBACK → ABANDONED → NOT_STARTED (reset)
WAITING_FOR_APPROVAL → ABANDONED → NOT_STARTED (reset)
```

- `NOT_STARTED` → `WAITING_FOR_FEEDBACK` or `WAITING_FOR_APPROVAL`
- Cannot go from `WAITING_FOR_*` directly back to `NOT_STARTED` — must go through `ABANDONED` first
- When resetting to `NOT_STARTED`, pass `reload_conf_for_reset=True` via the API to refresh the signoff configuration from the blueprint version

**Feedback statuses:** `APPROVED`, `MINOR_ISSUE`, `MAJOR_ISSUE`

**Approval statuses:** `APPROVED`, `REJECTED`, `ABANDONED`

**Users container JSON format** (for delegate commands):

```json
{"type": "user", "login": "alice"}
```

The `type` must be `"user"` (lowercase). The only supported type for delegation via CLI.

**Prerequisites for signoffs:**

1. The workflow step must be `ONGOING` on the artifact (not `NOT_STARTED`)
2. A signoff configuration must exist on the blueprint version for that step
3. The signoff must be created on the artifact (`govern signoff create`)
4. Users must be in the configured feedback/approval groups to submit reviews

If signoff creation fails with "workflow step is not active", the step needs to be activated first. If it fails with "no sign-off configuration exists", a Govern architect must configure the signoff on the blueprint version.

### govern role

```bash
dku govern role list [-o FORMAT]
dku govern role get ROLE_ID [-o FORMAT]
dku govern role create IDENTIFIER --definition JSON
dku govern role set-definition ROLE_ID --definition JSON
dku govern role delete ROLE_ID --confirm
```

**Creating a role:**

```bash
dku govern role create data_steward --definition '{
  "label": "Data Steward",
  "description": "Responsible for data quality and lineage"
}'
```

The `IDENTIFIER` becomes `ro.<identifier>`.

**Built-in roles:**

| Role ID | Purpose |
|---------|---------|
| `ro.project_manager` | Full project management |
| `ro.contributor` | Can contribute to models |
| `ro.reader` | Read-only access |
| `ro.it_operations_reviewer` | IT & Operations feedback group |
| `ro.risk_compliance_reviewer` | Risk & Compliance feedback group |
| `ro.business_reviewer` | Business feedback group |
| `ro.final_approver` | Final signoff approval |

### govern custom-page

```bash
dku govern custom-page list [-o FORMAT]
dku govern custom-page get PAGE_ID [-o FORMAT]
dku govern custom-page create IDENTIFIER --definition JSON
dku govern custom-page set-definition PAGE_ID --definition JSON
dku govern custom-page delete PAGE_ID --confirm
```

**Creating a custom page:**

```bash
dku govern custom-page create risk_dashboard --definition '{
  "name": "Risk Dashboard",
  "type": "artifact-table",
  "visible": true,
  "icon": "warning"
}'
```

Page types: `standard-page`, `artifact-table`.

The `IDENTIFIER` becomes `cp.<identifier>`.

### govern user

```bash
dku govern user list [-o FORMAT]
dku govern user get LOGIN [-o FORMAT]
dku govern user create LOGIN --password PASS [--display-name NAME] [--email EMAIL] [--group GROUP ...] [--profile PROFILE] [--source-type LOCAL|LDAP]
dku govern user create-bulk --definition JSON [-o FORMAT]
dku govern user edit-bulk --definition JSON [-o FORMAT]
dku govern user delete-bulk --definition JSON --confirm [-o FORMAT]
dku govern user get-own [-o FORMAT]
dku govern user list-activity [--enabled-only] [-o FORMAT]
```

**Bulk create JSON format:**

```json
[
  {
    "login": "alice",
    "password": "SecurePass1!",
    "displayName": "Alice Smith",
    "sourceType": "LOCAL",
    "groups": ["data_team", "reviewers"],
    "userProfile": "DATA_SCIENTIST",
    "email": "alice@company.com"
  }
]
```

All fields except `login` and `password` have defaults: `sourceType` = `"LOCAL"`, `groups` = `[]`, `userProfile` = `"DATA_SCIENTIST"`.

**Bulk edit JSON format:**

```json
[
  {
    "login": "alice",
    "displayName": "Alice Updated",
    "groups": ["data_team", "reviewers", "approvers"],
    "enabled": true
  }
]
```

The `login` key is mandatory (identifies the user). All other keys are optional — only included keys are modified.

**Bulk delete JSON format:**

```json
["alice", "bob", "carol"]
```

A simple array of login strings. Requires `--confirm` flag.

**User profiles:** `FULL_DESIGNER`, `DATA_DESIGNER`, `AI_CONSUMER`, `DATA_SCIENTIST`, `TECHNICAL_ACCOUNT`

**`get-own`** only works with user-session auth (not API keys). API key auth will return an auth error.

### govern group

```bash
dku govern group list [-o FORMAT]
dku govern group get GROUP_NAME [-o FORMAT]
dku govern group create GROUP_NAME [--description DESC] [--source-type LOCAL|LDAP]
dku govern group delete GROUP_NAME --confirm
```

### govern time-series

```bash
dku govern time-series create [--datapoints JSON] [-o FORMAT]
dku govern time-series get TIME_SERIES_ID [--min EPOCH_MS] [--max EPOCH_MS] [-o FORMAT]
dku govern time-series push-values TIME_SERIES_ID --datapoints JSON [--no-upsert]
dku govern time-series delete TIME_SERIES_ID [--min EPOCH_MS] [--max EPOCH_MS] --confirm
```

**Datapoint JSON format:**

```json
[
  {"timestamp": 1700000000000, "value": 42},
  {"timestamp": 1700000060000, "value": 99.5}
]
```

- `timestamp`: epoch in **milliseconds** (not seconds)
- `value`: any JSON value (number, string, object)
- Time series are referenced by ID (e.g. `ts.1`) — typically stored in artifact fields

### govern file

```bash
dku govern file upload FILE_PATH [-o FORMAT]
dku govern file get FILE_ID [-o FORMAT]
dku govern file download FILE_ID [--dest PATH]
```

- `upload` takes a local file path, returns the uploaded file ID (e.g. `uf.1`)
- Uploaded file IDs are used in artifact `UPLOADED_FILE` fields as arrays: `'["uf.1", "uf.2"]'`

---

## Blueprint Version Definition Structure

When creating or modifying blueprint versions via the admin API, the definition follows this structure:

```json
{
  "id": {
    "blueprintId": "bp.my_blueprint",
    "versionId": "bv.system.default"
  },
  "name": "Default",
  "fieldDefinitions": {
    "description": {
      "label": "Description",
      "fieldType": "TEXT",
      "sourceType": "STORE",
      "required": false
    },
    "risk_level": {
      "label": "Risk Level",
      "fieldType": "CATEGORY",
      "sourceType": "STORE",
      "required": true,
      "categories": ["Low", "Medium", "High"]
    },
    "owner": {
      "label": "Owner",
      "fieldType": "REFERENCE",
      "sourceType": "STORE",
      "required": true,
      "allowedBlueprints": ["bp.system.user", "bp.system.group"]
    },
    "documents": {
      "label": "Documents",
      "fieldType": "UPLOADED_FILE",
      "sourceType": "STORE",
      "listConfig": {},
      "required": false
    }
  },
  "workflowDefinition": {
    "stepDefinitions": [
      {"id": "exploration", "name": "Exploration"},
      {"id": "qualification", "name": "Qualification"},
      {"id": "delivery", "name": "Delivered"}
    ]
  }
}
```

**Field types:**

| fieldType | sourceType | Description |
|-----------|-----------|-------------|
| `TEXT` | `STORE` | Free text, set by user |
| `CATEGORY` | `STORE` | Constrained value from `categories` list |
| `NUMBER` | `STORE` | Numeric value |
| `DATE` | `STORE` | ISO 8601 datetime |
| `REFERENCE` | `STORE` | Link to another artifact (by ID) |
| `UPLOADED_FILE` | `STORE` | Attached file (by uploaded file ID) |
| `*` | `COMPUTE` | Auto-calculated — cannot be set by users/agents |

Add `"listConfig": {}` to any field to make it accept arrays.

## Signoff Configuration Structure

Signoff configurations are created on blueprint versions and define who reviews at each workflow step:

```json
{
  "title": "Exploration Review",
  "feedbackUsersGroups": [
    {
      "id": "business_review",
      "title": "Business Reviewers",
      "usersContainer": {
        "type": "user",
        "login": "alice"
      }
    }
  ],
  "approverConfiguration": {
    "usersContainer": {
      "type": "user",
      "login": "bob"
    }
  }
}
```

**Users container types for signoff configuration:**

| Type | JSON | Use case |
|------|------|----------|
| Single user | `{"type": "user", "login": "alice"}` | Specific user as reviewer |
| Field reference | `{"type": "FIELD", "fieldId": "signoff_reviewers_business"}` | Resolve users from a REFERENCE field on the artifact |
| Group | `{"type": "group", "groupName": "administrators"}` | All members of a Govern group |

**Important:** Each `feedbackUsersGroups` entry requires both `id` and `title`. The `id` is the group identifier used in `add-feedback --group-id` and `delegate-feedback --group-id`.

---

## Artifact Definition Structure (Raw JSON)

When using `create --definition` or `set-definition`, the full artifact JSON looks like:

```json
{
  "blueprintVersionId": {
    "blueprintId": "bp.system.govern_project",
    "versionId": "bv.system.default"
  },
  "name": "Customer Churn Prediction",
  "fields": {
    "description": "ML model to predict customer churn in Q1",
    "cost_rating": "High",
    "sensitive_data": "Yes",
    "countries": ["France", "Germany"],
    "start_date": "2025-01-15T00:00:00.000Z",
    "business_initiative": "ar.10",
    "progress_docs": ["uf.1", "uf.2"],
    "qualification_risk_score": 7.5
  }
}
```

---

## Gotchas

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Govern integration is not enabled` | DSS doesn't have Govern configured or API key lacks admin rights | Enable Govern in DSS Administration > Settings > Govern. Use an admin API key |
| `No sign-off configuration exists` | Blueprint version has no signoff config for that step | Ask a Govern architect to add signoff config, or use the admin API: `get_blueprint_designer()` |
| `workflow step is not active` | Step status is `NOT_STARTED`, not `ONGOING` | Check artifact workflow state with `govern artifact get AR_ID -o json` — the step must be `ONGOING` |
| `Cannot set status to NOT_STARTED` | Can't go directly from `WAITING_FOR_*` to `NOT_STARTED` | Transition through `ABANDONED` first, then to `NOT_STARTED` |
| `User/API key is not part of the group` | The authenticated identity isn't in the signoff feedback/approval group | Use `delegate-feedback` or `delegate-approval` to add the user, or authenticate as a user in the group |
| `get-own` fails with auth error | Using API key auth instead of user session | `get-own` only works with user session auth, not API keys |
| `feedbackUsersGroups` is empty after config | Used `feedbackGroups` key instead of `feedbackUsersGroups` | The signoff configuration key is `feedbackUsersGroups`, not `feedbackGroups` |
| `SignoffConfiguration title is required` | Missing `title` in signoff config | Add `"title": "..."` to the signoff configuration JSON |
| `Users group title is required` | Feedback group missing `title` | Each entry in `feedbackUsersGroups` needs both `id` and `title` |
| List field rejected | Passed single value instead of array | List fields (marked `*` in `fields` output) require JSON arrays even for single values: `'["France"]'` |
| `unknown type "SINGLE_USER"` | Wrong users container type | Use `"type": "user"` (lowercase, no prefix) — not `"SINGLE_USER"` |
| Blueprint field values silently ignored | Field ID doesn't match blueprint version | Run `dku govern blueprint fields BP_ID` to get exact field IDs |
| Bulk create returns FAILURE for a user | User already exists or invalid params | Check the `error` column in the output table for the specific failure reason |
