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

Produce a complete inventory of every source step / tool, its inputs, outputs, and what it does. **No Dataiku planning yet** — just understand the source. For complex sources (>20 tools) surface the inventory for a sanity check before drafting the plan; for small sources roll straight into Phase 2. The single consequential confirmation gate is between Phase 2 (plan) and Phase 3 (build).

Generic inventory template:

```
| # | Source ID | Source Type | What It Does | Inputs | Outputs | Migratable? |
|---|-----------|-------------|--------------|--------|---------|-------------|
| 1 | …         | …           | …            | …      | …       | Yes → …     |
```

For source-specific column meanings (`Source ID` vs `Tool ID` vs `SAS step name`), parsing logic, and inventory examples, read `<source>/overview.md`.

### Deduplicating multi-implementation projects

Real projects often have the same transformation implemented several ways (DATA step *and* PROC SQL; or `Formula` + `Filter` *and* `RunPython`). Identify the canonical production version, migrate that one, and note the alternatives as "skipped (alternative of step N)" in the inventory. Present the choice to the user before proceeding.

---

## Phase 2 — Migration plan

Map each migratable step to a Dataiku recipe. Pick types using `../../dku-cli/playbooks/tabular-flow.md` (decision rationale) + `../../dku-cli/playbooks/tabular-flow.md` (the exact CLI command + Python anti-pattern per recipe) and `<source>/overview.md` (priority: **Visual → SQL → Python**).

**Apply the collapse triggers as you draft, not after.** The full per-source list lives in `<source>/overview.md` § Collapse triggers. As you map each step, ask:

1. **Consecutive single-row transforms (Formula, Select, TextToColumns, DateTime, Filter)?** → fold into one Prepare recipe with N steps.
2. **Filter immediately upstream/downstream of a Group/Join/Window/Sort?** → fold into the visual recipe's `preFilter` / `postFilter` slot (top-level rule 12).
3. **Computed column immediately upstream of a Group/Join/Window?** → fold into the visual recipe's `computedColumns` slot.
4. **Per-input Prepare adding a literal "source" column before a Stack?** → replace with `dku recipe create-stack --origin-column source` (the entire per-input layer disappears).
5. **Pivot or Unpivot whose only consumer immediately re-aggregates?** → compute the per-group aggregate **inline** in the upstream Prepare (`add-formula` per modality) and remove the reshape entirely. This is also the only reliable workaround for the `create-pivot` modality-scan blocker.
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

Print a one-line ratio at the top of the plan: *"Source: N tools → Plan: M recipes (N/M ≈ X×)."* Expected **3–5×** for typical workflows. If you're at <2×, either re-walk the triggers (you've probably missed fold-ins or per-input Prepare-before-Stack patterns) or state explicitly why this workflow doesn't compress (small input, fully parallel branches, output-only chain). Then get user confirmation before Phase 3.

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
# Leave date columns as string (rule 6).

# 3.2 — Create recipe (visual shortcuts auto-create outputs)
dku recipe create-filter filter_active -i DS --output-ds active \
    -f 'status == "A" && amount > 0' -P PROJ

# 3.3 — Validate BEFORE running (catches formula errors early)
# (a) For visual recipes with formula filters / computed cols, check $status.ok
dku recipe get-settings filter_active -P PROJ -o json \
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

**The shipped ground truth is the contract — not the solution's literal tool config.** When a transformation's config *contradicts* the shipped expected output, reproduce the ground truth and note the divergence; don't blindly transliterate the config. Verify against the answer key on a row whose value depends on the contested step — e.g. a gap-fill: fill-with-0 vs forward-fill (LOCF) disagree on any row with an interior gap, and the GT tells you which the author used (for event-driven series — seat-share, event-only prices — LOCF is usually intended). (Ch.109)

### Cadence: one-liner per recipe, summary per zone

