---
name: wikis
description: Understand and inspect Dataiku wiki articles, then use grounded context for Cobuild documentation work. Use when reviewing wiki structure, article content, or planning wiki changes.
---

# Wikis

Use this guide to understand existing project documentation and plan grounded wiki work through Cobuild.

Apply the shared operating rules in `../SKILL.md` for routing, grounding, and validation.

## Wiki Concepts

Each Dataiku project has a wiki composed of Markdown articles organized in a parent/child hierarchy. An article has a title, body, and position in the tree; one article can serve as the home article.

Wiki articles can document project assets through Dataiku object references and can link to other articles. Creation, edits, moves, and deletion route through Cobuild.

Read [wiki content](./wikis/wiki-content.md) when a request involves article links or Dataiku object references.

## Workflow

1. Use `list_wiki_articles` to discover article identifiers, hierarchy, and the home article.
2. Use `get_wiki_article` to read a selected article before interpreting or changing its content.
3. For new or moved content, inspect the intended parent and nearby articles to ground placement and avoid duplication.
4. Discover any referenced project objects through their object-specific skills.
5. Route wiki creation, edits, moves, and deletion through `./cobuild.md`.
6. Re-read the article or hierarchy after a Cobuild change when validation is needed.

## Supporting Context

- Datasets and recipes: `./datasets.md` and `./recipes.md`
- Models and analyses: `./machine-learning.md`
- Agents and reviews: `./agents.md` and `./agent-reviews.md`
- Scenarios and dashboards: `./scenarios.md` and `./dashboards.md`

## Preferred Tools

- `list_wiki_articles`
- `get_wiki_article`

## Safety Rules

- Read an existing article before requesting a content change.
- Preserve existing Markdown body content unless the user requests replacement.
- Inspect hierarchy before moving or nesting an article.
- Treat deletion as destructive, even though Cobuild manages confirmation.
- Keep this skill focused on inspection, concepts, and Cobuild grounding. Do not document direct wiki mutation workflows here.
