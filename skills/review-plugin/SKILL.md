---
name: review-plugin
description: Review a Dataiku DSS plugin for code quality, pattern adherence, and consistency. Produces a structured findings report with severity levels.
disable-model-invocation: true
context: fork
---

Review a Dataiku plugin for code quality, patterns, and consistency.

**Preferred**: Spawn the `plugin-reviewer` agent for deep reviews — it has full tool access (Read, Grep, Glob, Bash) and produces scored reports.

**Fallback** (if agent spawning is unavailable): Follow the manual steps below.

## Steps

1. **Determine plugin** — if `$ARGUMENTS` is provided, use it as the plugin path/name. Otherwise, look for directories containing `plugin.json` and ask which plugin to review (or review all).
2. **Read all source files** in the plugin directory
3. **Check against the canonical checklist** in `skills/dataiku/references/plugin-review-checklist.md` — read it now and apply every item.
4. **Run automated checks** (if available):
   ```bash
   ruff check {plugin-directory}
   ruff format --check {plugin-directory}
   ```
5. **Report findings** as a structured table with severity and recommendations:
   - **critical**: Will cause runtime errors, security issues, or data loss
   - **warning**: Will cause confusion, maintenance burden, or subtle bugs
   - **info**: Style, naming, or minor improvements
6. **Score** the plugin /10 using the rubric in the checklist reference.
