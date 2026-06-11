# Playbook: Project Ops & Automation

Project lifecycle, variables, scenarios, jobs, flow builds, bundles, cross-project sharing.
Get exact flags from `dku <group> <cmd> --help`. Open a reference only for JSON payload shapes.

## Canonical commands

```bash
# Project lifecycle
dku project create KEY --name "Name" --if-not-exists
dku project inspect -P KEY
dku --format json project get-variables -P KEY
dku project set-variables -P KEY --set k=v --set k2=v2

# Scenario
dku scenario create NAME -P KEY
dku --format json scenario get-definition NAME -P KEY
dku scenario set-definition NAME -P KEY -d @scen.json
dku scenario run NAME -P KEY --wait
dku scenario add-trigger-dataset NAME --dataset DS -P KEY
dku scenario add-reporter NAME --condition failure --recipient email@x -P KEY
dku scenario list-triggers NAME -P KEY
dku scenario last-run NAME -P KEY

# Build + verify
dku job run --target OUT --type RECURSIVE_BUILD --auto-update-schema --wait -P KEY
dku job log JOB_ID -P KEY
dku dataset info OUT --recompute -P KEY
dku dataset head OUT -P KEY -n 5

# Bundle
dku bundle export -P KEY --bundle-id v1
dku bundle import -P TARGET --file ./v1.zip
dku bundle activate -P TARGET --bundle-id v1
```

## Project lifecycle

```bash
dku project create KEY --name "Name" --if-not-exists   # idempotent
dku project inspect -P KEY                              # one-shot summary: datasets, recipes, scenarios, sources, jobs, vars
dku project set-metadata -P KEY --name ... --description ...
dku project timeline -P KEY                             # history: who/when/what changed
dku project delete KEY -y                               # see gotcha below
```

- **Always `inspect` before substantive work**; skip for narrow reads.
- `delete` does NOT drop backing storage of managed datasets by default — physical SQL tables / folder contents stay orphaned. Add `--drop-data` to clear them. Without it, the command prints a reminder.

### Variables

```bash
dku --format json project get-variables -P KEY                   # read
dku project set-variables -P KEY --set k=v --set k2=v2  # patch individual standard vars
dku project set-variables -P KEY --definition @vars.json # replace ALL (standard + local)
```

Variables drive scenario branching and app forms. Reference them in SQL/recipes as `${projectVariables.k}`, in scenarios/reporters as `${var}`.

## Scenarios

A scenario = **triggers** (when) + **steps** (what) + **reporters** (who is told). Two kinds: step-based (visual) and custom Python.

### Build a step-based scenario

```bash
dku scenario create daily_build -P KEY
# steps go through set-definition (FULL replace — include params.steps)
dku --format json scenario get-definition daily_build -P KEY   # header-only: NO steps, NO triggers
dku scenario set-definition daily_build -P KEY -d @scen.json
dku scenario run daily_build -P KEY --wait
```

- **`set-definition` is a FULL replace** of `params.steps`, `params.reporters`, and header. Supply a complete definition, never a partial patch. For header-only edits use `set-metadata` instead.
- **`get-definition` returns header only** — no `params.steps`, no `triggers`. Round-trip the complete step payload you are editing; do not reconstruct from memory. For triggers use `list-triggers`.
- Common step types in `params.steps`: `build_flowitem` (`params.builds` = list of `{type:"DATASET"|"MANAGED_FOLDER", itemId, partitionsSpec}` + `params.buildMode`), `custom_python` (`params.script`), `exec_sql` (`params.sql`, `params.connection`). For unfamiliar shapes, build one in the DSS UI and round-trip it.
- **Gate critical builds on data quality:** add a *Compute Metrics* step then a *Run Checks* step on the output dataset — checks fail the scenario (`ERROR`) or warn (`WARNING`) so bad data stops the pipeline loudly instead of propagating. These step shapes are opaque JSON; build the gate once in the UI and round-trip it.
- Build modes: `RECURSIVE` (full refresh), `NON_RECURSIVE`, smart reconstruction (skip up-to-date). Prefer smart/non-recursive; reserve recursive for full refresh.

### Triggers

```bash
dku scenario list-triggers SCEN -P KEY                  # shows index + type + active + params
dku scenario add-trigger-dataset SCEN --dataset DS -P KEY   # shortcut for dataset-change
dku scenario add-trigger SCEN --trigger @trigger.json -P KEY # raw JSON (inline/@file/-)
dku scenario remove-trigger SCEN --index N -P KEY       # index from list-triggers
```

Multiple triggers OR together — any match fires. Raw trigger JSON needs `type`, `active`, `params`:

