# Install Dataiku Headless

Choose your agent below, install the plugin, then ask **Set up Dataiku Headless**.
The setup flow checks the runtime and helps you connect to Dataiku.

## Choose your agent

- [ChatGPT desktop app](#chatgpt-desktop-app)
- [Claude desktop app](#claude-desktop-app)
- [Cursor desktop app](#cursor-desktop-app)
- [Snowflake CoCo desktop app](#snowflake-coco-desktop-app)
- [GitHub Copilot desktop app](#github-copilot-desktop-app)
- [Codex CLI](#codex-cli)
- [Claude Code CLI](#claude-code-cli)
- [GitHub Copilot CLI](#github-copilot-cli)
- [Grok CLI](#grok-cli)
- [Cursor Agent CLI](#cursor-agent-cli)
- [Snowflake CoCo CLI](#snowflake-coco-cli)
- [Other AI assistants](#other-ai-assistants)

## Requirements

Dataiku Headless needs network access to your Dataiku instance and
[uv 0.12.0 or later](https://docs.astral.sh/uv/getting-started/installation/).
uv provides the isolated Python runtime and pinned dependencies. The setup flow
checks for uv and, with your approval, can run the official installer for your
platform.

For a local connection, have your Dataiku URL and personal API key ready. Enter
the key in the setup page when prompted; do not paste it into the conversation.
Building and changing project logic requires a Design node with Cobuild available.

## ChatGPT desktop app

Choose either of these modes before installing the plugin:

- **Codex:** choose **Codex** from the selector at the top left and use the
  **This computer** environment.
- **Work:** choose **ChatGPT** from the selector at the top left, then select
  **Work** in the **Chat / Work** switch at the top of the window.

Open **Plugins → Public**, search for **Dataiku**, and click **+** to install
Dataiku Headless. Then, in your chosen mode, ask **Set up Dataiku Headless**.
Follow the setup page to add your Dataiku instance, test the connection, save it,
and select **Done**.

This walkthrough shows installation and setup in Codex mode:

![Installing and setting up the Dataiku Headless plugin with Codex](https://github.com/dataiku/dataiku-headless/releases/download/readme-media-v2/headless_install_setup_codex.gif)

Next: [Connect to Dataiku](connecting-to-dataiku.md).

## Claude desktop app

Choose either of these modes before installing the plugin:

- **Cowork:** select the conversation icon at the top left, then **Cowork** in
  the **Chat / Cowork** switch in the message box.
- **Claude Code:** select the **code icon (`</>`)** at the top left and choose a
  local working environment.

Open **Customize → Plugins → Discover**, search for **Dataiku**, select
Dataiku Headless, and click **Add**. Then, in your chosen mode, ask
**Set up Dataiku Headless**. Follow the setup page to add your Dataiku instance,
test the connection, save it, and select **Done**.

Next: [Connect to Dataiku](connecting-to-dataiku.md).

## Cursor desktop app

Open **Customize → Plugins → + Add → From GitHub Repository**, enter
`https://github.com/dataiku/dataiku-headless`, and click **Import**.

In a new chat, ask **Set up Dataiku Headless**. Follow the setup page to add your
Dataiku instance, test the connection, save it, and select **Done**.

Next: [Connect to Dataiku](connecting-to-dataiku.md).

## Snowflake CoCo desktop app

Open **Customize → Plugins → + → Add from GitHub**, enter
`dataiku/dataiku-headless`, and press **Enter**. Follow CoCo's installation
prompts.

When installation completes, start a new chat and ask **Set up Dataiku Headless**.
Follow the setup page to add your Dataiku instance, test the connection, save it,
and select **Done**.

Next: [Connect to Dataiku](connecting-to-dataiku.md).

## GitHub Copilot desktop app

Open **Customize → + Add → Manage marketplaces**, enter
`dataiku/dataiku-headless`, and click **Add**. In the **Search** bar at the top,
search for **Dataiku**, select Dataiku Headless, and click **+ Install**.

In a new chat, ask **Set up Dataiku Headless**. Follow the setup page to add your
Dataiku instance, test the connection, save it, and select **Done**.

Next: [Connect to Dataiku](connecting-to-dataiku.md).

## Command-line agents

### Codex CLI

```bash
codex plugin marketplace add https://github.com/dataiku/dataiku-headless.git
codex plugin add dataiku-headless@dataiku
```

Next: [Connect to Dataiku](connecting-to-dataiku.md).

### Claude Code CLI

```bash
claude plugin marketplace add https://github.com/dataiku/dataiku-headless.git
claude plugin install headless@dataiku
```

You can also start setup with `/headless:dataiku-headless-setup`.

Next: [Connect to Dataiku](connecting-to-dataiku.md).

### GitHub Copilot CLI

```bash
copilot plugin marketplace add dataiku/dataiku-headless
copilot plugin install dataiku-headless@dataiku
```

Next: [Connect to Dataiku](connecting-to-dataiku.md).

### Grok CLI

```bash
grok plugin install dataiku/dataiku-headless --trust
```

Next: [Connect to Dataiku](connecting-to-dataiku.md).

### Cursor Agent CLI

```bash
cursor agent plugin marketplace add github.com/dataiku/dataiku-headless
# Tip: use /plugins in interactive mode to install the `dataiku-headless` plugin from this marketplace.
```

Next: [Connect to Dataiku](connecting-to-dataiku.md).

### Snowflake CoCo CLI

```bash
cortex plugin install dataiku/dataiku-headless
```

Next: [Connect to Dataiku](connecting-to-dataiku.md).

## Other AI assistants

Configure your agent's MCP integration to launch the server from a checkout of
this repository:

```bash
uv run --quiet --locked --script /absolute/path/to/dataiku-headless/runtime/run_mcp.py --transport stdio
```

Replace the path with your checkout's absolute path. Use your agent's configuration
format for the command and arguments; MCP configuration formats vary by client.

Install the companion skills as well so your agent can follow the Dataiku workflows:

```bash
npx skills add dataiku/dataiku-headless
```

Installing skills alone does not connect the agent to Dataiku; the MCP server
must also be configured.

Next: [Connect to Dataiku](connecting-to-dataiku.md).

## If the tools do not appear

Ask your agent to **Set up Dataiku Headless** so it can check the installation.
You can also check whether uv is installed and available on your `PATH`:

```bash
uv --version
```

If the command is missing or reports a version below 0.12.0, follow the
[official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/),
then fully restart your agent app. The first launch may take a little longer
while the runtime is prepared. If tools remain unavailable, check your agent's
MCP startup error or ask it to diagnose the plugin registration.

For credentials, certificates, multiple instances, and environment configuration,
see [Connecting to Dataiku](connecting-to-dataiku.md).

[Back to the README](../README.md)
