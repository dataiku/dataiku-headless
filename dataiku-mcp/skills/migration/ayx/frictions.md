# Frictions — DSS concepts Alteryx users push back on

Open this when the user's complaint is about *how DSS works* rather than about a specific tool. These are onboarding issues — not gaps — but treating them as gaps is the single biggest reason migrations stall.

Each entry: what the user says → what they actually want → what to point them at.

---

## Intermediate datasets

**User says:** "Why do I have 40 datasets in the Flow? I only want the final one. Storage is wasted and the Flow is cluttered."

**What they want:** either cleaner Flow layout, easier rebuild of changed downstream pieces, or "I can see the data change between tools" (the Alteryx preview paradigm — see below).

**Point them at:**
- **Flow Zones** to chunk the Flow into readable segments.
- **SQL pipelines** to collapse a chain of SQL recipes into one compiled query — no intermediate tables materialized.
- **Clear intermediate datasets** plugin (dataiku-contrib) to automate cleanup in a scenario post-build step.
- The **philosophy difference**: Alteryx materializes nothing between tools (desktop, single-process). DSS materializes every intermediate so you can inspect, resume from checkpoint, rebuild only what changed, and run recipes on different engines. Intermediate datasets are a feature of the server paradigm, not an artifact.

When they do refactor for production:
- Don't chain Prepares — collapse into one.
- Use recipe pre-/post-filters and computed columns.
- SQL pipelines for all-SQL segments.

---

## Dataset preview on every tool

**User says:** "In Alteryx I see the data change with every tool. Here I have to run the recipe, wait, then open the output dataset. Iteration is too slow."

**What they want:** a tight change → see-the-result loop.

**Point them at:**
- **Recipe dataset previews** (recent DSS) — shows the computed output sample in the recipe edit page.
- **Prepare recipe** already has this (the script view is live on a sample).
- **Run on sample** for visual recipes with heavy inputs — use the recipe's sample size setting.
- Open the input and output datasets in **two browser tabs** — DSS is web-native, not desktop. Liberate the user from one-window thinking.

---

## Record counts on the Flow

**User says:** "Alteryx shows row counts next to every tool after a run. How do I know at a glance if a recipe blew up the row count?"

**What they want:** fast visual sanity check that counts are sane across the Flow.

**Point them at:**
- **Record Count Flow view** (recent DSS) — right-click the Flow background → Flow view → record count. Trigger auto-compute in the dataset settings so counts refresh on each build.
- **Data Quality Rules / Metrics + Checks** — thresholded alerts that don't depend on eyeballing. Monitor unmatched-join-output row count > 0 as a DQ rule.
- **Scenario alerts** — email/Slack on build completion with row-count summary.
- `dku dataset info DS -P PROJ --recompute` — terminal-friendly row count.

The philosophy difference: DSS handles datasets bigger than one desktop can fit in memory, so per-tool row-count is opt-in, not automatic.

---

## Schema changes and downstream recipe breakage

**User says:** "I renamed a column upstream and now I have to open every downstream recipe and reconfigure it one by one."

**What they want:** schema changes propagate.

**Point them at:**
- **Auto-schema propagation** (recent DSS) — enable in project settings; column adds/removes/renames flow downstream automatically.
- **Schema propagation tool** (older DSS) — manual but reliable: open a Flow-level propagation dialog, accept the changes recipe-by-recipe.
- Warn them that rename-then-propagate can silently drop the renamed column in some DSS versions — spot-check downstream column lists after a rename.

---

## `*Unknown` columns (schema flexibility)

**User says:** "In Alteryx I tick `*Unknown` to let any future column pass through. How do I do that in DSS?"

**What they want:** flow that doesn't break when the source schema adds a new column.

**Point them at:**
- **Join recipe**: "non-matching columns" option (where available) passes through unmapped columns from either side.
- **Prepare**: by default does not drop unknown columns — a formula or rename step on a missing column will simply no-op on schema propagation.
- **Stack recipe** with `--mode UNION` (the default): union of columns across inputs.
- There is no blanket "always accept any future column" switch as in Alteryx. Tell the user: DSS is schema-aware, and the cost of that is a manual bump per recipe when the schema drifts. The win is deterministic downstream behavior.

