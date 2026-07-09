---
name: data-collections
description: Discover datasets on the instance via DSS Data Collections — curated cross-project catalogs. Use when the user wants to find a dataset by topic rather than by project.
---

# Data Collections

Browse curated cross-project catalogs of datasets. Uncatalogued datasets are invisible to this skill — for those, inspect projects directly via `list_datasets`.

- `list_data_collections` — index of collections (`id`, `name`, `description`, `tags`, `item_count`).
- `list_data_collection_objects(collection_id)` — items in one collection. Each item is `{type, project_key, id}` where `type` is always `DATASET` (the DSS API only catalogues datasets). Call `list_data_collections` first to get a `collection_id` — fanning out across every collection is expensive on large instances.

To use a found item in your project, share it from its source `project_key` via the `cross-project-sharing` skill — Data Collections only catalogues; it does not grant access.
