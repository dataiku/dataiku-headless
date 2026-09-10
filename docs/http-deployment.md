# Streamable HTTP deployment

Streamable HTTP runs Dataiku Headless as a centrally managed service, rather than
as a local process on each user's computer. An infrastructure administrator deploys
the MCP server on a host that users can reach, exposes it through HTTPS, and gives
it network access to one or more Dataiku instances.

The administrator also configures OAuth and a catalog of those Dataiku instances.
Authenticated users can select an instance from the catalog, but cannot add or
delete entries. The MCP server does not store Dataiku API keys: it exchanges each
user's MCP access token for a short-lived token that Dataiku accepts.

Clients can authenticate to the MCP server in two ways:

- **Interactive login:** the server redirects the user to the identity provider and
  handles the callback. This is the usual mode for interactive agent harnesses such
  as Codex and Claude.
- **Direct bearer token:** the calling application obtains an MCP access token and
  sends it with each request. This is useful for custom applications that manage
  OAuth themselves.

Both modes produce the same kind of MCP access token and use the same downstream
token exchange.

| | Stdio | Streamable HTTP |
| --- | --- | --- |
| Deployment | Local process started by a plugin | Shared remote service |
| MCP authentication | Local process boundary | OAuth access token |
| Dataiku authentication | API key | Exchanged user access token |
| Active instance | Process-wide | Selected per authenticated user |

## How a request reaches Dataiku

An access token's **audience** identifies the service allowed to accept it. Its
**scope** describes the access granted to the caller. The token sent to the MCP
server therefore cannot be sent directly to Dataiku: it has the wrong audience.

For each Dataiku-backed tool call:

1. The client obtains an MCP-audience access token, interactively or directly, and
   sends it to the MCP server.
2. The MCP server verifies its signature, issuer, audience, required scope, and
   expiry.
3. The server identifies the user and resolves the Dataiku instance they selected.
4. It asks the identity provider to exchange the MCP token for a **delegated token**
   whose audience and scope match that Dataiku instance.
5. Dataiku verifies the delegated token, maps its subject to a Dataiku user, and
   applies that user's normal Dataiku permissions.

## Deploy the server

Before starting, prepare:

- a server with DNS and HTTPS, either directly or through a reverse proxy;
- network access from that server to every configured Dataiku URL;
- the identity-provider configuration for one of the supported exchange modes; and
- administrator access to configure JWT authentication on each Dataiku instance.

If using a reverse proxy, forward the original scheme and host. Route the whole
public origin to the MCP server: OAuth metadata, login, callback, consent, and token
endpoints are served outside the configured MCP path.

Choose the matching example, then restrict the settings file because it contains
OAuth client secrets:

```bash
mkdir -p ~/.dataiku
cp .dataiku/http-config.json.entra-example ~/.dataiku/http-config.json
chmod 600 ~/.dataiku/http-config.json
uv run --quiet --locked --script runtime/run_mcp.py --transport http
```

For RFC 8693, copy `.dataiku/http-config.json.generic_oidc-example` instead. The
default destination is `~/.dataiku/http-config.json`; use `--settings-path PATH` to
choose another file.

The settings file has four sections:

- `server` controls the listening address, MCP path, and externally visible URL.
- `auth` configures incoming-token verification, optional interactive login, and
  token exchange.
- `dss_instances` lists the Dataiku endpoints users may select and the audience or
  scope requested for each one.
- `user_selections` records each authenticated user's current instance. Start with
  an empty object; the server manages it.

Authentication, transport, and instance settings are loaded at startup, so restart
the server after changing them. User selections are updated in memory and persisted
as users call `switch_instance`. This file-backed selection state supports one
server process.

The instance catalog is not an authorization list: any authenticated user can
select an entry, and Dataiku decides what that user may do. `configure_instance` and
`delete_instance` are therefore disabled in HTTP mode.

## Distribute the connection to end users

