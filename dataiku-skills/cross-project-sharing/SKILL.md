---
name: cross-project-sharing
description: Share flow items from a source project to another project via DSS shared objects. Use when an agent must make a dataset, folder, saved model, knowledge bank, or evaluation store from project A usable as a read-only input in project B.
---

# Cross-Project Sharing

For a recipe or agent tool in project B to use an object from project A, A must share it with B. Use `list_shared_objects`, `share_objects`, `unshare_objects`. Idempotent. `local_name` is the dataset name for `DATASET` and the object id for all other types. Each item's `type` must be a non-empty DSS object type string.

Requires `Read project conf` + `Write project conf` on the source. UI alternative: open the source in a DSS Data Collection and click "Add to project" on a Quick-Sharing-enabled dataset.
