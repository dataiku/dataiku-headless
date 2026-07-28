# Contributing a Source Subskill

Source Subskill = directory `skills/dataiku-headless/references/migrations/sources/<kind>/` (kind kebab-case): reference `<kind>.md` plus optional helper scripts `*.py`.

Frontmatter:

```yaml
---
name: source-<kind>-reference
description: "How to read a <Source> bundle and the <Source> semantics needed to extract its business logic faithfully."
---
```

## The contract

Content = ONLY this source's SILENT failure modes — facts whose absence makes a migration WRONG or MIS-PARSED, silently.

Two framework safety nets already catch most failures loudly; restating them wastes space:
- Completion gate catches wrong SHAPE — schema / data-invariant (`gate/README.md`).
- Gap resolution catches unbuildable constructs (parent `references/migrations.md` § Gap resolution).

KEEP only what escapes BOTH nets — three kinds:

1. Silent VALUE divergences — source behavior yielding wrong-but-valid output vs DSS: aggregation null-handling, null semantics, formula / eval order, width / size truncation, source-formula→GREL traps mapping to a wrong or phantom GREL function.
2. Silent PARSE traps — bundle-reading silently yielding wrong / incomplete inventory: where real data / config lives, binary formats, multi-implementation dedup.
3. Silent MIS-REALIZATIONS (sparingly) — construct agent builds CONFIDENTLY WRONG rather than stalls on.

DROP everything else: obvious 1:1 tool→recipe mappings, ANY mapping / translation table, ALL code / CLI / XML / GREL example blocks, rationale / "why" prose, collapse or optimization hints, unbuildable / equivalent-lacking constructs (gap resolution's job).

Mapping table invites 1:1 transliteration, against DSS-Optimized Logic. Agent reads bundle, derives DSS-native realization from recipe-type subskills; Source Subskill flags only where that derivation goes silently wrong.

## Sections

Omit a section lacking content.

- `## Source Identification` — ONE line. File signatures, for routing.
- `## Recovering intent` (optional, comprehension-heavy sources) — DAG-first heuristics for reading what the bundle aims to achieve when intent is implicit, undocumented, mixed with presentation: harvest stated intent text, read dependency-graph topology, classify roles, recover structure the graph omits. Heuristics only — tool→construct maps stay on the DROP list.
- `## Reading the bundle (wrong/incomplete inventory)` — parse traps (kind 2). Terse caveman bullets or tiny code-free table; facts and instructions only.
- `## <Source> semantics (silent meaning changes)` — value divergences + mis-realizations (kinds 1, 3). Same form.
- `## Placeholders` (optional) — non-migratable hint sparing obvious thrashing.

## Writing style

Caveman: telegraphic, drop articles and filler.

State positively. Facts and instructions only — DROP-list items stay out.

Carry only source-specific knowledge. Reference parent `references/migrations.md` for workflow, Manifest, gap resolution.

Estimated size 30–90 lines.

## Helper scripts (optional)

Atomic source-parsers in `sources/<kind>/*.py`, one purpose each, named by purpose; directory carries the kind. Author as generic starting points the planner adapts. Declare deps minimally, prefer stdlib plus one parsing library. Output, stdout-digest, and first-docstring-line conventions: parent `references/migrations.md` § Helper scripts.

## Routing

Runtime routing lists `skills/dataiku-headless/references/migrations/sources/` (parent `references/migrations.md` Phase 2); shipping = one PR adding one `sources/<kind>/` directory: the `<kind>.md` reference plus any helper scripts.
