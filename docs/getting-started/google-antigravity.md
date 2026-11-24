# Google Antigravity

This guide covers installing Dataiku Headless in Google Antigravity and connecting it to
Dataiku.

## Before you start

Have your Dataiku instance URL and personal API key ready. Do not paste the key
into the conversation. Dataiku Headless also needs network access to the instance
and [uv 0.12.0 or later](https://docs.astral.sh/uv/getting-started/installation/).
The setup flow checks for uv and, with your approval, can install it.

## Install

Run:

```bash
agy plugin install https://github.com/dataiku/dataiku-headless
agy plugin list --json
```

For the standalone Antigravity IDE, you can also place the complete plugin
checkout under `.agents/plugins/dataiku-headless/` in your workspace or
`~/.gemini/config/plugins/dataiku-headless/` globally. See Google's
[plugin installation guide](https://antigravity.google/docs/plugins).

## Connect to Dataiku

Start an Antigravity session and ask **Set up Dataiku Headless**, or run
`/dataiku-headless-setup`. Approve the MCP server URL prompt if Antigravity asks.
If no prompt appears, the server opens the local setup page directly and returns
a link you can open yourself.

In the setup page, add an instance with a name, instance type, Dataiku URL, and personal
API key. Select the type that matches your node (Design, Automation, or Deployer). Find
your key in Dataiku under Profile & Settings → API keys. Keep the key in the setup page;
do not paste it into chat. Test the connection, save the instance, and select **Done**.
The profile stores credentials locally in plaintext with user-only file permissions. The
checkboxes to use the instance by default and switch to it after saving are selected by
default.

![Add a Dataiku instance, test the connection, and save it](../assets/installation/dataiku-instance-form.png)

Ask Antigravity to verify the connection or show the projects you can access. Building
or changing project logic requires a Design node with Cobuild available.

For multiple instances, certificate trust, or environment configuration, see
[Connecting to Dataiku](../connecting-to-dataiku.md).

[Back to the README](../../README.md)
