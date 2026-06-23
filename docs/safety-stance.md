# Safety stance — confirmation flags vs harness authorization (Phase-2 proposal)

Status: **design note, not implemented.** Nothing in `safety.py` changes on the
strength of this doc. It tests our tiered `safety.guard` against a general
agent-safety principle and proposes where each boundary belongs.

## The principle

A bare confirmation boolean is not an authorization boundary for an agent caller:

> Treat user confirmation as a **harness concern** (user-confirmation mode vs
> yolo mode in the caller). A boolean confirmation flag (`confirm*`) on a tool
> API is not a reliable authorization boundary for an autonomous caller. Where
> possible, represent destructive intent through **semantic** operation
> parameters instead (`overwrite=true`, `drop_data=true`, `mode="replace"`,
> `job_type="RECURSIVE_FORCED_BUILD"`).

The load-bearing claim: a boolean `confirm` is trivially satisfiable by the model
itself. An agent that wants the operation to proceed will set `confirm=true`
without a human in the loop, because nothing about the flag encodes *who*
authorized it. The flag protects against accidental invocation, not against an
agent acting beyond its mandate. So a confirmation boolean on its own is theatre —
it looks like an authorization boundary and isn't one.

## How our design measures up

Our `safety.guard` tiers (`READ`/`WRITE` → `DELETE --yes` → `CASCADE --yes
+ --confirm-name` → `ADMIN --yes + --confirm-name + --i-know-what-im-doing`,
plus IAM `--i-understand-lockout-risk`) look, at a glance, exactly like the
"confirmation flags" the principle warns against. The reconciliation is that our
flags are doing two *different* jobs, and only one of them is the job the
principle critiques:

1. **Intent encoding (semantic).** `--confirm-name <TARGET>` is not a boolean.
   It requires the caller to reproduce a fact about the world — the exact name of
   the resource being destroyed. A model that hallucinated the wrong target
   cannot satisfy it; a fat-fingered project key fails closed. This is the same
   spirit as `drop_data=true` / `mode="replace"`: it makes destructive intent
   *specific and unrepresentable-when-wrong*, which is squarely our tenet "make
   the illegal unrepresentable, loudly." This part is sound and stays.

2. **Authorization (the part the principle targets).** `--yes` *is* a bare
   boolean, and an autonomous agent can set it as freely as it sets any other
   flag. On its own, `--yes` is exactly the theatre named above. What makes it
   more than theatre in our model is the **exit-77 handshake**: the guard does
   not silently proceed on a missing flag — it exits 77 and prints an
   `AGENT INSTRUCTION:` block with a verbatim confirmation question and an exact
   rerun command. The *protocol* (stop, surface the question to the human, rerun
   only the provided command) is what carries the authorization, not the boolean.

So the honest framing: **`--confirm-name` is good semantic intent-encoding;
`--yes` is a weak authorization signal that only becomes meaningful because of
the exit-77 / `AGENT INSTRUCTION:` contract with the harness.** The boolean alone
authorizes nothing.

## Where harness-level confirmation is the right boundary

Harness confirmation (the caller's user-confirmation vs yolo mode, gating tool
calls before they reach us) is the correct boundary when **the human's "yes" must
be fresh and out-of-band** — i.e. the model must not be able to manufacture it:

- **Tier 4 ADMIN and IAM writes.** A bad SSO/LDAP payload locks every user out
  with no in-band recovery. The decision to proceed must come from a human, not a
  flag the model can set. Our flags raise the cost (multiple acks, exact name,
  lockout ack) but cannot *prevent* an unattended agent from assembling them. A
  harness that requires a real human approval before the call leaves our process
  is strictly stronger here. This is where harness confirmation should be
  mandatory and non-bypassable, mirroring "Tier 4 is never bypassed by
  `--dangerous`."
- **CASCADE operations that orphan unnamed resources** (deleting a dataset that
  silently removes downstream recipes; `users-sync resync-all` mass-deactivation).
  The blast radius exceeds the named target, so the human approving needs context
  the flag can't convey.

## Where our flags are the right (or sufficient) boundary

Our in-band flags are the appropriate boundary when the operation is **scoped,
named, and reversible enough that fresh human approval is overkill** — and where
the value of running headless/unattended is real:

- **Tier 2 DELETE of one named, reproducible resource.** `--yes` plus the
  not-found-says-what-exists error path is enough friction. Requiring a harness
  round-trip on every single delete would make unattended pipelines unusable for
  little safety gain.
- **Anywhere intent is genuinely semantic already.** Where DSS exposes a
  semantic destructive parameter (recursive/forced build mode, replace/overwrite
  write mode, `drop_data`), prefer encoding intent in *that typed option* over
  bolting on a separate confirmation flag — this is the principle applied
  directly, and it matches our rule "no flags that default to the only
  reasonable value."

## Proposed Phase-2 changes (design only)

1. **Audit for bare-boolean `confirm*` flags and delete them.** Any guard whose
   only gate is a boolean the model can set, with no `--confirm-name` and no
   exit-77 handshake, is theatre. Replace with either (a) a semantic typed option
   that encodes the destructive intent, or (b) the full exit-77 + `AGENT
   INSTRUCTION:` contract. Do not keep a boolean that pretends to authorize.
2. **Make the exit-77 contract the single source of "authorization."** Document
   that `--yes` is an *acknowledgement token consumed by the exit-77 protocol*,
   never a standalone authorization. The authority lives in the harness relaying
   the verbatim question to a human and rerunning the exact command.
3. **Add a harness-confirmation hook point for Tier 3/4.** Expose, for callers
   that have a user-confirmation mode, a way to require fresh human approval
   before CASCADE/ADMIN calls execute — independent of (and in addition to) our
   flags. Yolo-mode callers still hit the exit-77 wall; confirmation-mode callers
   get a real human gate. Tier-4 remains non-bypassable in both.
4. **Keep `--confirm-name` exactly as is.** It is the part of the design the
   principle would endorse: specific, world-referencing, fail-closed intent.
