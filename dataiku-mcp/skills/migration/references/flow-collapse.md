# Flow collapse & sanity check (source-agnostic)

The **Tier-2** pass — Phase 3.5, on the **built** DSS graph, same rules for every source. Tier-1 (the source's Collapse-triggers section — `<source>/overview.md`, or `analysis-workbooks.md`/`model-workbooks.md` for xlsx — Phase 2) folds *source idioms* branch-by-branch; it never sees the whole graph, so it ships graph-shape redundancy — identical sibling branches, per-metric groupings joined back, join chains. This pass catches that.

## Inspect the graph

```bash
dku flow graph -P PROJ                       # node/type table — find chains and fan-ins
dku flow visualize -P PROJ                   # DAG shape — fan-outs, parallel branches
diff <(dku --format json recipe get-settings A -P PROJ | jq .payload) \
     <(dku --format json recipe get-settings B -P PROJ | jq .payload)   # byte-identical siblings?
```

An identical `.payload` diff proves rule 1. For the rest, read each recipe's `keys`, `values`, `preFilter`, join `type`.

## Verdict table (required — emit before Phase 4)

Phase 3.5 is a visible artifact, not a skim. Fill this in for THIS flow before moving on:

| Rule | Applies? (which nodes) | Check | Verdict |
|---|---|---|---|
| 1 · Hoist below union | … | sibling payloads identical? | collapse → … / keep: … |
| 2 · Merge grouping fan-out | … | same input+keys? divergent filter? join type? | collapse → … / keep: … |
| 3 · Broadcast aggregate | … | group→join-back on partition key? | collapse → … / keep: … |
| 4 · Drop dead nodes | … | only consumer is display/export/ordering? | drop … / none |
| 5 · Fuse join chain | … | join types compose? keys on left side? | collapse → … / keep: … |
| 6 · Merge consecutive Prepares | … | intermediate single-consumer? engine split? | collapse → … / keep: … |
| 7 · Delete empty Prepares | … | zero steps? schema/connection actually no-op? | drop … / none |
| + · First-principles | any subgraph DSS emits in fewer nodes | one native recipe reproduces it? | collapse → … / none |

- **Run the `diff`** on every sibling pair feeding a union/join — "looks similar" is not the check. The most-missed collapse is two byte-identical Prepares before a Stack.
- **"Keep" needs a reason.** Readability is a valid one; what's forbidden is shipping redundancy without evaluating it — not "always minimize node count".
- A healthy Phase-2 ratio doesn't excuse skipping this. Restate the ratio after any rewrite.

## The catalog (detect → precondition → rewrite; verify every one, below)

**1 · Hoist an identical transform below a union.** ≥2 byte-equal recipes feeding one Stack. *Safe only if every step is row-wise* — a Window/Distinct/TopN depends on the per-branch population and breaks if you stack first. Move the Stack upstream of one copy: `s₁→prep→o₁; s₂→prep→o₂; (o₁,o₂)→stack` ⟶ `(s₁,s₂)→stack(UNION,+origin)→prep`. **N prepares + stack → 1 stack + 1 prepare.**

**2 · Merge a grouping fan-out.** N single-aggregation groupings, same input + same keys, joined back on those keys (RFM: max date / count / sum, 3-way join). Two traps: (a) a **divergent pre-filter** on one branch — re-express it as an indicator column and `sum()` it (`is_recent=if(diff(now(),date,"days")<=730,1,0)` → `sum`); (b) **join type** — an INNER join drops keys absent from a filtered branch, so the merged grouping (which keeps them at 0) needs a `postFilter` (`is_recent_sum >= 1`) to match; LEFT keeps them as null. Rewrite: one `create-group` with all aggregations + indicator columns + `--no-global-count`, then set the postFilter (mechanics: `../../dku-cli/references/visual-recipe-payloads.md`). **N groupings + join → 1 grouping.**

**3 · Collapse a broadcast aggregate.** A Group computing a per-partition stat, joined straight back to the rows on the partition key (impute / normalize / ratio-to-group). Join must be LEFT/INNER on the full key, no row multiplication. Replace with one Window partitioned by the key, `--frame-unbounded` (else it accumulates cumulatively). **Group + Join → 1 Window.**

**4 · Drop dead nodes.** A recipe whose only consumer is display/export (`BrowseV2`, `Render`, Excel), a sort feeding an op that doesn't need order, or sample-then-rebuild. Confirm nothing downstream depends on it, then delete.

**5 · Fuse a sequential join chain.** ≥2 joins in a line, each adding one input (`A⋈B→AB; AB⋈C→ABC`), every intermediate consumed only by the next join — an equi-join lookup ladder *or* a cross/cartesian combination grid (often emulated as LEFT/INNER on a constant key `_k`). The Join recipe takes 2+ inputs, so the ladder is one node. *Safe if the join types compose into one left-deep ladder (all the same type, or reordering can't change the row set) and each key sits on the accumulated left side (else set `joins[i].table1` — § Join in `../../dku-cli/references/visual-recipe-payloads.md`).* Rewrite: one `create-join` with all inputs — cross grid `-i a -i b -i c -j CROSS` (no keys; drop the `_k` helper); equi-ladder `-i spine -i a -i b -k key -k 1:akey` (each `-k` after the first targets pair N). **N joins + (N−1) intermediates → 1 join — usually the biggest single reduction in a flow.**

**6 · Merge consecutive Prepares.** ≥2 Prepare recipes in a line, each intermediate consumed only by the next — the built-graph backstop of the Phase-2 "consecutive row-local transforms" trigger (1:1 drafts ship these). Steps run in order inside one Prepare, so concatenation is semantics-preserving: append B's `steps` onto A's (`get-settings` → splice → `set-settings`), `apply-schema`, repoint B's consumers to A's output, delete B + the intermediate. *Keep the split only if the intermediate is a genuine deliverable/shared dataset, or the upstream half is SQL-translatable and the downstream half isn't (merging demotes the whole recipe to the DSS engine).* **N Prepares + (N−1) intermediates → 1 Prepare.**

**7 · Delete empty Prepares.** A Prepare with zero (or all-disabled) steps — `dku recipe list-steps R -P PROJ` shows none — is a passthrough that exists only to mint a useless intermediate dataset (left over from 1:1 drafting or an abandoned rename/retype). Repoint its consumers to its *input* dataset, delete the recipe + output. *Check first that it isn't silently working anyway: an output schema that retypes columns (set-schema'd output), or an output on a different connection (it's doing a Sync's job — keep it or swap in an explicit `sync`).* **1 recipe + 1 dataset → 0.**

## Beyond the catalog — find the minimal flow yourself

The named rules are the *recurring* shapes, not the whole job: **the catalog is a floor, not a checklist.** A subgraph no rule names is still a collapse if DSS expresses the same output in fewer nodes — the next redundancy is usually one no rule anticipated. So after the named rules, do one pass with no checklist:

- For every linear run and fan-in, ask: *does one native recipe — multi-input Join, multi-step Prepare, Group with computed columns + pre/post-filter, unbounded Window — produce this output directly?* If yes, collapse it.
- **An intermediate dataset whose only consumer is the next recipe is the tell** — usually two recipes DSS would let you write as one.
- Aim for the smallest count that stays correct *and* legible. Readability can veto; "didn't look" can't.

Record what you find as extra Verdict rows. Every first-principles collapse earns the same proof as a named rule.

## Verify every collapse (build-and-diff — mandatory)

Never delete the old nodes until the replacement is proven equivalent on real data.

1. Build the new recipe into a **fresh** output (don't overwrite yet).
2. `dku dataset info OLD/NEW -P PROJ --recompute` — row counts must match; `dku --format json dataset head OLD/NEW -n 20` — spot-check per-key values. A row-count *increase* after rule 2 = the missing postFilter; fix before proceeding.
3. Only when counts and values match: repoint consumers to the new output, delete the old nodes.
4. After **each** rewrite, restate three lines so a regression is traceable to its cause: `recipes: N → M`, `rows: <old final> → <new final>` (must match), `<rule>: <which nodes>`.

## What silently breaks equivalence

| Rule | Trap |
|---|---|
| Hoist below union | a Window/Distinct/TopN that depends on the per-branch population |
| Merge grouping fan-out | divergent pre-filters (→ indicator-sum) and join type (INNER → postFilter; LEFT → null-vs-0) |
| Broadcast aggregate | Window is cumulative by default — needs `--frame-unbounded` |
| Drop dead nodes | a consumer that actually depends on the ordering/sampling |
| Fuse join chain | join types that don't compose, or a key on an input not yet joined |
| Merge consecutive Prepares | another consumer of the intermediate; an SQL→DSS engine split the merge would erase |
| Delete empty Prepares | a zero-step Prepare that still retypes (output schema) or lands on another connection (implicit Sync) |
