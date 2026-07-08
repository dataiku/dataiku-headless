---
name: skill-optimization
description: Review and compress an agent skill (SKILL.md, playbook, reference) so it steers rather than commands. Use when asked to review, tighten, de-bloat, or optimize a skill file, when a skill has accumulated incident scars, or when deciding whether a proposed skill addition (issue, review feedback, incident note) is worth its tokens.
---

# Skill optimization

A skill steers a capable agent; it doesn't legislate to an incompetent one. The reader is already very smart — every sentence must either hand it a fact it doesn't have or tilt a decision it was about to make. Everything else is drag, and drag isn't neutral: the context window is a public good, and noise buries the load-bearing lines. Calibrate to the weakest reader the file actually serves — scaffolding that insults a frontier model can be load-bearing for a smaller one.

## The pass

Read the file cold, as its consumer would. Classify each sentence:

| Class | Looks like | Action |
|---|---|---|
| Fact | exact flag, payload key, detector, gotcha+fix | keep, verbatim precision |
| Steering | a principle that tilts a choice ("readability can veto; 'didn't look' can't") | keep once, as a principle |
| Narration | justification, origin story, restatement, things the model already knows | cut |
| Duplicate | the same fact's second home | cut, point to the first |

Paragraph test: compress to one phrase, then ask what the agent would now do differently. Nothing → it was narration. Per piece of information: "can I assume the model knows this?" and "does this paragraph justify its token cost?"

Verdict the file, not just its sentences: one skill does one job. A file doing two jobs splits; two files always read together merge.

## One home per fact

A fact stated twice will drift. Pick the canonical home — a table for enumerable facts, prose where it's consumed in context — and make every other occurrence a pointer. Across files: a hub doc indexes a reference's sections one line each, never restates its paragraphs. A pointer sitting next to a restatement of the same paragraph is the drift engine fully assembled.

Structure follows loading: metadata is always in context, SKILL.md loads on trigger, references load on demand. So the description is a trigger — what + when, third person, carrying the symptoms and error strings an agent would actually have in context, and slightly pushy (agents measurably under-trigger). It is never a workflow summary: an agent will follow the description instead of opening the file. SKILL.md is a router under 500 lines, and references hang one level deep with a TOC past ~100 lines. A reference the agent re-reads every task belongs in SKILL.md; one it never opens is dead weight or badly signaled.

## Freedom matches fragility

State constraints as facts, not commands — "the `subscriptions` table is append-only" steers harder than "NEVER update subscriptions" and ages better. Reserve imperatives and exact sequences for the narrow bridge: fragile, irreversible operations with one safe path (deletes, publishes, migrations). Open fields get direction and trust. When everything is bold, nothing is.

Emphasis scars ("THIS flow", a rule restated three ways) are incident residue; the durable fix is one gotcha row in the right table. Escalate to MUST only after observing an agent miss the rule — and spend the escalation on that one rule, not the whole file. Match the form to the failure: a rule skipped under pressure needs a prohibition plus the named rationalization; a wrong output shape needs a positive template; conditional behavior needs a condition on an observable predicate. Restating the fact louder fixes none of these. A mandated artifact (checklist, verdict table) is legitimate when it forces a pass to actually happen; keep its scaffold minimal and don't re-encode facts that live elsewhere into its columns.

## What survives compression

Edge cases and gotchas carry the highest signal — build them from observed failures, one line each, one table. Also: exact mechanics (flags, keys, schemas), detectors and preconditions, verification loops for irreversible steps, one default with an escape hatch (never a menu of equivalent options), one concrete example per pattern.

Compression deletes words, never facts: after rewriting, list every flag, key, detector, and gotcha in old vs new — the lists must match.

## Admitting a new fact

A candidate earns its line when the failure was observed, not anticipated; the fix is non-derivable from `--help`, the API, or the model's own knowledge; it has exactly one home at the right loading layer (always-loaded router line vs on-demand reference); and it names the symptom an agent would search for. Unconfirmed shapes enter marked unconfirmed or not at all — never reconstructed from a failure report. Conflicting observations (works on one install, missing on another) land as the variance itself, not as both claims.

## Verify by behavior, not by reading

The fact diff proves nothing was deleted; only a run proves nothing was broken. Before compressing, capture one representative task the skill exists for and the failure it prevents; after, run a fresh agent on that task with the new file. A pass is the only evidence the compression was safe; a miss whose rationalization you can quote is the next edit. Additions face the same bar — baseline the agent without the new line before concluding it was needed.

## Smells

- The same precondition in the prose AND a checklist column AND a traps table.
- "This rule was added after…" — history, not guidance.
- Numbered cross-refs ("rule 12") — they break on recompaction; name the rule.
- Hand-written flag tables shadowing `--help`.
- A long exact-sequence block the agent must replay verbatim — a script wearing a markdown costume.
- A defensive bullet that only makes sense if you know the incident behind it.
- A menu of libraries/approaches where a default + escape hatch would do.
- Time-sensitive content ("before August 2025…") in the main path.
- Mixed terminology for one concept (endpoint/URL/route) — pick one.

Expect 30–50% fewer lines on a typical scarred file. Much less and you've classified narration as steering; much more and you've started deleting facts.
