---
name: cli-meta-analysis
description: Reflect on your usage of the `dku` CLI, Dataiku skill, and platform knowledge during this conversation. Surface actionable insights that would improve the skill, CLI, or reference docs for future agent runs. Use at the end of any session involving DSS work — building projects, running dku commands, debugging CLI errors, or using Dataiku platform features. Writes findings to `.learnings/PENDING.md` in the current working directory for later processing.
triggers:
  - meta analysis
  - cli meta
  - analyze session
  - what went wrong
  - improve the skill
  - session learnings
metadata:
  author: dataiku
  version: "1.0.0"
  tags: dataiku, dss, cli, improvement, feedback
---

# cli-meta-analysis

Reflect on this session and extract actionable insights that would improve the `dku` CLI, skill docs, or reference docs for future agent runs.

## What to Analyze

Review everything you did in this conversation — commands run, docs read, mistakes made, workarounds used — and extract patterns across these dimensions:

### 1. CLI Friction

Commands or workflows where you:
- Had to retry or guess flags
- Got unhelpful error messages that didn't tell you what to do next
- Needed to read source code because `--help` was insufficient
- Wished a command existed but had to use Python/API instead
- Used the wrong command first before finding the right one

### 2. Skill & Doc Gaps

Places where the skill (`SKILL.md`) or reference docs:
- Didn't mention something you needed (missing pattern, missing gotcha)
- Buried critical info too deep (you found it late or by accident)
- Were wrong or outdated vs actual CLI/API behavior
- Didn't steer you toward a built-in DSS feature when one existed
- Had examples that weren't copy-paste-runnable

### 3. Gotchas Hit

Concrete errors or surprises where knowing the answer upfront would have saved significant time. For each:
- What you tried
- What went wrong
- What the fix was
- Where this should be documented (CLI error message / SKILL.md cheat sheet / gotchas table / reference doc)

### 4. dataikuapi Discoveries

Any `dataikuapi` behaviors you discovered that aren't documented:
- Unexpected return types
- Methods that don't exist or work differently than expected
- Payload structures that differ from what docs suggest

### 5. Built-In Feature Misses

Cases where you wrote Python/custom code but a built-in DSS feature (visual recipe, GenAI recipe, AutoML, agent, knowledge bank) could have done it. Be honest — this is the highest-value feedback.

## Output Format

Write the analysis directly in chat using this structure:

```
## Meta Analysis: [brief description of what you built]

### TL;DR
[2-3 sentence summary of the biggest insights]

### CLI Friction (N issues)
| Issue | What Happened | Suggested Fix |
|-------|--------------|---------------|
| ...   | ...          | ...           |

### Skill & Doc Gaps (N issues)
| Gap | Impact | Where to Fix |
|-----|--------|-------------|
| ... | ...    | ...         |

### Gotchas Hit (N issues)
For each:
- **Tried**: [what you did]
- **Failed**: [what went wrong]
- **Fix**: [what worked]
- **Document in**: [CLI error / SKILL.md cheat sheet / gotchas table / reference doc]

### dataikuapi Discoveries
| Quirk | Details | Add to CLAUDE.md? |
|-------|---------|-------------------|
| ...   | ...     | ...               |

### Built-In Feature Misses
| What I Did | What DSS Has | Priority |
|-----------|-------------|----------|
| ...       | ...         | ...      |

### Recommended Changes (ranked by agent impact)
1. [highest impact change — file path + what to change]
2. ...
```

## Rules

- **Be brutally honest.** The point is to find gaps, not to report success.
- **Concrete over vague.** "Error message was unhelpful" is useless. "Running `dku recipe create -t python` without `--connection` gave 'creationInfo params are suppressing it' with no suggestion to add `--connection`" is actionable.
- **Skip things that worked fine.** Don't pad the report with "X worked great." Focus on friction.
- **Rank by agent impact.** A missing cheat sheet rule that would prevent 5 retries > a cosmetic --help tweak.
- **If nothing went wrong, say so.** A clean run is valid signal too — means the skill is working.

## Final Step: Persist to `.learnings/PENDING.md`

After writing the analysis to chat, append it to `.learnings/PENDING.md` in the **current working directory**.

If the file doesn't exist yet, create it with this header first:
```
# Pending Learnings

Insights from past sessions. Copy relevant entries to the dataiku-cli repo's `.learnings/PENDING.md` to process them into fixes via `/cli-improvement`.

---
```

Then append the full analysis under a dated entry:
```
## [YYYY-MM-DD] <brief session description>
**Status:** pending

<paste the full analysis here>

---
```

Before appending, scan the existing file for entries with the same symptom or command. If found, add a `**Recurring** (also seen: YYYY-MM-DD)` note to the new entry — recurring issues get fixed first.