- **Time (`temporal`)**: `params.frequency` ∈ `Minutely|Hourly|Daily|Weekly|Monthly`, plus `hour`/`minute`/`timezone`. `Weekly` adds `daysOfWeek`; `Monthly` adds `monthlyRunOn`.
- **Dataset change (`ds_modified`)**: `delay` (check interval, seconds) and `graceDelaySettings` are **root-level, NOT inside params**; `params.watches` = `[{type:"DATASET", itemId:"DS"}]`. Gotcha: putting `delay` under `params` silently never fires.
- **SQL (`sql_query`)**: `params.connection` + `params.query`; fires on non-empty result. For incremental triggers, filter on the built-in `${scenarioTriggerPreviousFireDate}` (e.g. `WHERE created_at > '${scenarioTriggerPreviousFireDate}'`) so each fire only sees new rows.

### Email / reporters

```bash
dku scenario add-reporter SCEN --condition failure --recipient ops@x --channel smtp -P KEY
dku scenario add-reporter SCEN --condition success --recipient team@x --channel smtp -P KEY
dku scenario list-reporters SCEN -P KEY                 # verify
```

- `--condition`: `failure` → `outcome != 'SUCCESS'`, `success` → `== 'SUCCESS'`, `always`. For "alert ops on failure, notify team on success" add two reporters.
- Reporter saves even if `--channel` doesn't match a configured SMTP channel (channels validate at send time). Verify with `list-reporters`.
- Reporter body vars: `${scenarioName}`, `${scenarioOutcome}`, `${scenarioError}`, `${scenarioTriggerName}`, `${projectKey}`.

### Verify scenarios

```bash
dku scenario run SCEN -P KEY --wait
dku scenario last-run SCEN -P KEY        # outcome of last finished run
dku scenario runs SCEN -P KEY --limit 5  # recent run history
dku scenario run-log SCEN -P KEY         # debug a failure
```

## Jobs & flow builds

The canonical build: `dku job run --type RECURSIVE_BUILD --auto-update-schema --wait`.

```bash
dku job run --target OUT --type RECURSIVE_BUILD --auto-update-schema --wait -P KEY
dku job run --target A --target B -P KEY     # multiple outputs in one job
dku job last -P KEY                          # most recent job id on stdout (composable)
dku job log $(dku job last -P KEY) -P KEY    # tail the log
dku job status JOB_ID -P KEY
dku job abort JOB_ID -P KEY
```

- `--target` auto-detects type (dataset / managed folder / saved model by name or ID) — folder/model targets won't error as "dataset does not exist".
- `--type` defaults to `NON_RECURSIVE_FORCED_BUILD`; use `RECURSIVE_BUILD` to build upstream deps.
- `--auto-update-schema` propagates output schemas before each recipe run — eliminates manual `flow propagate`.
- `--wait` blocks; add `--timeout` for bounded waits.
- `log --errors-only` filters to error-like lines + context; `--tail N` keeps last N lines.

### Flow orchestration

```bash
dku flow visualize -P KEY                    # ASCII DAG
dku flow sources -P KEY                       # all source datasets (or upstream sources of one DATASET arg)
dku flow check -P KEY                          # schema + data consistency across the flow
dku flow propagate DATASET -P KEY              # manual schema propagation from a starting dataset
dku flow create-zone "Staging" --color "#FF5500" -P KEY
dku flow move DS1 DS2 --type DATASET --zone ZONE -P KEY
```

- Prefer `job run --auto-update-schema` over standalone `flow propagate`. Use `propagate --stop-at RECIPE` / `--mark-ok RECIPE` / `--no-auto-rebuild` to scope it.

### Verify builds with real data

Exit 0 is not proof. After a build:

```bash
dku dataset info OUT --recompute -P KEY      # fresh row/size/file counts (cache is stale otherwise)
dku dataset head OUT -P KEY                   # eyeball values
dku dataset schema OUT -P KEY                 # confirm columns/types
```

Empty arrays are data, not success — check row counts and sample values.

## Bundles (Design → Automation/Prod promotion)

```bash
dku bundle export -P KEY --bundle-id v1       # snapshot project as a bundle
dku bundle download -P KEY --bundle-id v1 --dest ./v1.zip
dku bundle import -P TARGET --file ./v1.zip   # on the automation node
dku bundle activate -P TARGET --bundle-id v1
dku bundle list -P KEY
```

Bundles are the supported promotion path. Activate makes the imported bundle the live version. For deployer-driven promotion see the extensions-admin playbook.

## Cross-project sharing

```bash
dku dataset copy DS --to-project OTHER --name newname -P KEY   # physical copy into another project
dku project duplicate KEY NEWKEY --name "Copy"                 # clone an entire project
```

- `dataset copy` lands a copy; `--name` overrides the target name (default same). For sharing across flow **zones** within a project use `dataset share --zone` (visibility only) vs `flow move` (relocate).
- Exposing a dataset to another project for reads (not a copy) is configured in project settings / the DSS UI; verify the consuming project can resolve it before building downstream.
