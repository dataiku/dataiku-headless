# Reference: Safety

`dku` is guarded by default. Destructive commands refuse to run until the user
explicitly confirms. This is the canonical safety reference; exact flags come
from `--help`.

## Tier model

| Tier | Command... | Required confirmation |
|---|---|---|
| `READ` / `WRITE` | Lists, reads, or makes a reversible create/update | none |
| `DELETE` | Deletes or clears one named resource | `--yes` / `-y` |
| `CASCADE` | Irreversible, or can destroy/orphan resources the user did not name | `--yes` + `--confirm-name <TARGET>` |
| `ADMIN` | Mutates instance-wide admin config | `--yes` + `--confirm-name <id>` + `--i-know-what-im-doing`; IAM writes (`sso`/`ldap`/`azure-ad set`) additionally require `--i-understand-lockout-risk` |

`--confirm-name` must match the target resource exactly. Never guess it.

## Exit code 77 — the agent instruction

Exit code `77` is reserved for safety blocks (do not reuse it). When a command
exits 77 it prints an `AGENT INSTRUCTION:` block on stderr with a verbatim
confirmation question and an exact rerun command.

**Agent procedure on exit 77:**

1. Read the `AGENT INSTRUCTION:` block on stderr.
2. Ask the user the verbatim confirmation question from that block.
3. If the user confirms, copy the provided rerun command **exactly**.
4. Do not guess `--confirm-name`; do not re-run without asking.

Global options (`--format json`, `--profile`, `--dangerous`, `--url`,
`--api-key`) must appear **before the noun**. The rerun command in the block
already preserves correct flag position.

## Dangerous mode

`--dangerous`, `DKU_DANGEROUS=1`, and `dangerous_mode=true` bypass tier 2 and
parts of tier 3 for a trusted session. Use dangerous mode only when the user
explicitly asks for it. **Tier 4 ADMIN guards are never bypassable.**

## Delete side-effects (no cascade prompt)

`dataset delete` is tier 2 (one named resource) but deleting a dataset that is
an INPUT to another recipe **silently removes that recipe too** — no cascade
prompt. After a `dataset delete`, re-list recipes and recreate any that
disappeared. Most common in Stack-chain prototyping.

## Credential exposure (strip before sharing)

DSS does not redact credentials at the API level. Several read commands return
secrets in plain text. NEVER pipe their raw output to chat, a wiki, or git.

| Command | Leaks | Strip with |
|---|---|---|
| `dataset get-definition` on a plugin connector (`type: CustomPython_<plugin>`) | raw PAT/token in `params.customConfig.<sa>.inlinedConfig` | `jq 'del(.params.customConfig)'` |
| `webapp get-definition` | top-level webapp-scoped `apiKey` | `jq 'del(.apiKey, .config.apiKey)'` |
| `dku --format json connection list` | `params.password`, `aws_secret_access_key`, OAuth refresh tokens | `jq 'del(.params.customConfig)'`; for support, use the UI export (DSS redacts) |

---

# Admin lockout risks

A single `dku admin` write can take the whole instance offline. **Read this
before any `dku admin` write** (anything that isn't `logs`, `get-log`, `usage`,
`instance-info`, `sanity-check`, or a `*-get`/`*-status` read).

## Hard rules

1. **Admin writes are blocked, not dry-run, until fully authorized.** Missing a
   required flag exits `77` with an `AGENT INSTRUCTION:` block and an exact rerun
   command — it does NOT preview-and-continue. `license upload`, `settings set`,
   and the IAM `set` verbs are tier-4 ADMIN (`--yes` + `--confirm-name <id>` +
   `--i-know-what-im-doing`) and are NOT bypassable by `--dangerous`.
2. **IAM writes (`sso`/`ldap`/`azure-ad` `set`) require a lockout ack on top of
   tier-4.** Add `--i-understand-lockout-risk`. A bad SAML/OIDC/LDAP config locks
   EVERY user out — only a DSS admin with local filesystem access to `install.ini`
   can recover. Keep a second authenticated session open and verify login before
   closing your current one.