File this as a real friction — the fix is a Product request, not a workaround. Keep a list of the user's specific pain points for feedback to Product.

---

## Detour / conditional flow branches

**User says:** "In Alteryx I can disable a Container based on a user selection in an App. How do I do that?"

**What they want:** "if condition, run this zone; else, run that zone" flow structure.

**Point them at:**
- **Split recipe at the zone entry**: all data goes to Zone A's output if the condition is true (Zone B's output is empty), and vice versa. Zone C (the downstream merge) runs on both but only one has rows.
- **Scenario step: build zone** (recent DSS) — conditional zone builds in a scenario rather than in the Flow.
- Empty dataset ≠ cleared dataset — DSS can consume an empty dataset as a valid recipe input; a cleared dataset breaks the recipe. Always prefer "empty via filter" over "clear in scenario".

---

## Drag-and-drop flow layout

**User says:** "I want to drag tools onto wires / rearrange the Flow by hand."

**What they actually mean** (one of four):
1. "The Flow redraws itself and moves what I was working on." — legitimate gripe; minimize by using Flow Zones.
2. "The Flow redraws without me asking." — same.
3. "The auto-layout doesn't match my mental model of 'tidy'." — use Flow Zones + anchoring; their 'tidy' is sequential, DSS 'tidy' is fewest-line-crossings.
4. "I want to throw tools on the canvas first and connect them second." — this is a workflow difference, not a gap. DSS builds piece-by-piece. Explain that this enforces working data + immediate validation, which is why recipe failures are caught at edit time rather than run time.

Don't promise drag-drop — it's a Product request, not a skill gap to work around.

---

## Insert / snip / reshape recipes in place

**User says:** "I want to drop a Prepare onto the wire between two existing recipes."

**Point them at:**
- **Insert Recipe** (recent DSS) — right-click a dataset → insert recipe. Creates the new recipe and reconnects downstream.
- To **remove** a recipe and reconnect the severed branches (snip): no visual path — manually rewire inputs.
- To **merge** two adjacent recipes: manual recreation.

---

## Getting files off the desktop

**User says:** "My inputs are Excel files on my laptop."

**What they need:** those files live in a shared, versioned source before migration can succeed.

**Point them at (in this order):**
1. **SharePoint Online** / **OneDrive** / **Google Drive** / **Google Sheets** / **Dropbox** / **Box** plugins — pick what the company uses.
2. Admin involvement to set up service accounts / OAuth.
3. Ideally: done before the first user onboards, not during their first project.

This is the single biggest first-day blocker. If the user can't get to their data, nothing else matters.

---

## "Build All" vs incremental builds

**User says:** "I hit Run, Alteryx runs the whole workflow. Why is DSS so complicated about what runs?"

**Point them at:**
- **Incremental build** — DSS builds only what's changed and downstream. Massive win on big flows.
- **Non-recursive / recursive / smart / forced / missing-data-only** build modes — walk them through the modal. Use job previews to see what'll run.
- **Build Zone** (recent DSS) — closest to Alteryx "build this container".
- **Build All Flow Action** — exists for peace of mind; discourage as the default (slow, expensive, defeats the point of DSS's incremental model).

---

## Reporting / Excel as final deliverable

**User says:** "I need to produce a multi-sheet Excel with conditional formatting and email it."

**First question:** *does it need to be Excel?* Often the answer is "the recipient expects Excel because that's what Alteryx produced." Explore:
- DSS dataset shared on a Workspace.
- DSS Dashboard with pivot tables and charts.
- Email reporter with a link to the DSS content.

If Excel really is required: **Multisheet Excel export** plugin + DSS conditional formatting (preserved on export). Template-based range writes / dynamic per-partition files require a private plugin — contact internal TAM.
