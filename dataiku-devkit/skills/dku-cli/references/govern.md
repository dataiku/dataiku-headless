# `dku govern` — GOVERN node operations

Govern nodes are a separate Dataiku product from Design/Automation. They have
**no projects, no datasets, no recipes, no flows**. Instead they expose a
governance schema (blueprints + blueprint versions) that describes governed
records (artifacts) and a review workflow (signoffs / feedbacks / approvals).

> When `dku whoami` shows `[GOVERN]`, every `dku <noun> ...` command other than
> `dku govern`, `dku user`, `dku group`, `dku admin instance-info`, `dku admin
> usage`, `dku admin logs`, `dku whoami`, and `dku auth *` will exit with code
> **4** and tell you to use `dku govern …` instead.

---

## Mental model

| Concept | Design/Automation analog | Shape |
|---|---|---|
| **Blueprint** (`bp.*`) | — (unique to Govern) | Schema: which fields an artifact has, which workflow steps, which signoff steps |
| **Blueprint version** (`bv.*`) | — | Snapshot of a blueprint at a point in time. `DRAFT` / `ACTIVE` / `ARCHIVED` |
| **Artifact** (`ar.*`) | like a "project" in DSS | One governed record: a business initiative, a governed model, an intake request, a use-case risk assessment |
| **Signoff** | — | One gate on an artifact (e.g. "Project Approval"). Has reviewer groups + one approver |
| **Feedback** | — | Reviewer group opinion on a signoff: `APPROVED` / `MINOR_ISSUE` / `MAJOR_ISSUE` |
| **Approval** | — | Final approver decision on a signoff: `APPROVED` / `REJECTED` / `ABANDONED` |
| **Role** (`ro.*`) | like a group | Reviewer/approver role, can be bound to users per blueprint |
| **Custom page** (`cp.*`) | — | Dashboard, intake form, or artifact table rendered in the Govern UI |
| **Uploaded file** (`uf.*`) | — | Attachment stored against a blueprint field (e.g. risk assessment doc) |

Identifiers use dotted prefixes: `bp.*`, `bv.*`, `ar.*`, `ro.*`, `cp.*`, `uf.*`, `ts.*` (time series). Keep them as literals — they are not human-readable but are stable.

---

## Setup

```bash
# One-time auth
dku auth login --url https://govern.example.com \
  --api-key dkuaps-… \
  --profile govern-prod
# Output includes:  Node type: GOVERN

dku whoami
# Shows  ◆ api:xyz on https://govern.example.com (DSS 14.5.1) [GOVERN] [groups...]

dku auth list
# Each profile shows its node type:
#   govern-prod *  [GOVERN]  https://govern.example.com  (key stored)
#   design-prod    [DESIGN]  https://design.example.com  (key stored)
```

A profile with `[?]` for node type was created before node-type tracking existed — re-run `dku auth login --profile <name>` to refresh.

---

## Cheat sheet — command groups

| Group | Verbs | Tier |
|---|---|---|
| `govern instance-info` / `govern usage` | — | R |
| `govern blueprint` | `list`, `get BP_ID`, `versions BP_ID` | R |
| `govern artifact` | `list`, `get AR`, `create --from-json`, `delete AR` | R/W/D (tier 2) |
| `govern signoff` | `list AR`, `get AR STEP`, `update-status AR STEP --status X`, `add-feedback`, `add-approval`, `feedback-list` | R/W |
| `govern role` | `list`, `get RO`, `assignments [--blueprint BP]` | R |
| `govern custom-page` | `list`, `get CP` | R |
| `govern uploaded-file` | `upload PATH`, `download UF --to PATH`, `delete UF` | R/W/D (tier 2) |
| `govern log` | `list`, `get NAME [--tail N]`, `custom-audit TYPE --params JSON` | R/W |

All destructive commands route through the standard `dku` safety guard. `--yes` for tier 2 (DELETE); no tier-3 / tier-4 Govern commands in the MVP.

---

## Canonical workflows

### Discover blueprints + find artifacts

```bash
dku govern blueprint list
# 26 blueprints — e.g. bp.system.business_initiative, bp.system.govern_project,
#                      bp.system.dataiku_dataset, bp.intake, bp.system.llm_vendor…

dku govern artifact list --blueprint bp.system.govern_project --limit 50
# Paged artifact search with blueprint filter

dku govern artifact list --name-contains "factory" -o json
# Full-text name search (case-insensitive), JSON for piping

dku govern artifact get ar.3375 -o json | jq '.workflow.steps'
# Inspect current workflow state for one artifact
```

### Inspect governance workflow state

