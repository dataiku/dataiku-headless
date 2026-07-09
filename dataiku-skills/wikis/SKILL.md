---
name: wikis
description: Create, read, update, and delete wiki articles in a Dataiku DSS project. Use when an agent must list wiki articles, read article content, create new articles, edit article names or bodies, move articles in the hierarchy, or delete articles.
---

# Wiki Operations

Use Dataiku MCP tools to manage wiki articles inside a DSS project.

## What Is a DSS Wiki?

Each DSS project has one wiki — a structured collection of markdown articles organized in a tree hierarchy (parent/child). Articles have a display name, a markdown body, and a position in the taxonomy. One article can be designated as the home article.

## Follow This Execution Pattern

1. Call `list_wiki_articles` to discover existing articles, their IDs, parent hierarchy, and which article is the home article.
2. Announce the intended action in one sentence before any mutation.
3. For reads: call `get_wiki_article` with the article ID.
4. For creates: call `create_wiki_article`. Provide `parent_article_id` to nest the article.
6. For updates: call `update_wiki_article`. Pass only the fields that need to change.
7. For deletes: confirm with the user first — deletion is irreversible.
8. After any mutation, validate by calling `list_wiki_articles` or `get_wiki_article`.

## Tool Reference

| Goal | Tool |
| --- | --- |
| Discover all articles and hierarchy | `list_wiki_articles` |
| Read article content (name + body) | `get_wiki_article` |
| Create a new article | `create_wiki_article` |
| Update name, body, or hierarchy position | `update_wiki_article` |
| Delete an article | `delete_wiki_article` |

## Key Behaviors

- **Article IDs vs names**: Tools that mutate articles require the `article_id` (e.g. `"nMHjj59X"`), not the display name. Always call `list_wiki_articles` first to resolve names to IDs.
- **body is full-replace**: `update_wiki_article` with a `body` argument replaces the entire article body. Read the existing body with `get_wiki_article` first if you want to append or patch content.
- **Hierarchy**: `create_wiki_article` accepts an optional `parent_article_id`. `update_wiki_article` accepts `new_parent_article_id` to move an article, or `move_to_top_level=True` to remove its parent.
- **Deletion**: `delete_wiki_article` is irreversible. Always confirm with the user before calling it.

## DSS Object References

Wiki article bodies support clickable references to DSS project objects using markdown link syntax:

```
[Display Name](object_type:object_id)
```

Or without a display name (DSS renders a default badge):

```
object_type:object_id
```

To link to another wiki article within the same project:

```
[[Article Name]]
```

### Supported object types

| Object type | Reference syntax | ID source |
| --- | --- | --- |
| Dataset | `dataset:<name>` | Dataset name (not a hash) |
| Recipe | `recipe:<name>` | Recipe name |
| Saved model | `saved_model:<id>` | Saved model ID (hash) |
| ML analysis | `analysis:<id>` | Analysis ID (hash) |
| Agent | `ai_agent:<id>` | Agent ID (hash) |
| Agent tool | `agent_tool:<name>` | Agent tool name |
| Scenario | `scenario:<id>` | Scenario ID |
| Dashboard | `dashboard:<id>` | Dashboard ID (hash) |

Use `get_flow_items_in_traversal_order` to discover dataset and recipe names, and `list_saved_models`, `list_agents`, `list_scenarios` etc. to discover IDs for other object types. Never invent IDs — always discover them.

## Safety Rules

- Never invent article IDs — always discover them with `list_wiki_articles`.
- Do not overwrite an existing body without first reading and presenting the current content to the user.
- Treat deletion as a destructive action — confirm explicitly before calling `delete_wiki_article`.
