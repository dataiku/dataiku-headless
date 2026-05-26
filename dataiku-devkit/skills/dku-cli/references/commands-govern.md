# dku-cli Govern Command Syntax

Exact command syntax for `dku govern`. For payload shapes and platform behavior, read `../dataiku/references/govern.md` and the Govern blueprint references.

## govern

Nested `dku govern <group> <verb>`. Requires Govern integration + admin API key. Deep patterns, JSON payloads, signoff state machine, gotchas: `skills/dataiku/references/govern.md`. Blueprint authoring (versions, fields, hooks, views, signoff config): `skills/dataiku/references/govern-blueprint-designer.md`.

```bash
# Instance
dku govern whoami [-o FORMAT]
dku govern info [-o FORMAT]

# Artifacts — run `blueprint fields BP` first to discover schema
dku govern artifact list [-b BP] [-n NAME] [--archived|--no-archived] [--page-size N] [--all] [-o FORMAT]
dku govern artifact get ARTIFACT_ID [-o FORMAT]
dku govern artifact create (-b BP -n NAME [-f key=value ...] | --definition JSON) [-o FORMAT]
dku govern artifact set-field ARTIFACT_ID FIELD_ID VALUE
dku govern artifact set-definition ARTIFACT_ID --definition JSON
dku govern artifact delete ARTIFACT_ID --confirm

# Blueprints (read-side only — authoring verbs live in govern-blueprint-designer.md)
dku govern blueprint list [-o FORMAT]
dku govern blueprint get BP_ID [-o FORMAT]
dku govern blueprint list-versions BP_ID [-o FORMAT]
dku govern blueprint get-version BP_ID VER_ID [-o FORMAT]        # alias: get-version-definition
dku govern blueprint describe-version BP_ID VER_ID                # summary + structural lint
dku govern blueprint fields BP_ID [--version VER_ID] [-o FORMAT]
dku govern blueprint create IDENTIFIER --definition JSON [-o FORMAT]
dku govern blueprint set-definition BP_ID --definition JSON
dku govern blueprint delete BP_ID --confirm

# Sign-offs
dku govern signoff create          ARTIFACT_ID STEP_ID
dku govern signoff list            ARTIFACT_ID                                            [-o FORMAT]
dku govern signoff get             ARTIFACT_ID STEP_ID                                    [-o FORMAT]
dku govern signoff update-status   ARTIFACT_ID STEP_ID STATUS
dku govern signoff add-feedback    ARTIFACT_ID STEP_ID -g GROUP_ID -s STATUS [-c COMMENT]
dku govern signoff add-approval    ARTIFACT_ID STEP_ID            -s STATUS [-c COMMENT]
dku govern signoff delegate-feedback  ARTIFACT_ID STEP_ID -g GROUP_ID --users-container JSON
dku govern signoff delegate-approval  ARTIFACT_ID STEP_ID            --users-container JSON
dku govern signoff list-feedbacks  ARTIFACT_ID STEP_ID                                    [-o FORMAT]
dku govern signoff get-feedback    ARTIFACT_ID STEP_ID FEEDBACK_ID                        [-o FORMAT]
dku govern signoff get-approval    ARTIFACT_ID STEP_ID                                    [-o FORMAT]

# Roles / Custom pages (same CRUD shape — ID prefixes `ro.` / `cp.`)
dku govern role        {list | get ID | create IDENTIFIER --definition JSON | set-definition ID --definition JSON | delete ID --confirm}
dku govern custom-page {list | get ID | create IDENTIFIER --definition JSON | set-definition ID --definition JSON | delete ID --confirm}

# Users / Groups (admin)
dku govern user list [-o FORMAT]
dku govern user get LOGIN [-o FORMAT]
dku govern user create LOGIN --password PASS [--display-name NAME] [--email EMAIL] [--group G ...] [--profile P] [--source-type LOCAL|LDAP]
dku govern user {create-bulk | edit-bulk | delete-bulk} --definition JSON [--confirm] [-o FORMAT]
dku govern user get-own [-o FORMAT]                                   # user-session auth only
dku govern user list-activity [--enabled-only] [-o FORMAT]
dku govern group {list | get GROUP_NAME | create GROUP_NAME [--description D] [--source-type LOCAL|LDAP] | delete GROUP_NAME --confirm}

# Time series (timestamps = epoch ms; push-values upserts by default, `--no-upsert` skips existing)
dku govern time-series create [--datapoints JSON] [-o FORMAT]
dku govern time-series get TS_ID [--min EPOCH_MS] [--max EPOCH_MS] [-o FORMAT]
dku govern time-series push-values TS_ID --datapoints JSON [--no-upsert]
dku govern time-series delete TS_ID [--min EPOCH_MS] [--max EPOCH_MS] --confirm

# Files — returned `uf.<id>` goes into UPLOADED_FILE fields as array: '["uf.1"]'
dku govern file upload PATH [-o FORMAT]
dku govern file get FILE_ID [-o FORMAT]
dku govern file download FILE_ID [--dest PATH]
```

- `artifact create`: ergonomic (`-b`/`-n`/`-f`) or raw (`--definition`). `set-field` updates one field without round-tripping the full definition
- `blueprint fields` auto-resolves the ACTIVE version; prints field IDs, types, required flags, categories
- `blueprint describe-version` pretty-prints fields/workflow/signoffs/views + flags silent-failure patterns (empty `uiDefinition.views`, missing `artifactPageViewId`, fields not in any view, signoffs on non-existent steps). Prefer over `get-version | jq` when authoring
- Sign-off state machine: `NOT_STARTED → WAITING_FOR_FEEDBACK → WAITING_FOR_APPROVAL → APPROVED|REJECTED|ABANDONED`. Reset requires passing through `ABANDONED`. Feedback statuses: `APPROVED|MINOR_ISSUE|MAJOR_ISSUE`; approval: `APPROVED|REJECTED|ABANDONED`
- `--users-container` JSON: `'{"type": "user", "login": "alice"}'` — `type` is **lowercase** (`user`/`group`/`role`/`global-api-key`)
- All `--definition` / `--datapoints` flags accept literal string, `@file.json`, or `-` (stdin)
- All `delete*` commands require `--confirm` / `-y`. `blueprint delete` needs every version + artifact gone first
