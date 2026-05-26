# Pending Learnings

Insights from past sessions. Copy relevant entries to the dataiku-cli repo's `.learnings/PENDING.md` to process them into fixes via `/cli-improvement`.

---

## [2026-05-26] PR87 dashboard and insight live verification
**Status:** pending

## Meta Analysis: PR87 dashboard and insight review fixes

### TL;DR
Live verification was clean once targeting a known project and dataset. The only friction was using `dku project list -o json` first on a very large DSS instance, which produced a huge payload and was slower/noisier than needed for a focused command check.

### CLI Friction (1 issue)
| Issue | What Happened | Suggested Fix |
|-------|--------------|---------------|
| Large project list payload | `uv run dku project list -o json` returned more than 1,600 lines on the live DSS instance while I only needed to confirm candidate projects for dashboard/insight testing. | Add a `--limit`, `--search`, or `--name-contains` filter to `dku project list`, or document that live verification should prefer known sandbox projects such as `ADVISORGPT` / `AGENTTEST` when available. |

### Skill & Doc Gaps (0 issues)
| Gap | Impact | Where to Fix |
|-----|--------|-------------|
| None found in the current skill flow. | The dku-cli skill correctly pushed me to live verification and the dashboard chart reference already had the persisted `genericMeasures[].function` shape. | N/A |

### Gotchas Hit (0 issues)
No unexpected DSS errors during the live round trip.

### dataikuapi Discoveries
| Quirk | Details | Add to CLAUDE.md? |
|-------|---------|-------------------|
| Dashboard create accepts seeded `pages` settings | Passing `settings={"pages": [...]}` through `proj.create_dashboard()` created a dashboard whose page persisted and allowed immediate tile insertion. | Already addressed in this PR's docs/tests; add to CLAUDE.md only if this becomes a recurring dashboard gotcha. |
| Chart measure aggregation persists as `function` | `COUNT_DISTINCT` must be stored as DSS's `COUNTD`; after save, DSS normalized the measure and preserved `"function":"COUNTD"`. | Already addressed in this PR's docs/tests. |

### Built-In Feature Misses
| What I Did | What DSS Has | Priority |
|-----------|-------------|----------|
| None. | N/A | N/A |

### Recommended Changes (ranked by agent impact)
1. Consider adding project list filtering to `src/dku_cli/commands/project.py` so live verification can avoid huge project-list payloads on shared DSS instances.
2. If dashboard workflows keep getting benchmarked, promote the default-page behavior and `genericMeasures[].function` gotcha into a dashboard-specific gotchas table.

---
