# Admin Safety — destructive ops & lockout prevention

Agents operating on `dku admin ...` can take the whole instance offline in
a single command. This reference enumerates every destructive verb, the
failure it can cause, and the safe-pattern that prevents it.

**Read this before ANY `dku admin` command that isn't `logs`, `get-log`,
`usage`, `instance-info`, `sanity-check`, or a `*-get` subcommand.**

---

## Hard rules

1. **`--yes` is never optional for admin writes.** The CLI dry-runs without
   it and prints the planned action. Use the dry-run to confirm target,
   payload, and side effects BEFORE re-running with `--yes`.
2. **IAM writes (`sso`, `ldap`, `azure-ad` `set`) require `--i-understand-lockout-risk`.**
   A bad SAML/OIDC/LDAP config locks EVERY user out of DSS — only a DSS admin
   with local filesystem access to `install.ini` can recover. Keep a second
   browser session open and verify login before closing your current one.
3. **`settings set` is a FULL replace, not a merge.** Always `get` first,
   edit the JSON, `set` the entire object. The CLI refuses to save if the
   payload is missing fields present in the live config.
4. **`license upload` has no rollback.** Wrong license edition can revoke
   user caps immediately. Keep the current license JSON on disk BEFORE
   uploading a new one.
5. **`users-sync resync-all` can deactivate users.** Any user removed from
   the external supplier (LDAP/Azure AD) is deactivated in DSS. Use
   `fetch-external-users` first to preview what the sync will see.

---

## Destructive verb → failure mode → safe pattern

| Verb | Worst failure | Safe pattern |
|---|---|---|
| `admin license upload` | Wrong edition → users can't log in; no rollback | GET `license status` → save response → `upload --yes` → verify with `status` |
| `admin sso set` | SAML misconfig → all SSO users locked out | `sso get -o json > /tmp/sso.json` → edit → `sso set -d @/tmp/sso.json --yes --i-understand-lockout-risk` → keep second session open |
| `admin ldap set` | Wrong bind DN/URL → LDAP users can't log in | Same as SSO. ALWAYS keep a local (non-LDAP) admin account as break-glass |
| `admin azure-ad set` | Wrong tenant/client → all Azure users locked out | Same as SSO |
| `admin settings set` | Bad impersonation rule → code envs/container-exec break for all projects | GET → diff intended change → SET with full payload |
| `admin infra push-base-images` | Broken registry creds → container-exec stops working for all projects | Run `sanity-check` first; verify registry creds in `settings get`; retryable |
| `admin infra apply-k8s-policies` | Misconfigured namespace → pods can't start across cluster | Read `settings get` K8s block first; apply during low-traffic window |
| `admin users-sync resync-all` | External source unreachable → mass user deactivation | `fetch-external-users --source LDAP` first to verify connectivity |
| `admin messaging create` | Wrong SMTP creds → scenario failure alerts stop firing | Use `admin messaging send-test` BEFORE deleting the old channel |
| `admin messaging delete` | Scenarios using the channel silently stop alerting | Grep scenario JSON for the channel id BEFORE delete; create replacement first |
| `admin llm-cost counters` | Read-only; configuration is UI-only | Use this to MONITOR quotas; configure caps in Admin → LLM Mesh → Cost limiting |
| `user bulk-create` | Password-in-plaintext in CSV if mishandled | Pipe CSV from a vault-rendered tempfile (`doppler run --`); delete file after; rotate passwords |
| `user bulk-edit` | Mass-disable (`enabled:false`) can lock everyone out | Limit the change set; always pass a minimal diff; verify with `dku user list` |
| `connection update` / `set-definition` | Wrong creds break EVERY dataset on the connection | `connection get` first; rotate one field; `connection test CONN -P PROJ` after |
| `api-key delete` | Revokes a key a scenario depends on → jobs start failing | Grep scenario definitions for the key label BEFORE delete |
| `connection delete` | Orphans every dataset using the connection | `dku connection get CONN -P PROJ -o json` → check `nbUsages` → migrate first |
| `plugin delete` / `plugin uninstall` | Breaks every recipe/webapp using the plugin | Check plugin usages via `project inspect` across projects |
| `user delete` / `user deactivate` | User-owned projects become un-editable if they were sole admin | Reassign ownership via `project set-permissions` first |
| `code-env delete` | Breaks every recipe/webapp using the env | `code-env usages ENV -o json` before delete |
| `cluster delete` | In-flight jobs lose their executor | Check `job list --state RUNNING` first; drain before delete |
| `codeenv update --force-rebuild` | Rebuild from scratch → blocks new runs on that env briefly | Safe, idempotent; queue the rebuild during low-traffic. Existing pods keep old env. |
| `codeenv jupyter --disable` | Notebooks using this env stop launching kernels | No effect on recipes/scenarios. Reversible with `--enable`. |
| `codeenv update-images` | New pods pull the rebuilt image; running pods keep the old one | Non-destructive; idempotent. Run after `set-packages` to propagate to container-exec. |
| `admin catalog-index` | Indexing job consumes connection capacity | Idempotent; pick `--mode INCREMENTAL` for large connections. |
| `admin audit-log` | Writes a self-scoped audit entry | Non-destructive — purely additive. Use for CI/CD deploy markers. |
| `admin disk-footprint all` | Walks the full data dir; can take minutes on large instances | Read-only. Run at night or use `global`/`project` subcommands. |

---

## Pre-flight checks (run BEFORE any admin write)

```bash
# 1. Snapshot current state so you can diff / rollback
mkdir -p /tmp/dss-admin-snapshot
dku admin settings get > /tmp/dss-admin-snapshot/settings.json
dku admin sso get -o json > /tmp/dss-admin-snapshot/sso.json
dku admin ldap get -o json > /tmp/dss-admin-snapshot/ldap.json
dku admin license status -o json > /tmp/dss-admin-snapshot/license.json

# 2. Verify health BEFORE changes
dku admin sanity-check

# 3. For IAM changes — confirm a second admin session is active
dku --profile break-glass whoami
```

---

## IAM edit loop (SSO / LDAP / Azure AD)

```bash
# 1. GET current settings
dku admin sso get -o json > /tmp/sso.json

# 2. Edit /tmp/sso.json — make the SMALLEST possible change (one field)
# 3. DRY RUN (no --yes): prints what WOULD happen
dku admin sso set -d @/tmp/sso.json

# 4. Open a second browser session. Log in. KEEP IT OPEN.

# 5. Apply
dku admin sso set -d @/tmp/sso.json --yes --i-understand-lockout-risk

# 6. IMMEDIATELY open a new incognito window and verify SSO login
#    If it fails: use the session from step 4 to revert.
```

---

## Recovery when you've locked yourself out

If IAM config breaks authentication:

1. **SSH to the DSS host**
2. `cd $DATA_DIR/config && cp general.json general.json.bak`
3. Edit `general.json` — restore the prior `ssoSettings` / `ldapSettings` block
4. `dss restart backend`
5. Verify login

If you lose the local-admin break-glass account, Dataiku support is the only path.

---

## Agent checklist (copy into any admin workflow)

- [ ] Snapshot taken? (`/tmp/dss-admin-snapshot/`)
- [ ] Sanity check clean? (`dku admin sanity-check`)
- [ ] Break-glass session open in a second browser?
- [ ] Smallest possible diff?
- [ ] Dry-run output reviewed?
- [ ] `--yes` (+ `--i-understand-lockout-risk` for IAM) explicitly in the command?
- [ ] Post-change verification planned? (`license status`, login test, `sanity-check`)
