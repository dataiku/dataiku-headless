# Project Standards

Project Standards is the DSS-native quality gate for whole projects. Checks and
scopes are instance-wide policy; executions and saved reports are project-scoped.
Use `dku project-standards --help` for the command index and command-level help
for exact flags. Open `references/project-standards.md` only for payload and
result semantics.

## Golden workflow

Discover specs → configure checks → create an ordered scope → resolve it against
a real project → run → inspect the saved report → optionally gate CI.

### 1. Inspect before changing policy

```bash
dku project-standards list-check-specs
dku --format json project-standards list-check-specs
dku project-standards list-checks
dku project-standards list-scopes
dku project-standards get-default-scope
dku project-standards project-scope -P PROJ
```

The JSON spec output contains plugin-supplied parameter names, types, defaults,
and select choices. Never infer check params from the label.

### 2. Import and configure a check

```bash
dku project-standards create-checks --spec ELEMENT_TYPE
dku project-standards get-check CHECK_ID
dku project-standards update-check CHECK_ID --params @params.json
```

Multiple imports of one spec are valid separate configurations; capture the ID
DSS returns. Every check-library mutation is tier-4. The initial unconfirmed
attempt exits 77—ask the user the emitted question, then copy the sentinel's
exact rerun command. Never invent `--confirm-name`.

### 3. Create the narrowest scope

```bash
# Exact project keys
dku project-standards create-scope --name quality-gate \
  --selection-method BY_PROJECT --item PROJ --check CHECK_ID

# Projects under a project folder
dku project-standards create-scope --name quality-gate \
  --selection-method BY_FOLDER --item FOLDER_ID --check CHECK_ID

# Projects carrying a tag
dku project-standards create-scope --name quality-gate \
  --selection-method BY_TAG --item production --check CHECK_ID
```

Scopes are first-match priority. Reorder deliberately and resolve a real
representative project instead of assuming the selector matched:

```bash
dku project-standards reorder-scope quality-gate 0
dku project-standards project-scope -P PROJ
```

`update-scope --check` replaces the complete check list; `--item` replaces the
complete selector list. Read the scope first when preserving values. A selector
type change requires new items or an explicit clear so project keys cannot
silently become tags or folder IDs.

### 4. Run and verify

```bash
# Assigned scope: wait, print results, and update the saved report
dku project-standards run -P PROJ
dku project-standards last-report -P PROJ

# Ad hoc diagnosis: named checks do not replace the saved report
dku project-standards run --check CHECK_A --check CHECK_B -P PROJ

# CI gate: print the report, then exit 1 at or above the threshold
dku project-standards run --fail-at HIGH -P PROJ
```

Process success is not standards success. `RUN_SUCCESS` means the check
executed; severity greater than zero means it found a policy violation. Inspect
every severity and message. Execution errors always fail the command.

### 5. Delete without corrupting scopes

```bash
dku project-standards delete-check CHECK_ID
dku project-standards delete-scope SCOPE_NAME
```

The DSS API permits deleting a referenced check and leaves a dangling ID. `dku`
refuses this. Use `--force` only when the intent is to remove the check from
every referencing scope first; tier-4 confirmation still applies. Default
cannot be deleted or reordered, but its check list can be updated.

## Done when

1. `get-check` shows the intended params and tags.
2. `get-scope` contains only existing check IDs and the intended selector.
3. `project-scope` resolves to the expected highest-priority scope for a real
   project in every selector branch used.
4. `run` prints one row per check and no execution error.
5. `last-report` reflects the completed scoped run.
6. Automation uses an explicit `--fail-at` policy instead of treating exit 0
   as proof that every severity is zero.

## Gotchas

- Project Standards requires its DSS license capability.
- Check specs come from installed plugin components; importing one does not
  install the plugin.
- Project keys, project-folder IDs, and tags are different namespaces.
- Explicit-check runs are diagnostic and never update `last-report`.
- A scoped run updates `last-report` only after completion.
- A broad scope above a narrow scope shadows it.
