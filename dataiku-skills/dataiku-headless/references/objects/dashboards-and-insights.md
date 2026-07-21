# Dashboards and insights

A dashboard owns pages, layout, page filters, and tiles. Reusable insight content
is a separate project object. An insight tile points to an existing insight by
`insightId`; text, image, iframe, group, and title tiles carry dashboard content
or structure.

Page filters apply to a page, not one tile. The filter dataset must be compatible
with the insights it affects; a mismatch can make healthy tiles appear empty.

## Insight source types

| Insight type | Source or behavior |
|---|---|
| `chart` | Dataset chart definition, engine, encoding, and sampling |
| `dataset_table` | Dataset exploration table with persisted state |
| `data-quality` | Current Data Quality state of a referenced object |
| `model-evaluation_report` | A section from one evaluation-store entry |
| `saved-model_report` | A section from a saved-model report |
| `scenario_last_runs` | Recent scenario outcomes |
| `scenario_run_button` | A dashboard control that triggers a scenario |
| `web_app` | An inline WebApp |

Discover and inspect the source object before asking Cobuild to change an insight.
Discover the insight before asking Cobuild to place or change its dashboard tile.