Per recipe, a one-liner is enough: `recipe_name: input → output, N rows OK`. At the end of each functional unit / zone (or every 5–8 recipes for large flows), present a short summary table — recipes built, row counts vs. source, anything skipped. Reserve a richer per-recipe report for the cases where the row count *doesn't* match and you need to walk the user through what you tried. Verbose per-recipe narration on every step is unnecessary in a 30+-recipe flow.

### Independent branches can run concurrently

If two recipes share no upstream dependency (parallel branches in the source DAG), there is no reason to build them sequentially. Configure both, validate `$status.ok` on both, then run them in parallel — verify each terminus as it lands. The "one at a time" anti-pattern this is replacing is *cascading 10+ unverified recipes*, not "ever submitting two builds in the same minute".

### Cross-connection landing

If the source upload lands on a different connection from the rest of the flow (e.g. CSV → Filesystem, but the rest is on Snowflake), insert a single `sync` recipe to land it on the target connection before any further processing. Otherwise rule 2 (one engine per flow) is silently violated.

---

## Phase 3.5 — Flow collapse & sanity check

Tier-1 collapse (Phase 2) reasons on the draft plan, per source, branch-by-branch — it never sees the whole emitted graph at once. So a correctly-translated flow still ships structural redundancy: two sibling branches translated identically, or one grouping recipe per metric joined back together. This pass is the backstop. It runs on the **built** graph and is **source-agnostic** — same rules whether the source was SAS, Alteryx, or Excel.

```bash
dku flow visualize -P PROJ                 # spot fan-outs and parallel branches
# Two recipes byte-identical? Diff their payloads:
diff <(dku recipe get-settings A -P PROJ -o json | jq .payload) \
     <(dku recipe get-settings B -P PROJ -o json | jq .payload)
```

Five named rewrites to hunt — full detect / precondition / rewrite / verify in `references/flow-collapse.md`:

1. **Hoist an identical transform below a union** — N identical sibling Prepares → one Stack then one Prepare.
2. **Merge a grouping fan-out** — N single-aggregation groupings (same input + keys) joined back → one multi-aggregation grouping.
3. **Collapse a broadcast aggregate** — Group → join-back-on-key → one unbounded-frame Window.
4. **Drop dead nodes** — display-only / redundant-sort / sample-then-rebuild.
5. **Fuse a sequential join chain** — N joins each adding one input (equi-join lookup ladder *or* cross/cartesian combination grid) → one multi-input Join recipe.

**These five are a floor, not a checklist.** After working them, do one no-checklist pass: for every linear run and fan-in, ask whether a single native DSS recipe (multi-input Join, multi-step Prepare, Group with `computedColumns` + pre/post-filter, unbounded Window) reproduces the subgraph's output. An intermediate dataset consumed only by the next recipe is the tell. Collapse for the smallest correct, legible flow — readability can veto, "didn't look" can't. See `references/flow-collapse.md` § Beyond the catalog.

**Verify every rewrite before deleting anything.** Build the replacement into a fresh output and compare row counts (`dku dataset info --recompute`) and spot-checked values against the pre-collapse output. A row-count *increase* after merging a grouping fan-out means you dropped the INNER join's implicit row-filter — reproduce it with a postFilter. Only repoint consumers and delete old nodes once counts and values match.

---

## Phase 4 — Integration test

```bash
dku recipe list -P PROJ
dku dataset list -P PROJ
dku dataset head FINAL_OUTPUT -P PROJ -n 5 -o json
```

Present a migration summary: source step → recipe → output dataset → row count → status. Note anything skipped (non-migratable patterns; alternative implementations).

If a wiki was bootstrapped via `dku project ai-describe --save` in Phase 3, refine it now with the final mapping table and any deviations from parity. Link DSS objects natively in the wiki mapping table, e.g. `[clean_customers](recipe:clean_customers)` and `[customers_clean](dataset:customers_clean)`, not inline-code object names; see `../../dku-cli/playbooks/tabular-flow.md` § Project wiki.
