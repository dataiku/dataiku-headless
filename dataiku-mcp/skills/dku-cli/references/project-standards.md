# Reference: Project Standards Payloads

Cold detail for the Project Standards playbook. Exact flags live in
`dku project-standards <command> --help`.

## Check spec

`dku --format json project-standards list-check-specs` returns normalized rows
containing the plugin-provided schema:

```json
{
  "element_type": "project_standards_check_spec_plugin_component",
  "label": "Project must satisfy policy",
  "description": "Checks one organization rule",
  "owner_plugin_id": "plugin",
  "parameters": [
    {
      "name": "threshold",
      "type": "INT",
      "label": "Maximum allowed value",
      "defaultValue": 20,
      "mandatory": true
    }
  ]
}
```

`element_type` is the import identifier. `parameters` is the source of truth
for `--params`; select parameters may contain case-sensitive `selectChoices`.

## Check instance

```json
{
  "id": "Projectmustsatisfypolicy",
  "name": "Project must satisfy policy",
  "description": "Organization policy",
  "checkElementType": "project_standards_check_spec_plugin_component",
  "checkParams": {"threshold": 20},
  "tags": ["QUALITY"]
}
```

DSS assigns `id`. Multiple instances can share one `checkElementType`; duplicate
imports commonly receive suffixes. Scopes reference check IDs, never element
types.

## Scope

```json
{
  "name": "Production",
  "description": "Quality checks for production projects",
  "checks": ["Projectmustsatisfypolicy"],
  "selectionMethod": "BY_PROJECT",
  "selectedProjects": ["PROJ"],
  "selectedFolders": [],
  "selectedTags": []
}
```

Exactly one selector array is active:

| Method | Active field | Values |
|---|---|---|
| `BY_PROJECT` | `selectedProjects` | Project keys |
| `BY_FOLDER` | `selectedFolders` | Project-folder IDs |
| `BY_TAG` | `selectedTags` | Project tag strings |
| `ALL` | none | Immutable Default selection |

The CLI clears inactive arrays when the method changes. Scope names cannot be
renamed. Default stays last and cannot be reordered or deleted; only its
`checks` array is editable. Scope order is first-match priority.

## Run rows

Completed runs render one row per entry in `bundleChecksRunInfo`:

```json
{
  "check_id": "Projectmustsatisfypolicy",
  "name": "Project must satisfy policy",
  "status": "RUN_SUCCESS",
  "severity": 3,
  "severity_category": "MEDIUM",
  "message": "Policy threshold exceeded"
}
```

Status is execution health, not compliance:

- `RUN_SUCCESS`: the check executed; read severity.
- `RUN_ERROR`: execution failed and the CLI exits 1.
- `NOT_APPLICABLE`: the check does not apply; treat it as non-executed context,
  not a passing policy result.

Severity is 0 for no issue, then `LOWEST`, `LOW`, `MEDIUM`, `HIGH`, and
`CRITICAL` for values 1 through 5. `--fail-at` compares inclusively. Without a
threshold, findings remain report data and do not change the exit code;
execution errors still do.

## Saved versus explicit reports

- A run without explicit check IDs resolves the assigned scope and replaces
  the saved report after completion.
- A run with explicit IDs is diagnostic and does not replace the saved report.
- `last-report` is absent until a scoped run completes at least once.
- `--no-wait` cannot enforce `--fail-at` because no report is available yet.

## Deletion and concurrency integrity

DSS allows deleting a check while scopes still reference its ID. The CLI
refuses that state; `delete-check --force` holds the shared policy lock,
serializes each affected scope read-modify-write, re-scans every scope, then
deletes and verifies the check only when no references remain.

Scope mutations and check deletion share one policy lock on the local host;
check and scope document saves also use per-object locks. Updates render a
fresh server read after saving so DSS normalization is visible. Every mutation
uses a non-bypassable tier-4 guard because it changes instance-wide policy.
