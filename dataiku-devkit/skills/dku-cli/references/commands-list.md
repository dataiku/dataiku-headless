# Command Groups Reference

Complete list of all `dku` command groups and verbs.

## Quick Reference Table

| Group | Verbs | Needs Project? |
|---|---|---|
| `auth` | login, logout, status, list, switch | No |
| `config` | set, get, list, path, variables, set-variables | No |
| `project` | list, get, **inspect**, export, create, delete, duplicate, set-metadata, variables, set-variables, permissions, set-permissions, tags, **ai-describe, timeline** | No |
| `plugin` | list, get, push, delete, **download**, settings, create-code-env, set-code-env, update-code-env, usages, **recipes, list-files, get-file, put-file, rename-file, move-file, install-from-store, install-from-git, update-from-store, update-from-git** | No |
| `code-env` | list, get, create, delete, update | No |
| `connection` | list, **get**, create, **delete**, test, **schemas, tables, sync-acls** | No (schemas/tables need `-P`) |
| `user` | list, **get**, create, **delete, activity, add-secret** | No (admin) |
| `sql` | query | No |
| `dataset` | list, schema, **info**, head, build, create, upload, delete, clear, get-definition, set-definition, set-schema, **set-metadata, set-column-description, ai-describe, rename, copy, partitions, exists, usages, lineage, detect, zone, share, unshare** | Yes |
| `recipe` | list, get, **get-definition**, run, create, delete, set-code, get-code, set-definition, **get-settings, set-settings**, add-input, add-output, check-schema, apply-schema, **rename, status**, **create-join, create-group, create-stack, create-distinct, create-sort, create-filter, create-window, create-split, create-topn, create-pivot, create-sampling**, create-embed, create-embed-docs, create-extract, create-llm-eval, create-agent-eval, **list-steps, add-step, get-step, remove-step, disable-step, enable-step, add-formula, add-rename, add-filter-rows, add-fill-empty, add-delete-columns, add-find-replace, add-fold, add-geopoint, add-geodistance** | Yes |
| `scenario` | list, run, abort, status, create, delete, get-definition, set-definition, **last-run, runs, avg-duration, run-log, set-metadata, list-triggers, add-trigger, add-trigger-dataset, remove-trigger** | Yes |
| `job` | list, run, status, log, abort, wait | Yes |
| `model` | list, get, versions, set-active-version, metrics, delete-version, delete, usages, **set-metadata, create-mlflow, import-mlflow, create-external** | Yes |
| `folder` | list, ls, upload, download, create, delete, delete-file, get, create-dataset, **set-metadata** | Yes |
| `llm` | list, completion, embeddings, **generate-image, rerank** | Yes |
| `webapp` | list, start, stop, status, get-definition, set-definition | Yes |
| `dashboard` | list, get, create, delete, get-definition, set-definition, **set-metadata** | Yes |
| `evaluation-store` | list, create, get, evaluations, latest, build, delete | Yes |
| `insight` | list, get, create, delete, validate, get-definition, set-definition, **set-metadata** | Yes |
| `macro` | list, run | Yes |
| `flow` | graph, **visualize**, zones, create-zone, **set-zone**, **move**, propagate, check, sources, successors | Yes |
| `library` | list, read, write, delete, mkdir | Yes |
| `agent` | list, create, get, delete, wake-up, shutdown, status, add-tool, set-llm, set-prompt, test, **set-metadata** | Yes |
| `agent-review` | list, create, get, delete, set-agent, set-llm, add-trait, list-tests, create-test, import-tests, export-tests, run, list-runs, results | Yes |
| `agent-tool` | list, get, **create** (--dataset, --llm, --kb), set-definition, run, types, delete | Yes (except `types`) |
| `code-studio` | list, create, get, delete, status, start, stop, change-owner, templates | Yes (except `templates`) |
| `git` | status, log, diff, commit, pull, push, fetch, branches, create-branch, delete-branch, switch, tags, create-tag, remote | Yes |
| `api-deployer` | list-infras, list-services, get-service, list-deployments, create-deployment, get-deployment, update-deployment, delete-deployment, deployment-status | No |
| `project-deployer` | list-infras, list-projects, list-deployments, create-deployment, get-deployment, update-deployment, delete-deployment, deployment-status | No |
| `notebook` | list, get, create, delete, sessions, stop, clear-outputs, history | Yes |
| `discussion` | list, get, create, reply | Yes |
| `knowledge` | list, create, get, set-definition, build, search, delete | Yes (accepts name or ID) |
| `semantic-model` | list, create, get, delete, versions, get-version, create-version, set-version, set-active-version, distinct-values, update-index | Yes (accepts name or ID) |
| `agent-hub` | list, config, set-config, list-agents, add-agent, remove-agent, set-agent, set-llm, start, stop | Yes (auto-detects hub) |
| `bundle` | list, export, download, import, activate | Yes |
| `api-service` | list, create, get, create-package, list-packages, **add-endpoint, list-endpoints, publish-package, delete-package** | Yes |
| `rag` | **list, create, get, delete, get-definition, set-definition** | Yes |
| `continuous` | **list, start, stop, status** | Yes |
| `meaning` | **list, get, create, update** | No (admin) |
| `project-folder` | **list, create, move-project** | No |
| `model-comparison` | **list, create, get, add-model, remove-model, delete** | Yes |
| `workspace` | **list, create, get, list-objects, delete** | No |
| `app` | **list, get, list-instances, create-instance** | No |
| `app-designer` | **enable, disable, get, set-definition, set-section, list-tiles, add-tile, remove-tile** | Yes |
| `streaming` | **list, create, get, delete, schema, set-schema** | Yes |
| `admin` | **logs, get-log, usage, instance-info, sanity-check** | No (admin) |
| `api-key` | **list, get, create, delete** | No (admin) |
| `cluster` | **list, get, create, start, stop, status, delete** | No (admin) |
| `wiki` | list, create, get, update, delete | Yes |
| `(root)` | whoami | No |

## Key Notes

- `dku llm list` defaults to `GENERIC_COMPLETION`. Pass `--purpose TEXT_EMBEDDING_EXTRACTION` for embedding models.
- `dku llm embeddings` rejects completion-only model IDs.
- `dku semantic-model` — Only active version is used by agents. Always `update-index --wait` after changing entities/attributes.
- `dku agent-hub` — Cannot create via CLI (it's a plugin webapp). Create in DSS UI first.

> For exact command syntax and flags, see `commands.md`.
