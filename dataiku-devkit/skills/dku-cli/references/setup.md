# Setup & Configuration

## Authentication

### Interactive Login

```bash
dku auth login
```

Prompts for DSS URL and API key. Stores credentials in system keyring (macOS Keychain, Linux Secret Service, Windows Credential Locker) with file fallback.

### Non-Interactive / CI

```bash
dku auth login --url https://dss.example.com --api-key YOUR_KEY --profile prod
```

### Environment Variables (CI/CD)

```bash
export DKU_URL=https://dss.example.com
export DKU_API_KEY=your-api-key
export DKU_PROJECT=MY_PROJECT
```

Environment variables override saved profiles. Useful for CI/CD pipelines where keyring isn't available.

### Managing Profiles

```bash
dku auth list          # Show all saved profiles
dku auth status        # Show active profile + connection status
dku auth switch prod   # Switch active profile
dku auth logout        # Remove current profile credentials
```

## Error Output Format

Use `--errors json` when the failure path also needs to be machine-readable. Do not merge stderr into stdout before `jq`; parse stdout on success, stderr on failure.

```bash
dku --errors json recipe get missing_recipe -P PROJ -o json
```

Prefer `dku ... -o json | jq ...` on success paths. Avoid `2>&1 | jq` — stderr has error payloads, not success objects.

```bash
# Success path: parse stdout only
dku recipe get my_recipe -P PROJ -o json | jq '.type'

# Failure path: request machine-readable stderr
if ! dku --errors json recipe get missing_recipe -P PROJ -o json >out.json 2>err.json; then
  jq '.error.code, .error.message' err.json
fi
```

## JSON Input Patterns

Creation/mutation commands accept `--definition JSON`:
- Literal JSON string: `--definition '{"key": "value"}'`
- From file: `--definition @config.json`
- From stdin: `--definition -`

Code commands accept `--code` with the same patterns: literal string, `@file.py`, or `-` for stdin (heredoc-friendly).
