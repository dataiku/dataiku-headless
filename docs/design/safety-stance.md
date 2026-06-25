# Safety stance — confirmation flags vs harness authorization (Phase-2 proposal)

Status: **design note, not implemented.** Nothing in `safety.py` changes on the
strength of this doc. It tests our tiered `safety.guard` against a general
agent-safety principle and proposes where each boundary belongs.

> **Decision (2026-06):** the guard is a deliberate **speed bump for the agent**, not an
> authorization wall, and we are **not** pursuing harness-level hooks (supersedes proposal #3
> below). Under Claude Code the guard stacks on the harness's own permission layer: it is
> largely redundant when `dku` is unallowlisted (Claude Code already prompts before running
> the command), and earns its keep when `Bash(dku:*)` is allowlisted or the run is headless,
> where exit-77 is the only checkpoint that surfaces a destructive call. `--dangerous` /
> `DKU_DANGEROUS` stays an explicit opt-in; tier-4 ADMIN is never bypassable by it.

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
3. ~~**Add a harness-confirmation hook point for Tier 3/4.**~~ **Declined (2026-06).**
   We deliberately keep the guard a CLI-only speed bump and do not add harness hooks: a
   hook would turn the speed bump into a wall (not the intent) and create a second source
   of truth for the tier map. See the decision note at the top. `--dangerous` /
   `DKU_DANGEROUS` is kept as a deliberate, explicit opt-in.
4. **Keep `--confirm-name` exactly as is.** It is the part of the design the
   principle would endorse: specific, world-referencing, fail-closed intent.

## MCP threat model

### Trust modes

The MCP server (`dku-mcp serve`) operates in two trust modes:

| Mode | Transport | Env | Sandbox | Use case |
|---|---|---|---|---|
| `local` | stdio only | Full host env, no scrubbing | Optional | Local agent, same user |
| `hosted` | http | Scrubbed (only DKU_URL/DKU_TICKET), per-session workdir | Bubblewrap required | Remote/multi-tenant |

Local mode inherits the caller's full environment (including `DKU_DANGEROUS`,
`PATH`, `HOME`). Hosted mode is locked down: it sets `HOME` to the per-session
workdir, does not pass `DKU_DANGEROUS`, and refuses to run without bubblewrap
unless `--allow-insecure-sandbox` is explicitly passed.

The server refuses `--trust local` on an HTTP transport because local-mode
environment inheritance (full `PATH`, home dir, config files) is inappropriate
for a network-reachable endpoint.

### Identity — bearer vs pod key

The server distinguishes two identity modes via the `is_http` flag, resolved
at the server level — never inferred from a request context's availability (a
hosted HTTP server can never silently fall back to the pod's own credential):

- **HTTP (bearer):** The `Authorization: Bearer` token IS the caller's DSS
  personal API key. Every `dku` command runs as that user. The pod's injected
  key (`DKU_API_KEY` / `DKU_API_TICKET`) is NEVER used for HTTP callers.
  Sessions are keyed off the bearer token for per-caller isolation. If no
  bearer can be extracted, an empty key is returned so `dku_exec` produces the
  auth-required error rather than running as the pod owner.
- **stdio (pod owner):** The agent runs as the pod user, authenticated via
  `DKU_API_KEY` or `DKU_API_TICKET`.

**X-API-Key fallback headers:** Some reverse proxies strip the `Authorization`
header. The HTTP server additionally checks `X-DKU-API-Key` and `X-API-Key`
headers as a fallback, so bearer-based identity (model A) works through such
proxies. These headers are NOT a separate auth mechanism — they follow the same
bearer-identity rules.

### Sandbox isolation

The executor sandbox selects a backend (`SandboxBackend`) at startup:

- **Bubblewrap** (`BubblewrapBackend`): Full kernel-level isolation via
  unprivileged user namespaces. The jail exposes only:
  - **Read-only:** `/bin`, `/sbin`, `/usr`, `/lib*`, `/etc/ssl`, `/etc/pki`,
    `/etc/ca-certificates`, `/etc/resolv.conf`, `/etc/hosts`, `/etc/nsswitch.conf`,
    `/etc/passwd`, `/etc/group` — runtime/cert/DNS files, not user data.
  - **Writable:** The per-session workdir (bound after the tmpfs so it stays
    writable when sessions live under `/tmp`).
  - **Temp:** An isolated `tmpfs` at `/tmp` (NOT the host `/tmp`).
  - **Network:** On by default (DSS reachability); gated by `--no-network`.
  - **PIDs/IPC:** `--unshare-pid`, `--unshare-ipc`, `--unshare-uts`.
- **Subprocess** (`SubprocessBackend`): No isolation beyond cwd/env change.
  Intended only for local dev where the agent and DSS run on the same machine.

**Bubblewrap probe:** `probe_bubblewrap()` checks not just that the `bwrap`
binary exists but that creating an unprivileged user namespace actually works
in this environment — hardened K8s clusters may block it even when the binary
is present.

**`--allow-insecure-sandbox`:** The HTTP server refuses to start when the
selected backend is not bubblewrap, unless this flag is passed. This is a
deliberate safety gate: serving to remote agents without kernel isolation is
unsafe. The doctor command (`dku-mcp doctor`) reports the active backend and
warns when it is not bubblewrap.

### File-system boundaries

| Boundary | Local (stdio) | Hosted (HTTP) |
|---|---|---|
| HOME | User's home dir | Per-session workdir |
| CWD | Client's cwd | Per-session workdir |
| TMPDIR | Inherited | `/tmp` (isolated tmpfs in bubblewrap) |
| Host filesystem | Full access | Bubblewrap jail (runtime paths only) |
| DSS config | `~/.config/dku/` | NOT mounted (auth via bearer only) |

The per-session state directory is `{state_root}/{session_id}/`. It is created
once per unique bearer (or once for the pod owner on stdio), and cleaned up when
the session expires.

### Audit trail

All `dku_exec` calls are logged with: caller session id, command (sanitised
of credential-bearing env vars), exit code, duration, and backend name. The
log line goes to stderr in the MCP server process; in a Code Studio this is
visible in the pod's console logs.

### In-pod TLS

When running inside a DSS Code Studio exposed port, TLS termination happens
at the Code Studio reverse proxy. The `dku` CLI connects to its DSS instance
*through the pod's internal network* using the pod ticket
(`DKU_API_TICKET`), which is a local loopback credential. The ticket is never
exposed to HTTP callers — they authenticate via their own bearer.

The bubblewrap jail mounts `/etc/ssl`, `/etc/pki`, and `/etc/ca-certificates`
so that SSL connections (e.g. `dku` → DSS API) work inside the sandbox.

## One-line summary

Confirmation *booleans* don't authorize agents — our `--confirm-name` already
encodes intent semantically (keep it), `--yes` only means something inside the
exit-77 handshake (document it as such), and for Tier 3/4 the right long-term
boundary is fresh harness-level human approval, not any flag the model can set.