The public `dataiku-headless` marketplace plugin provides the Dataiku tools and
skills through a personal stdio connection. It must not be installed for this
mode because it would launch a second MCP server on the workstation using uv and
a personal API key.

For HTTP, generate a customer-specific marketplace bundle after configuring the
server:

```bash
uv run python scripts/build_http_plugin.py \
  --http-config .dataiku/http-config.json \
  --output ./dataiku-headless-http-marketplace
```

When `--http-config` is used, the generator verifies that
`auth.interactive_login` is enabled, then reads `server.public_url` and
`server.path`. Administrators who have already verified the deployment can instead
pass `--interactive-oauth-url https://mcp.customer.example/mcp`. The bundle is not
for direct bearer authentication.

The generated private-marketplace repository contains a portable plugin, a
Claude-compatible plugin, the fixed Streamable HTTP endpoint, and the shared
Dataiku skills. It does not copy the HTTP configuration, OAuth secrets, or Dataiku
credentials. The output path must not already exist.

Publish the generated directory to a private GitHub repository, then distribute
it according to the client surface:

- **ChatGPT desktop and the Codex app:** a ChatGPT workspace administrator
  [imports the repository from Admin > Plugins](https://learn.chatgpt.com/docs/enterprise/plugin-management),
  then makes the plugin Available or Installed for the appropriate roles.
  Workspace-imported plugins containing MCP servers are desktop-only.
- **Codex CLI:** an administrator adds the marketplace through managed or system
  configuration. Users install **Dataiku Headless** from the
  [`/plugins` browser](https://learn.chatgpt.com/docs/plugins), or receive it
  automatically.
- **Codex IDE extension:** plugins are not available. Distribute the shared MCP
  configuration and skills separately as described below.
- **Claude Code and Claude Desktop:** a Claude administrator registers the
  repository as a managed marketplace and enables the plugin.

On supported plugin surfaces, users select **Dataiku Headless**—or receive it
automatically—and complete interactive browser authentication. They do not need
uv, a Dataiku API key, or the MCP URL.

Keep exactly one Dataiku MCP definition enabled in each client. Disable the public
marketplace plugin before distributing the customer-specific remote plugin.

### Managed or configuration-only distribution

Use this path for direct bearer deployments, the Codex IDE extension, or any
environment where the organization cannot distribute a plugin. Install the shared
skills and distribute a server named `dataiku` through managed Codex, Claude Code,
or workstation configuration. Codex clients can
[share MCP configuration](https://learn.chatgpt.com/docs/extend/mcp) where their
administrator-managed setup supports it, but the skills must also be made available
to clients without plugin support. The server URL is the externally visible
`server.public_url` followed by `server.path`, for example
`https://mcp.customer.example/mcp`.

For interactive OAuth, clients discover the server's OAuth metadata and store each
user's login. For direct bearer authentication, the managed client or calling
application must obtain a correctly scoped access token and attach it to every MCP
request. Do not put OAuth client secrets, bearer tokens, or Dataiku credentials in
plugin files or source repositories.

Users whose clients are not centrally managed can install the skills with
`npx skills add dataiku/dataiku-headless`, then use the following commands with
the exact MCP URL supplied by the administrator. Codex supports Streamable HTTP
and interactive OAuth:

```bash
codex mcp add dataiku --url https://mcp.customer.example/mcp
codex mcp login dataiku
```

Claude Code uses the equivalent HTTP registration and login:

```bash
claude mcp add --scope user --transport http dataiku https://mcp.customer.example/mcp
claude mcp login dataiku
```

If `dataiku` already exists, inspect that definition rather than adding another
one. Users receiving a managed definition skip `mcp add` and authenticate the
existing server through their client's MCP panel or login command.

After authentication, the end-user workflow is:

1. Ask the agent to **Set up Dataiku Headless**.
2. The setup skill calls `list_instances`; the user chooses from the
   administrator-managed catalog.
3. The skill calls `switch_instance`, then `get_current_instance` and
   `list_projects` to verify delegated Dataiku access.
4. The user begins normal Dataiku work. Their existing Dataiku permissions govern
   every operation.

The user's workstation needs neither uv nor a Dataiku API key. Browser login,
token storage, and refresh belong to the MCP client; incoming-token validation
and downstream Dataiku token exchange belong to the deployed server.

## Host-local file operations

Streamable HTTP does not expose reads from or writes to caller-supplied paths on the
MCP host. In HTTP mode, `export_dataset`, `upload_file_to_managed_folder`,
`write_project_library_file`, and `update_plugin` are unavailable. To create an
Uploaded Files dataset, pass `columns` and `rows` directly to
`create_upload_dataset`; this route accepts at most 10,000 rows. Stdio retains the
local-path workflows for a process running on the user's machine.

### Interactive login or direct bearer token

With interactive login, set `server.public_url` to the externally visible HTTPS
base URL and register `<public_url>/auth/callback` with the identity provider. The
`auth.interactive_login` setting enables the browser-based login flow.

With direct bearer authentication, the calling application is responsible for
obtaining a correctly scoped MCP token and sending it with every request. Remove
`auth.interactive_login`; `server.public_url` is then optional. The remaining token
exchange settings are still required for Dataiku-backed tools.

## Microsoft Entra ID

The Entra mode supports public-cloud, single-tenant v2 user tokens and the OAuth
on-behalf-of (OBO) flow. It does not support application-only tokens.

The examples use these values:

- `<tenant-id>`: the Directory (tenant) ID.
- `<mcp-app-client-id>`: the Application (client) ID of the MCP registration.
- `<dataiku-app-client-id>`: the Application (client) ID of a Dataiku API registration.
- `<public-url>`: the HTTPS base URL of the deployed MCP server.

Two app registrations are required. The **MCP registration** represents the API
that clients call and acts as the confidential client during OBO. The **Dataiku API
registration** represents the downstream resource for which Entra issues the
delegated token. The current MCP server authenticates with a client secret;
certificate credentials are not yet supported.

Both registrations must request v2 access tokens. The MCP registration controls
the token accepted by the MCP server; the Dataiku API registration controls the
delegated token accepted by Dataiku.

### 1. Register the Dataiku API

In **Microsoft Entra admin center → App registrations**:

1. Create a single-tenant registration for the Dataiku instance. This resource
   registration needs no redirect URI or credential.
2. Under **Expose an API**, accept the default Application ID URI
   `api://<dataiku-app-client-id>` and add an enabled delegated scope named
   `dataiku.access`.
3. In this Dataiku API registration's Microsoft Graph app manifest, set
   `api.requestedAccessTokenVersion` to `2`. Access-token format is controlled by
   the target resource registration, not by the token endpoint: leaving this
   value unset or setting it to `1` makes Entra issue a v1 token even when the MCP
   server uses the v2 OBO endpoint.
4. Record the client ID and the full scope
   `api://<dataiku-app-client-id>/dataiku.access`.

Use a separate registration for each Dataiku instance that needs a distinct token
audience.

### 2. Register the MCP server

1. Create a single-tenant registration for the MCP server.
2. Under **Expose an API**, accept `api://<mcp-app-client-id>` and add an enabled
   delegated scope named `mcp.access`. Clients request this scope when calling the
   MCP server.
3. Set `api.requestedAccessTokenVersion` to `2` in this MCP registration's
   Microsoft Graph app manifest so clients receive a v2 token for the MCP server.
4. Under **Authentication**, add `<public-url>/auth/callback` as a **Web** redirect
   URI.
5. Under **Certificates & secrets**, create a client secret and store its value
   securely for the MCP settings file.
6. Under **API permissions → Add a permission → My APIs**, select each Dataiku API and
   add its delegated `dataiku.access` permission. This permits the MCP application to
   request a Dataiku token on behalf of the signed-in user.
7. Grant administrator consent for the tenant.

See Microsoft's guidance for [exposing API scopes](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-configure-app-expose-web-apis),
[granting a client access to an API](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-configure-app-access-web-apis),
[access-token versions](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens),
and the [OBO flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow).

### 3. Configure the MCP server

```json
{
  "server": {
    "host": "127.0.0.1",
    "port": 8000,
    "path": "/mcp",
    "public_url": "https://mcp.example"
  },
  "auth": {
    "provider": "entra",
    "tenant_id": "replace-with-tenant-id",
    "client_id": "replace-with-mcp-app-client-id",
    "client_secret": "replace-with-secret",
    "required_scope": "mcp.access",
    "interactive_login": true
  },
  "dss_instances": {
    "prod": {
      "url": "https://dataiku.example",
      "delegated_scope": "api://replace-with-dataiku-app-client-id/dataiku.access"
    }
  },
  "user_selections": {}
}
```

`tenant_id` identifies the Entra tenant. `client_id` and `client_secret` come from
the MCP registration. For each Dataiku instance, `delegated_scope` is the full scope
exposed by its Dataiku API registration. Do not add `delegated_audience`: Entra derives
the downstream resource from this scope.

The server derives the tenant-specific v2 issuer, JWKS URI, token endpoint, and
incoming audience. A valid incoming token has the MCP client ID as `aud` and
`mcp.access` in `scp`; the exchanged token has the Dataiku client ID as `aud` and
`dataiku.access` in `scp`.

For direct bearer mode, remove `interactive_login` and optionally `public_url`.
The client ID and secret remain required because the server still performs OBO.

## Generic OIDC and RFC 8693

Generic mode separates two concerns. First, the MCP server verifies an incoming
OIDC access token. It may obtain that token through interactive login, or the caller
may supply it directly. Second, a confidential exchange client trades that token
for one that Dataiku accepts.

The authorization server must:

- issue signed OIDC access JWTs and publish JWKS;
- support an OIDC web client when interactive login is enabled;
- accept an access token through [RFC 8693 token exchange](https://www.rfc-editor.org/rfc/rfc8693.html);
- authenticate the exchange client with HTTP Basic client ID and secret; and
- return an access token whose issuer, audience, scope, and subject Dataiku trusts.

The interactive and exchange clients may be separate registrations. Their exact
setup, trust, and consent requirements depend on the authorization server.

```json
{
  "server": {
    "host": "127.0.0.1",
    "port": 8000,
    "path": "/mcp",
    "public_url": "https://mcp.example"
  },
  "auth": {
    "provider": "generic_oidc",
    "issuer": "https://idp.example/oauth2/mcp",
    "jwks_uri": "https://idp.example/oauth2/mcp/keys",
    "required_audience": "dataiku-mcp",
    "required_scope": "mcp.access",
    "interactive_login": {
      "client_id": "dataiku-mcp",
      "client_secret": "replace-with-secret"
    },
    "delegation": {
      "token_endpoint": "https://idp.example/oauth2/token",
      "client_id": "dataiku-mcp-exchange",
      "client_secret": "replace-with-exchange-secret"
    }
  },
  "dss_instances": {
    "prod": {
      "url": "https://dataiku.example",
      "delegated_audience": "dataiku-prod",
      "delegated_scope": "dataiku.api"
    }
  },
  "user_selections": {}
}
```

`issuer`, `jwks_uri`, `required_audience`, and `required_scope` describe the token
accepted by the MCP server. `delegation` identifies the token endpoint and the
confidential client allowed to exchange it. Each Dataiku instance supplies the
`delegated_audience` and `delegated_scope` requested for its resulting token. One
settings file uses one exchange endpoint and client for all instances.

For direct bearer mode, remove `interactive_login` and optionally `public_url`.
`delegation` remains required for Dataiku-backed tools.

## Configure Dataiku to trust delegated JWTs

This step is required for both exchange modes. Dataiku validates the delegated token
returned by the identity provider—not the original token sent to the MCP server.
Configure each Dataiku instance with values taken from that delegated token:

| Dataiku setting | Purpose |
| --- | --- |
| Issuer | Must exactly match the token's `iss` claim |
| JWKS URI | Supplies the public keys used to verify its signature |
| Audience | Must match the token's `aud` claim |
| Scope | Permission Dataiku requires from the token |
| Scope claim key and format | Identifies whether the scope claim is a string or array |
| Subject match | Chooses the Dataiku user field compared with the token's `sub` |

Current Dataiku releases configure these values through general settings. A forthcoming
Dataiku release will expose the equivalent settings in the administration UI. Until
then, run the following from a Dataiku Python environment as a Dataiku administrator.
It replaces the existing global JWT settings, so record the previous value first.

```python
import dataiku

TENANT_ID = "replace-with-tenant-id"
DATAIKU_APP_CLIENT_ID = "replace-with-dataiku-app-client-id"
ENTRA_ISSUER = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"

admin = dataiku.api_client()
settings = admin.get_general_settings()
raw = settings.get_raw()

print("Previous JWT settings:", raw.get("jwtAuthSettings"))

raw["jwtAuthSettings"] = {
    "enabled": True,
    "issuer": ENTRA_ISSUER,
    "keysFormat": "JWKS_URI",
    "jwksUri": (
        f"https://login.microsoftonline.com/{TENANT_ID}"
        "/discovery/v2.0/keys"
    ),
    "audience": DATAIKU_APP_CLIENT_ID,
    "scope": "dataiku.access",
    "scopeClaimFormat": "STRING",
    "scopeClaimKey": "scp",
    "subjectMatch": "LOGIN",
}

settings.save()
```

For generic OIDC, use the exact issuer, JWKS URI, audience, scope claim name, and
string-or-array format found in the exchanged token.

> **Current subject-mapping limitation**
>
> Dataiku always reads the standard JWT `sub` claim. `subjectMatch` only chooses whether
> that value is compared with the Dataiku user's login (`LOGIN`) or email (`EMAIL`); it
> cannot select another JWT claim. This remains true for the forthcoming UI.
>
> Entra uses a pairwise, application-specific `sub`, so it normally differs from a
> person's login and email. The MCP and Dataiku tokens may also contain different `sub`
> values for the same user because they target different applications. For now, the
> delegated token's `sub` must equal the selected Dataiku login or email. Validate this
> constraint before production rollout. See Microsoft's
> [access-token claims reference](https://learn.microsoft.com/en-us/entra/identity-platform/access-token-claims-reference).

## Verify and troubleshoot

After starting the server:

1. Authenticate and call `list_instances`.
2. Call `switch_instance` for one catalog entry.
3. Call a Dataiku-backed tool such as `list_projects`.

| Failure | Where it occurred | Check |
| --- | --- | --- |
| MCP returns 401 | Incoming-token validation | Signature, expiry, issuer, MCP audience, and required scope |
| Token exchange returns 400 | Identity-provider token endpoint | Exchange credentials, incoming audience, downstream scope, trust, and consent |
| Dataiku rejects the token | Dataiku JWT validation or user lookup | Delegated issuer, JWKS, audience, scope claim/format, and `sub` mapping |

For Entra, a token whose issuer is `https://sts.windows.net/<tenant-id>/` is a v1
token. Calling a v2 token endpoint does not override the version selected by the
target resource registration, so set `api.requestedAccessTokenVersion` to `2` on
both app registrations:

- If the MCP server rejects the incoming token, check the **MCP registration**.
- If Dataiku rejects the exchanged token, check the **Dataiku API registration identified
  by that instance's `delegated_scope`**.

After correcting the Dataiku API registration, the next Dataiku-backed tool call performs
a new exchange; the MCP server does not need to be restarted.

Do not paste bearer tokens into tickets or logs. Use decoded claims without the
encoded token when diagnosing issuer, audience, scope, or subject mismatches.