3. **`settings set` is a FULL replace, not a merge.** Always `get` first, edit
   the JSON, `set` the entire object.
4. **`license upload` has no rollback.** Wrong edition can revoke user caps
   immediately. Save the current license JSON to disk first.
5. **`users-sync resync-all` can mass-deactivate users.** Tier-3 CASCADE
   (`--yes` + `--confirm-name resync-all`). Anyone removed from the external
   supplier is deactivated. Run `fetch-external-users` first to preview.

## Destructive verb → worst failure → safe pattern

| Verb | Worst failure | Safe pattern |
|---|---|---|
| `license upload` | No-login; no rollback | `dku --format json admin license status` → save → `upload --yes --confirm-name license --i-know-what-im-doing` → verify `status` |
| `sso`/`ldap`/`azure-ad set` | All SSO/LDAP/Azure users locked out | GET → smallest one-field edit → keep 2nd session open → `set --yes --confirm-name <sso\|ldap\|azure-ad> --i-know-what-im-doing --i-understand-lockout-risk` → verify login in incognito |
| `settings set` | Bad impersonation rule breaks code envs/container-exec project-wide | GET → diff intended change → SET full payload with `--yes --confirm-name general-settings --i-know-what-im-doing` |
| `infra push-base-images` / `apply-k8s-policies` | Broken registry/namespace stops container-exec / pods | `sanity-check` + verify creds first; apply in low-traffic window; retryable |
| `users-sync resync-all` | External source unreachable → mass deactivation | `fetch-external-users --source LDAP` first |
| `messaging create`/`delete` | Wrong/removed SMTP channel silently stops scenario alerts | `messaging send-test` before delete; create replacement first; grep scenario JSON for channel id |
| `connection update`/`delete` | Wrong creds or orphan break every dataset on the connection | `connection get` (check `nbUsages`) → rotate one field → `connection test` after; migrate before delete |
| `api-key delete` | Revokes a key a scenario depends on | grep scenario defs for the key label first |
| `plugin delete`/`uninstall` | Breaks every recipe/webapp using it | check usages via `project inspect` across projects |
| `user delete`/`deactivate` | Sole-admin's projects become un-editable | reassign ownership via `project set-permissions` first |
| `code-env delete` | Breaks every recipe/webapp using the env | `dku --format json code-env usages ENV` first |
| `cluster delete` | In-flight jobs lose executor | check `job list --state RUNNING`; drain first |

Non-destructive/idempotent admin verbs (safe, reversible): `codeenv update
--force-rebuild`, `codeenv jupyter --disable/--enable`, `codeenv
update-images`, `catalog-index` (prefer `--mode INCREMENTAL`), `audit-log`
(additive), `disk-footprint` (read-only, slow on large instances).

## Pre-flight (before any admin write)

1. Snapshot current state to disk (`settings get`, `sso get`, `ldap get`,
   `license status`) so you can diff/rollback.
2. `dku admin sanity-check` — verify health is clean first.
3. For IAM changes: confirm a second admin session is active
   (`dku --profile break-glass whoami`), keep a local (non-IAM) break-glass
   admin account.

## IAM edit loop (SSO / LDAP / Azure AD)

GET current settings → make the SMALLEST possible change (one field) → open and
keep a second logged-in session → apply with `--yes --confirm-name <sso|ldap|azure-ad>
--i-know-what-im-doing --i-understand-lockout-risk` → immediately verify login in a
new incognito window; revert from the second session if it fails.

## Recovery from lockout

If IAM config breaks auth: SSH to the DSS host → `cd $DATA_DIR/config` →
restore the prior `ssoSettings` / `ldapSettings` block in `general.json`
(keep a `.bak`) → `dss restart backend` → verify login. If the break-glass
local admin is also lost, Dataiku support is the only path.