```bash
dku govern signoff list ar.3214
# STEP_ID          TITLE              STATUS     CYCLE  FEEDBACK_COUNT  HAS_APPROVAL
# ai_system_creation  Project Approval  APPROVED  1      0               True

dku govern signoff get ar.3214 ai_system_creation -o json
# Full signoff: approvers, delegations, recurrence config, feedback responses
```

### Advance a signoff

```bash
# Move a signoff into the feedback-collection phase
dku govern signoff update-status ar.123 step1 --status WAITING_FOR_FEEDBACK

# Submit reviewer feedback as a group
dku govern signoff add-feedback ar.123 step1 \
  --group-id ro.risk_compliance_reviewer \
  --status APPROVED --comment "Risk mitigation satisfactory"

# Record the final approval
dku govern signoff add-approval ar.123 step1 \
  --status APPROVED --comment "Cleared for production"

# Reset a signoff (e.g. after configuration change)
dku govern signoff update-status ar.123 step1 --status NOT_STARTED --reload-conf
```

Valid workflow states:

- **Signoff status**: `NOT_STARTED`, `WAITING_FOR_FEEDBACK`, `WAITING_FOR_APPROVAL`, `APPROVED`, `REJECTED`, `ABANDONED`
- **Feedback status**: `APPROVED`, `MINOR_ISSUE`, `MAJOR_ISSUE`
- **Approval status**: `APPROVED`, `REJECTED`, `ABANDONED`

### Create an artifact

```bash
cat > new-usecase.json <<EOF
{
  "blueprintVersionId": {
    "blueprintId": "bp.intake",
    "versionId": "bv.llm_use_case_intake"
  },
  "name": "Fraud model v2 — initial intake",
  "fields": {
    "business_owner": "remy",
    "estimated_annual_roi": "€ 500,000"
  }
}
EOF
dku govern artifact create --from-json @new-usecase.json
```

### Emit a compliance audit entry

```bash
dku govern log custom-audit "deployment.gate" \
  --params '{"artifact":"ar.3375","gate":"value_tracking","outcome":"passed"}'
# Appears in audit/audit.log on the Govern node
```

### Upload an attachment for an artifact field

```bash
UF=$(dku govern uploaded-file upload ./risk-assessment.pdf \
       -o json | jq -r '.id')
# Patch the artifact field to reference $UF via `govern artifact create` /
# a future `govern artifact edit --field` once it exists.
```

---

## Gotchas

| Symptom | Cause | Fix |
|---|---|---|
| `Command not available on GOVERN nodes` (exit 4) | Profile is `GOVERN`, command is project-scoped | Use `dku govern <noun>` or `dku auth switch <design-profile>` |
| `Not Found: /dip/publicapi/projects/` | Legacy `[?]` profile that was set up pre node-type tracking | `dku auth login --profile X` to refresh — now persists node_type |
| `govern artifact get ar.X` returns `NotFoundException` | Artifact ID typo or deleted | `dku govern artifact list --name-contains …` to find the right `ar.*` |
| Empty `govern signoff list` | Blueprint version has no signoff configuration, or signoffs not yet instantiated on this artifact | Check the blueprint version: `dku govern blueprint versions BP` |
| `update-status` rejects my status | Case-sensitive match against the whitelist above | Status values are uppercase (`APPROVED`, not `Approved`) |
| Raw `[object Object]`-like output in `artifact list status` column | Old SDK shape leaked through | Already handled — look at `workflow_step` and `archived` columns instead |
| `--errors json` after the subcommand fails with "No such option" | Global flag, not per-command | Put it BEFORE the noun: `dku --errors json govern artifact get X` |
| `delegate_*` needs weird `users_container` dict | SDK-level quirk | Use the CLI's `--delegate-user LOGIN` (future) — not exposed in MVP |

---

## Safety tiers on Govern commands

| Command | Tier | Why |
|---|---|---|
| `govern artifact delete` | 2 DELETE | Single record, recoverable from backup |
| `govern uploaded-file delete` | 2 DELETE | Single file |
| (future) `govern blueprint-version save --danger-zone` | 3 CASCADE | Breaks every artifact using that blueprint version |
| (future) `govern blueprint delete` | 4 ADMIN | Instance-wide schema mutation |
| (future) `govern role delete` | 3 CASCADE | Cross-blueprint permission impact |

Not yet implemented: `blueprint create/delete`, `blueprint-version create/save`, `role create/delete`, `role-assignment create/delete`, `custom-page create/edit/delete`, `time-series push/get/delete`, `signoff delegate-*`. These are the planned P1 follow-ups.
