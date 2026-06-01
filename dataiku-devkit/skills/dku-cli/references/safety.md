# Safety Guards

`dku` is guarded by default. Destructive commands refuse to run until the user explicitly confirms the risk.

## Tiers

| Tier | Meaning | Confirmation |
|---|---|---|
| 1 — read/write | Non-destructive reads and reversible creates/updates | No guard |
| 2 — delete | Deletes or clears one named resource | `--yes` / `-y` |
| 3 — cascade | Can destroy or orphan multiple resources | `--yes` and `--confirm-name <TARGET>` |
| 4 — admin | Instance-wide destructive admin writes | `--yes`, `--confirm-name`, and lockout acknowledgement |

Exit code `77` is reserved for safety blocks.

## Agent Procedure

When a command exits 77:

1. Read the `AGENT INSTRUCTION:` block on stderr.
2. Ask the user the verbatim confirmation question from that block.
3. If the user confirms, copy the provided rerun command exactly.
4. Do not guess `--confirm-name`.

Root options such as `--errors json`, `--profile`, `--dangerous`, `--url`, and `--api-key` must appear before the noun. The safety block's rerun command preserves the correct position.

## Common Confirmations

```bash
# Tier 2
dku dataset delete DS -P PROJ --yes
dku recipe delete RECIPE -P PROJ --yes
dku knowledge delete KB -P PROJ --yes

# Tier 3
dku project delete PROJ --yes --confirm-name PROJ
dku plugin delete my-plugin --force --yes --confirm-name my-plugin
dku connection delete CONN --yes --confirm-name CONN
```

## Delete Side-Effects

`dku dataset delete` is tier 2 (one named resource), but deleting a dataset that is an INPUT to another recipe silently removes that recipe too — no cascade prompt. After a `dataset delete`, re-list recipes and recreate any that disappeared. Most common when prototyping Stack chains.

## Credential Exposure

DSS does not redact credentials at the API level, so several read commands return secrets in plain text. NEVER pipe their raw output to chat, a wiki, or git — strip first.

| Command | Leaks | Strip before sharing |
|---|---|---|
| `dataset get-definition` on a plugin connector (`type: CustomPython_<plugin>`) | raw PAT/token in `params.customConfig.<sa>.inlinedConfig` | `jq 'del(.params.customConfig)'` |
| `webapp get-definition` | top-level webapp-scoped `apiKey` (same scope the webapp calls DSS with) | `jq 'del(.apiKey, .config.apiKey)'` |
| `connection list -o json` | `params.password`, `aws_secret_access_key`, OAuth refresh tokens | `jq 'del(.params.customConfig)'`; for support, use the UI export (DSS redacts it) instead of API output |

## Dangerous Mode

`--dangerous`, `DKU_DANGEROUS=1`, and `dangerous_mode=true` bypass tier 2 and parts of tier 3 for a trusted session. Agents should only use dangerous mode when the user explicitly asks for it. Tier 4 admin guards are never bypassable.

## Admin Writes

Admin writes have separate lockout and instance-health risks. Read `admin-safety.md` before any `dku admin` command that mutates settings, IAM, license, infra, messaging, or user sync.
