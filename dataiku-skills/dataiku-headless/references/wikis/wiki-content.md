---
name: wiki-content
description: Conceptual guide to Dataiku wiki hierarchy, Markdown content, and project-object references for Cobuild requests.
---

# Wiki Content

Read this reference when a wiki request involves article placement, links, or project-object documentation.

Wiki articles use Markdown and are organized into a parent/child hierarchy. One article can be the wiki's home article. Use the hierarchy to group related documentation and avoid duplicate pages.

## Links And References

- Link to another wiki article with `[[Article Name]]`.
- Reference a project object with `[Display Name](object_type:object_id)`.

| Object category | Reference type |
| --- | --- |
| Dataset | `dataset:<name>` |
| Recipe | `recipe:<name>` |
| Saved model | `saved_model:<id>` |
| ML analysis | `analysis:<id>` |
| Agent | `ai_agent:<id>` |
| Agent tool | `agent_tool:<name>` |
| Scenario | `scenario:<id>` |
| Dashboard | `dashboard:<id>` |

Discover each referenced object through its relevant reference guide. Do not invent names or identifiers for a wiki reference.
