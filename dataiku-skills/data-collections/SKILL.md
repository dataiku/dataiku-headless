---
name: data-collections
description: Discover datasets through Dataiku Data Collections, which are curated cross-project catalogs. Use when a user wants to find a dataset by topic rather than by project.
---

# Data Collections

Use this skill to discover cataloged datasets across projects and gather grounded context for the next access or asset-change step.

## Data Collection Concepts

A Data Collection is a curated cross-project catalog of datasets. It helps users discover relevant datasets without first knowing the source project.

Each catalog entry identifies a dataset and its source project. Catalog membership does not grant the current project access to that dataset, and a dataset absent from a collection may still exist elsewhere on the instance.

To use a discovered dataset from another project, its source project must expose it to the target project through cross-project sharing.

## Workflow

1. Use `list_data_collections` to discover collections and choose one based on its name, description, tags, or item count.
2. Use `list_data_collection_objects` for the selected collection to discover cataloged datasets and their source projects.
3. When the user needs to use a discovered dataset in another project, use `./dataiku-skills/cross-project-sharing/SKILL.md` to inspect its existing sharing relationship and ground any sharing request.
4. When a dataset is not cataloged, use `./dataiku-skills/datasets/SKILL.md` to inspect datasets within a known project instead.
5. Route resulting project-asset or sharing changes through the relevant skill and `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_data_collections`
- `list_data_collection_objects`

## Safety Rules

- Discover collection IDs, source project keys, and dataset identifiers via tools; do not invent identifiers.
- Keep this skill read-only. Data Collections catalog datasets but do not grant access or change project assets.
- Do not fan out across every collection unless the user explicitly needs an instance-wide catalog search; this can be expensive on large instances.
