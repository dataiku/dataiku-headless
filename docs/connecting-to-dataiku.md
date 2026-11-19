# Connecting to Dataiku

For a local connection, [install the plugin](installation.md), then configure
an instance using a personal API key:

1. Ask the agent to **Set up Dataiku Headless** (or run `/headless:dataiku-headless-setup` in Claude Code).
2. Approve the MCP URL prompt.
3. Enter an instance name, choose its type, and supply its Dataiku URL and personal API key in the setup page.
4. Test the connection when supported, save it, and select **Done**.
5. Ask your agent to verify the connection. Repeat to add more instances, or ask your agent to switch between them.

Inside a Code Studio, the hosting DSS instance is discovered automatically using
its injected API ticket. No personal API key or setup popup is needed.

Saved API keys and Code Studio tickets are kept out of the agent conversation.

## Manage saved instances

Ask your agent to **Manage Dataiku instances** to reopen the local browser manager.
You can add, edit, delete, or switch instances and choose a startup default.
Test the connection when supported, save your changes, and select **Done**.
Ask the agent to verify the active instance before continuing your work.

Saved credentials stay hidden in the manager. Environment and Code Studio
instances are read-only.

## HTTPS certificate trust

Dataiku Headless uses the operating system certificate store for
HTTPS connections, including connection tests in the setup page. Corporate CAs
trusted on the machine running Dataiku Headless are trusted automatically; no
CA-bundle environment variable is needed. In a container or remote deployment,
the CA must be trusted inside that environment.

Keep **Skip certificate verification** unchecked. If a saved profile previously
disabled verification, edit it in the instance manager, uncheck that option, and
test and save the connection again.

## Where configuration lives

**Saved profiles.** The setup page stores named instances and a `default_instance`
in a JSON file with user-only (0600) permissions. Credentials are stored in
plaintext. Use `--settings-path PATH` to select the file; otherwise, the server uses:

1. An existing `./.dataiku/stdio-config.json` in the server's working directory.
2. `~/.dataiku/stdio-config.json` otherwise.

Add multiple instances through the setup page or edit the file using
[`.dataiku/stdio-config.json.example`](../.dataiku/stdio-config.json.example).
Choose the instance type that matches the work you want to do: `design`,
`automation`, or `deployer`. A local Deployer on a Design or Automation node
requires a separate `deployer` profile for that URL.

**Environment override.** To select an explicit target, including inside a Code
Studio, set these three variables in your environment or copy
[`.env.example`](../.env.example) to the repository-root `.env`:

```bash
DKU_DSS_URL=https://your-instance.dataiku.com
DKU_INSTANCE_TYPE=design
DKU_API_KEY=your-api-key
```

`DKU_INSTANCE_NAME` optionally names this target (default `dataiku-from-env`).
`DKU_NO_CHECK_CERTIFICATE=true` optionally disables its TLS verification.
Existing environment variables take precedence over values in `.env`.

**Startup selection.** The active instance is the first available source below:

1. The explicit environment target above.
2. The hosting instance when running inside a Dataiku Code Studio.
3. The saved profiles' `default_instance`.

Ask your agent to show or switch the active instance at any time. Environment instances
take precedence over profiles with the same name. The explicit target must have
a different name from `dataiku-from-code-studio` when both exist. Missing required
credentials or environment types, unsupported types, and duplicate environment names fail startup.

Settings load at startup. Changes through the setup page or instance tools refresh
the saved profiles immediately; manual file edits and environment changes require a restart.

[Back to the README](../README.md)
