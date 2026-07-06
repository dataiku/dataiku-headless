# `dku` CLI bugs found in `analytics_mesh` run 20260703_114258_72838

Source: `traces/analytics_mesh_claude_dku_skills.json` / `.log` (Claude, `dku`
CLI + skills surface). Scenario: `benchmark/scenarios/end_to_end/analytics_mesh`.
Run scored 0.68/1.0 and still hit `error_max_turns` — an estimated 13 of the
~120 tool calls in the transcript were spent purely diagnosing and working
around the two bugs below, which is plausibly why DQ rules on the producer
output and the full failed-rows population never got finished in time.

Ranked by turns burned / likely blast radius on other users.

## 1. `dataset rename` doesn't move storage — new dataset that reuses the vacated name collides with it

```
dku dataset rename supplier_spend_failed_rows --name po_failed_raw -P SRC   # succeeds
dku recipe create-prepare derive_po_failure_reason -i po_failed_raw \
  --output-ds supplier_spend_failed_rows -P SRC                              # reuses the vacated name
dku job run --target supplier_spend_failed_rows --wait                       # FAILS
dku job run --target po_failed_raw --wait                                    # ALSO now fails
```

`dataset rename` updates the object's name but leaves the managed storage
path untouched — `get-definition` after the rename still shows
`path: "${projectKey}/supplier_spend_failed_rows"` even though the dataset is
now called `po_failed_raw`. When a *new* dataset was later auto-created under
the vacated name `supplier_spend_failed_rows`, DSS assigned it the same
default path, so the two datasets collided on disk. Both builds then failed
with `DataStoreIOException: Root path of the dataset ... does not exist` —
including `po_failed_raw`, which had nothing to do with the new recipe and
had previously built fine.

The fix required manually pulling `get-definition`, hand-patching
`params.path`, and pushing it back via `set-definition` — which itself threw
a stray warning (`Keys NOT persisted by DSS (unknown or misplaced): smartName`),
meaning `get-definition`'s own output isn't safely round-trippable into
`set-definition` without editing it first.

**Why it's a CLI bug:** nothing in `dataset rename --help` warns that storage
is untouched, and nothing in dataset auto-creation warns that a default path
can collide with an existing (renamed) dataset's still-live path. The error
message points at the symptom on a dataset that was never touched by the
triggering command.

**Turns burned:** ~6 tool calls.

**Suggested fix:** either (a) `dataset rename` also relocates managed storage
to match the new name, or (b) default-path assignment for new managed
datasets checks for collisions against *any* existing dataset's path, not
just same-name ones, and refuses/uniquifies instead of silently colliding.
Separately, drop `smartName` from `get-definition` output or accept it back
in `set-definition` so the two are round-trippable.

## 2. `dataset copy --to-project` requires the destination to already exist — contradicts its own help text

```
dku dataset copy suppliers --to-project PROJ_ANALYTIC -P PROJ_ANALYTIC_SRC
→ ◆ Not found: dataset does not exist: PROJ_ANALYTIC.suppliers
◆ Check the name and project (-P), then list what exists with the
  matching `dku <noun> list -P <project>`
```

`dataset copy --help` describes it as "Copy a dataset to another project"
with `--name` documented as "Name in target project (default: same name)" —
this reads as create-or-overwrite semantics. In practice it 404s unless a
dataset of that name already exists in the destination project with a
matching schema and connection. The only way to make it work is to manually
`dataset create --type Filesystem`, `dataset set-schema` (matching the
source schema by hand), and only then run `dataset copy`.

**Why it's a CLI bug:** the error message ("dataset does not exist... check
the name... list what exists") actively misdirects toward a spelling/typo
problem, when the real issue is that `copy` is "copy *data into* an existing,
identically-shaped dataset," not "copy a dataset (definition + data) to
another project." The latter is exactly the cross-project data-product
publishing pattern this CLI needs to support well — this is a data-mesh /
multi-project sharing task, one of the more common enterprise DSS patterns.

**Turns burned:** ~7 tool calls (re-reading help, probing with `dataset
list`, testing a same-project copy, before landing on the manual
create-first workaround).

**Suggested fix:** either make `dataset copy` auto-create the destination
dataset (schema + connection) when it doesn't exist yet — matching the
documented behavior — or keep the manual-precreate requirement but rewrite
the help text and error message to say so explicitly: "target dataset does
not exist — create it first with `dataset create` + `set-schema` matching
the source schema."

## 3. `recipe create-extract-failed-rows --help` cites a subcommand that doesn't exist

`recipe create-extract-failed-rows --help` says: *"The input dataset MUST
have checks defined (`dku dq add-check ...`)."* But `dq --help` lists only
`compute`, `create`, `delete`, `list`, `project-status`, `results`, `status`
— there is no `dq add-check`; the real command is `dq create`.

**Why it's a CLI bug:** the CLI's own help text quotes a command that
doesn't exist. In this run the agent cross-checked `dq --help` anyway and
lost no turns, but a less careful run (or a less thorough skill doc) would
burn a retry on a command guaranteed to fail.

**Suggested fix:** add a doc test that every backticked `dku ...` snippet
inside a `--help` string resolves to a real, currently-registered
subcommand — this class of drift (help text not updated when a command is
renamed) is cheap to catch mechanically.

## 4. Inconsistent default output format on `get`-style commands breaks naive JSON piping

```
dku insight get rFOx2VJ -P DST > file.json        # prints "Insight: rFOx2VJ" header, not JSON
dku recipe get-definition curate_supplier_spend -P SRC | python3 -c "json.load(...)"
→ json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

Without the global `--format json` flag, several `get`/`get-definition`
commands print a human-readable header line instead of the raw object, so
piping into `json.load` throws a raw Python traceback. The agent had to
rediscover `--format json` twice, in two unrelated subsystems (insights,
recipes), each costing a failed call plus a stdlib traceback before the fix.

**Why it's a CLI bug/gap:** this is a cross-cutting default-format
inconsistency, not one bad command — it recurred in unrelated noun/verb
pairs, suggesting there's no shared convention or test for "is this
`get`-style command's default output machine-parseable."

**Suggested fix:** default single-object `get`/`get-definition` commands to
JSON output (reserve pretty tables/headers for `list`), or detect
non-JSON-consumption downstream and print a one-line hint (`Add --format
json for machine-readable output`) instead of surfacing a raw traceback to
the caller.

## 5. Minor: `scenario set-active` doesn't accept `--active`

```
dku scenario set-active publish_supplier_mesh -P SRC --active
→ Error: No such option: --active
```

The bare `scenario set-active ID` already means "enable" (default
`--enable`/`--disable` pair) — no flag is needed for the common case, which
is easy to miss coming from other DSS toggles that use an explicit
`--<verb>` flag. Low severity: one retry, resolved via `--help`. Worth a
look only because it's a small consistency gap in the CLI's own flag
vocabulary.
