<!--
Keep the PR small: one claim, one reviewable change. Fill every section; write
"n/a" with a reason rather than deleting one. Do not paste instance URLs,
project keys, credentials or customer names anywhere in this description.
-->

## Scope

- **Target branch:** `release/X.Y.Z` <!-- never main; see CONTRIBUTING.md -->
- **Issue / RFC:** #
- **Cobuild routing:** <!-- Does Cobuild already cover this? If the PR adds or widens a direct write tool, name the fixed exception in CODING_STANDARDS_AND_STRUCTURE.md that allows it. -->

## Claim

<!-- One sentence: what a user or agent can do after this PR that they could not before, or what was wrong and is now right. -->

## Change

<!-- What changed and why, in a few bullets. Name added, removed or renamed tools. -->

## Proof

<!-- How you know the claim holds. Unit tests alone do not prove behaviour against a real Dataiku instance. -->

- **Tests:** <!-- focused tests added or changed; each new regression test fails without the fix -->
- **Live verification:** <!-- verdict and checks in your own words, DSS version and node type only. No host, project key, object name, count or output from the instance. Or "not run" and why. -->
- **Not exercised:** <!-- anything the claim covers that was not run live, with the reason -->

## Risk

<!-- What could break for existing users, tool-description size impact, and how to roll back. -->

## Checklist

- [ ] Follows the **PR Checklist** in `CODING_STANDARDS_AND_STRUCTURE.md`
- [ ] Title is a Conventional Commit (`type(scope): subject`)
- [ ] One claim; split anything unrelated into its own PR
