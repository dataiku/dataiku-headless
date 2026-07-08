# Govern Playbook

A separate node type: a governance schema (blueprints + versions) describing governed
records (**artifacts**) that move through **workflow steps** gated by **sign-offs**
(reviewer feedback + final approval). **No projects/datasets/recipes** — on a `[GOVERN]`
profile every non-govern command exits **4**; use `dku govern …`. Needs an admin API key.
Get exact flags from `dku govern <group> <cmd> --help`. Payload shapes, field-type rules,
hooks, audit, custom-html embedding: `references/govern.md`.

## Canonical commands

```bash
# discover → inspect schema → create record → advance sign-off
dku govern blueprint list
dku govern blueprint fields BP             # ALWAYS inspect fields before creating an artifact
dku govern artifact list -b BP --all       # --all: past the 50/page default; -n NAME to search
dku --format json govern artifact list -b BP -f sensitive_data=Yes --all | jq length   # count by a field value

# create / edit an artifact (list fields need a JSON array even for one value)
dku govern artifact create -b BP -n "Churn model" -f cost_rating=High -f countries='["France"]'
dku govern artifact set-field AR cost_rating "Medium low"
dku --format json govern artifact get AR

# advance a sign-off  (update-status STATUS is POSITIONAL + uppercase; add-* take --status)
dku govern signoff list AR
dku govern signoff update-status AR STEP WAITING_FOR_FEEDBACK
dku govern signoff add-feedback  AR STEP -g GROUP_ID --status APPROVED -c "looks good"
dku govern signoff update-status AR STEP WAITING_FOR_APPROVAL
dku govern signoff add-approval  AR STEP --status APPROVED -c "ship it"
```

## Run a governed workflow (the common case)

States (uppercase, case-sensitive): `NOT_STARTED → WAITING_FOR_FEEDBACK →
WAITING_FOR_APPROVAL → APPROVED|REJECTED|ABANDONED`; reset only via `ABANDONED`. Feedback:
`APPROVED|MINOR_ISSUE|MAJOR_ISSUE`. A sign-off runs only when the step is `ONGOING`, a
signoff **config** exists on the version, the signoff is created on the artifact, and the
caller is in the feedback/approval group (else `delegate-feedback` / `delegate-approval`).

## Author a blueprint (fork → edit → activate)

```bash
# fork an ACTIVE system version (it carries fields/steps Govern needs); new version = DRAFT
dku govern blueprint create-version BP v1 --from bv.system.default
dku --format json govern blueprint get-version BP bv.v1 > bv.json
#   edit bv.json: fieldDefinitions{} (dict by id), workflowDefinition, uiDefinition.views, logicalHookList[]
dku govern blueprint set-version-definition BP bv.v1 --definition @bv.json
dku govern blueprint describe-version BP bv.v1            # lint: empty views, unmapped steps, unreferenced fields
dku govern blueprint create-signoff-config BP bv.v1 STEP --definition @signoff.json
dku govern blueprint set-version-status BP bv.v1 ACTIVE   # DRAFT is invisible — do not skip

# brand-new blueprint entity (name/icon/color only), then fork its first version
dku govern blueprint create my_bp --definition '{"name":"My BP","icon":"science","color":"#da7f15"}'
```

`set-version-definition --force` (dangerZoneAccepted) **discards removed-field data in
every artifact** — never without explicit user go-ahead; prefer a new version + migrate.
Cross-instance: `export-version` / `import-version` (imports land DRAFT; **only role-based
reviewers survive** the round-trip — put reviewers in a Govern role).

## Embed external content (custom-html page)

```bash
dku govern custom-page create cp.x --definition @page.json   # {"type":"custom-html","htmlContent":"<iframe …>"}
dku --format json govern custom-page get cp.x                      # round-trip an existing one to see the full shape
```

Embed a DSS webapp by its **bare** view URL `http://<dss>/webapps/<PROJ>/<id>/` (the URL the
user's **browser** hits, not Govern's internal one), NOT the Angular-shell `…/projects/…` URL.

## Attachments & metrics

```bash
UF=$(dku --format json govern file upload ./doc.pdf | jq -r '.id')   # uf.<n> → into an UPLOADED_FILE field: '["uf.1"]'
dku govern time-series push-values TS --datapoints '[{"timestamp":1700000000000,"value":42}]'   # epoch MILLIS
```

## Gotchas

- **Inspect fields first** (`blueprint fields BP`) — a field id that doesn't match the
  version is silently ignored on create (the value vanishes, no error).
- **List fields need a JSON array even for one value:** `-f countries='["France"]'`.
- **`update-status` STATUS is positional + UPPERCASE;** `add-feedback`/`add-approval` use
  `--status`. Wrong case → rejected.
- **REFERENCE values are artifact IDs** (`ar.<n>`), not logins — `-f owner=ar.2`. No USER/GROUP
  fieldType; reference `bp.system.user`/`bp.system.group` artifacts.
- **Blank artifact page** = empty `uiDefinition.views`; declare a view and run
  `describe-version` before activating.
- **New version invisible to artifacts** → it's still DRAFT (`set-version-status … ACTIVE`).
- **`add-approval` "is not an approver"** = the gate's role/group has no members bound — bind it first.
- **Hooks** block with `raise` / `handler.status="ERROR"` (there is **no** `handler.fail()`);
  `print()` is dropped (use `logging`). **Audit is OFF by default** — an empty `audit.log`
  isn't proof hooks aren't firing. Both in `references/govern.md`.
- Global flags go **before** the noun: `dku --format json govern artifact get AR`.

## Done when

- `dku govern signoff list AR` shows the target step at `APPROVED` (or the terminal state you drove it to).
- `dku --format json govern artifact get AR` reflects the field values you set (`set-field` / `create -f`).
- A new/edited blueprint version is `ACTIVE`: `dku govern blueprint get-version BP bv.vX` shows `status: ACTIVE`, not `DRAFT`.
- A custom-html page round-trips: `dku --format json govern custom-page get cp.x` returns the `htmlContent` you set.
