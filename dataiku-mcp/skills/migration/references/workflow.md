# Migration workflow

The phase-by-phase migration playbook, in detail. Source-agnostic. Source-specific Phase 1 parsing lives in each `<source>/overview.md`.

---

## Phase 0 — Preflight

```bash
dku whoami                          # must succeed — if not: dku auth login
dku connection list                 # find a writable+managed connection
dku project create PROJ --name "Project"
```

Store the connection name and project key — every subsequent command uses them.

---

## Phase 1 — Extract & inventory

Produce a complete inventory of every source step / tool, its inputs, outputs, and what it does. **No Dataiku planning yet** — just understand the source. For complex sources (>20 tools) surface the inventory for a sanity check before drafting the plan; for small sources roll straight into Phase 2. The single consequential confirmation gate is between Phase 2 (plan) and Phase 3 (build) — unattended runs skip it (see SKILL.md: print the plan, proceed).

Generic inventory template:

```
| # | Source ID | Source Type | What It Does | Inputs | Outputs | Migratable? |
|---|-----------|-------------|--------------|--------|---------|-------------|
| 1 | …         | …           | …            | …      | …       | Yes → …     |
```

For source-specific column meanings (`Source ID` vs `Tool ID` vs `SAS step name`), parsing logic, and inventory examples, read `<source>/overview.md`.

### Parity reference — load it in Phase 1, not Phase 4

If the source ships its own expected outputs — cached values of a workbook's output sheets, Alteryx `BrowseV2` caches or bundled ground-truth CSVs, SAS output tables / log row counts — inventory them now and load them as a **parity-reference dataset** before building anything. It arbitrates every interpretation ambiguity in Phase 3: diff a candidate reading against the expected values *before* building it (a wrong reading of one ambiguous construct can cost a whole zone built-then-deleted). And it upgrades Phase 4 from row-count checks to a **value sweep** — compare every row × column of the final outputs against the reference. Quirks you're tempted to "fix" (sign conventions, mislabeled rows) are usually intentional: reproduce them, document them, and let the sweep arbitrate.

### Deduplicating multi-implementation projects

Real projects often have the same transformation implemented several ways (DATA step *and* PROC SQL; or `Formula` + `Filter` *and* `RunPython`). Identify the canonical production version, migrate that one, and note the alternatives as "skipped (alternative of step N)" in the inventory. Present the choice to the user before proceeding.

---

## Phase 2 — Migration plan

Map each migratable step to a Dataiku recipe. Pick types using `../../dku-cli/playbooks/tabular-flow.md` (decision rationale, exact CLI command, Python anti-pattern per recipe) and `<source>/overview.md` (priority: **Visual → SQL → Python**).

**Apply the collapse triggers as you draft, not after.** The full per-source list lives in `<source>/overview.md` § Collapse triggers. As you map each step, ask:

1. **Consecutive single-row transforms (Formula, Select, TextToColumns, DateTime, Filter)?** → fold into one Prepare recipe with N steps.
2. **Filter immediately upstream/downstream of a Group/Join/Window/Sort?** → fold into the visual recipe's `preFilter` / `postFilter` slot (see `../../dku-cli/playbooks/tabular-flow.md` § Collapse N recipes into 1).
3. **Computed column immediately upstream of a Group/Join/Window?** → fold into the visual recipe's `computedColumns` slot.
4. **Per-input Prepare adding a literal "source" column before a Stack?** → replace with `dku recipe create-stack --origin-column source` (the entire per-input layer disappears).
5. **Pivot or Unpivot whose only consumer immediately re-aggregates?** → compute the per-group aggregate **inline** in the upstream Prepare (`add-formula` per modality) and remove the reshape entirely.
6. **A "do this per Category" loop / batch macro?** → DSS expresses per-key iteration as a CROSS join on the key column. The macro body becomes one Join + (often) one Prepare.
7. **Any recipe whose only consumer is a `BrowseV2` / `Render` / Excel report?** → drop it. UI-only.

Plan shape:

```
| # | Source Step(s) | Recipe | Type | Input | Output | Key Operations |
|---|----------------|--------|------|-------|--------|----------------|
| 1 | …              | Prepare | Visual | … | … | … |
| 2 | …              | Join    | Visual | … | … | … |
| 3 | …              | Group   | Visual | … | … | … |
```

### Sanity check before presenting

Print a one-line ratio at the top of the plan: *"Source: N tools → Plan: M recipes (N/M ≈ X×)."* Expected **3–5×** for typical workflows. If you're at <2×, either re-walk the triggers (you've probably missed fold-ins or per-input Prepare-before-Stack patterns) or state explicitly why this workflow doesn't compress (small input, fully parallel branches, output-only chain). Then get user confirmation before Phase 3 (unattended run: print the plan and proceed immediately — never end the turn on a question).

---

## Phase 3 — Build & verify (incremental, in functional units)

