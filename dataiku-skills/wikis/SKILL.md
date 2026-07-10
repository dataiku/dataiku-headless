---
name: wikis
description: Inspect Dataiku wiki articles and use the results as context for Cobuild. Use when an agent must discover wiki structure or read article content before asking Cobuild to create or modify project assets.
---

# Wiki Inspection

Use this skill to inspect existing wiki articles.

## Workflow

1. Use `list_wiki_articles` to discover article ids, names, and hierarchy.
2. Use `get_wiki_article` to read article content.
3. Route wiki creation, editing, moving, or deletion through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_wiki_articles`
- `get_wiki_article`

## Safety Rules

- Never invent article ids.
- Keep this skill focused on inspection and Cobuild grounding.