```bash
# 3.1 — Upload source data (first time only)
dku dataset create DS --type UploadedFiles -P PROJ && \
dku dataset upload DS /path/to/file.csv -P PROJ && \
dku dataset set-schema DS -P PROJ -d '[
  {"name":"id","type":"bigint"},
  {"name":"amount","type":"double"},
  {"name":"dt","type":"string"}
]'
# Leave date columns as string (type: date on a CSV yields all-null — parse with DateParser later).

# 3.2 — Create recipe (visual shortcuts auto-create outputs)
dku recipe create-filter filter_active -i DS --output-ds active \
    -f 'status == "A" && amount > 0' -P PROJ

# 3.3 — Validate BEFORE running (catches formula errors early)
# (a) For visual recipes with formula filters / computed cols, check $status.ok
dku --format json recipe get-settings filter_active -P PROJ \
  | jq '.payload | {pre: .preFilter."$status".ok, post: .postFilter."$status".ok}'
# Both should be true. If false, read .message and fix before continuing.
# (b) Then apply-schema
dku recipe apply-schema filter_active -P PROJ

# 3.4 — Run
dku recipe run filter_active -P PROJ --wait

# 3.5 — Verify output
dku dataset info active -P PROJ --recompute
dku dataset schema active -P PROJ
dku dataset head active -P PROJ -n 5
```

Compare row count against the source's expected count (SAS: NOTE in the log `NOTE: Table WORK.X created, with N rows`. Alteryx: cached `BrowseV2` data or a ground-truth CSV. Excel: row count of the source range.). If counts differ, investigate before continuing.

**The shipped ground truth is the contract — not the solution's literal tool config.** When a transformation's config *contradicts* the shipped expected output, reproduce the ground truth and note the divergence; don't blindly transliterate the config. Verify against the answer key on a row whose value depends on the contested step — e.g. a gap-fill: fill-with-0 vs forward-fill (LOCF) disagree on any row with an interior gap, and the GT tells you which the author used (for event-driven series — seat-share, event-only prices — LOCF is usually intended).

**A recorded verification must be the LAST touch.** Never add probe/diagnostic steps or scratch columns to a delivered recipe after recording "exact match" — the live project then diverges from its verification. Probe GREL semantics in a scratch recipe (or scratch project), or remove the probes and re-verify before reporting success.

**Float ties break sort parity.** Mathematically equal computed scores can differ in the last bit (`13.447368421052632` vs `…628`), flipping tied-row order vs the source's sorted output. To match a legacy sorted output exactly: sort on a rounded helper (`round(score * 1e12) / 1e12`), keep the full-precision metric in the delivered columns, drop the helper in a final cleanup step.

### Cadence: one-liner per recipe, summary per zone

Per recipe, a one-liner is enough: `recipe_name: input → output, N rows OK`. At the end of each functional unit / zone (or every 5–8 recipes for large flows), present a short summary table — recipes built, row counts vs. source, anything skipped. Reserve a richer per-recipe report for the cases where the row count *doesn't* match and you need to walk the user through what you tried. Verbose per-recipe narration on every step is unnecessary in a 30+-recipe flow.

### Independent branches can run concurrently

If two recipes share no upstream dependency (parallel branches in the source DAG), configure both, validate `$status.ok` on both, then run them in parallel — verify each terminus as it lands. The anti-pattern is *cascading 10+ unverified recipes*, not parallel builds.

### Cross-connection landing

If the source upload lands on a different connection from the rest of the flow (e.g. CSV → Filesystem, but the rest is on Snowflake), insert a single `sync` recipe to land it on the target connection before any further processing. Otherwise the one-engine-per-flow rule is silently violated.

---

## Phase 3.5 — Flow collapse & sanity check

Tier-1 collapse (Phase 2) reasons on the draft plan branch-by-branch — it never sees the whole emitted graph, so a correctly-translated flow still ships graph-shape redundancy. This pass is the backstop, on the **built** graph, source-agnostic. Open `references/flow-collapse.md` and work it end to end: inspection commands, the seven named rewrites (hoist below union · grouping fan-out · broadcast aggregate · dead nodes · join chain · consecutive Prepares · empty Prepares), the first-principles pass beyond them, the required Verdict table, and build-and-diff verification before deleting anything.

---

## Phase 4 — Integration test

Run the finish gate first — it turns "is this reviewable?" into one pass/fail verdict and prints the exact `dku ...` fix for anything that fails (orphan datasets, missing/templated descriptions, no wiki, unbuilt outputs, blank/type smells):

```bash
dku project audit -P PROJ                            # reviewability gate (read-only)
dku project audit -P PROJ --contract @parity.json    # + value-parity on named outputs
dku --format json dataset head FINAL_OUTPUT -P PROJ -n 5
```

`--contract` is how the Phase-1 parity reference becomes a check: per output, assert expected `columns`, `types`, `min_rows`, and `not_blank` keys (literal JSON, `@file.json`, or `-`). Treat it as a guardrail, not the whole sweep — still diff every row × column of the final outputs against the reference for exact parity; the contract just stops you declaring done while a column is missing or a count is wrong.

Present a migration summary: source step → recipe → output dataset → row count → status. Note anything skipped (non-migratable patterns; alternative implementations).

Finalize the wiki now (mandatory unless the user opts out): hand-write it (`dku wiki create`) with the final mapping table and any deviations from parity, in the project's working language. Link DSS objects natively in the wiki mapping table, e.g. `[clean_customers](recipe:clean_customers)` and `[customers_clean](dataset:customers_clean)`, not inline-code object names; see `../../dku-cli/playbooks/tabular-flow.md` § Flow organization.
