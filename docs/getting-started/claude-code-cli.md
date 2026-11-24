# Claude Code CLI

This guide covers installing Dataiku Headless in Claude Code and connecting it
to Dataiku.

## Before you start

Have your Dataiku instance URL and personal API key ready. Do not paste the key
into the conversation. Dataiku Headless also needs network access to the instance
and [uv 0.12.0 or later](https://docs.astral.sh/uv/getting-started/installation/).
The setup flow checks for uv and, with your approval, can install it.

## Install

Run:

```bash
claude plugin marketplace add https://github.com/dataiku/dataiku-headless.git
claude plugin install headless@dataiku
```

## Connect to Dataiku

Start Claude Code and run `/headless:dataiku-headless-setup`. Approve the MCP
server URL prompt if Claude Code asks.

In the setup page, add an instance with a name, instance type, Dataiku URL, and personal
API key. Select the type that matches your node (Design, Automation, or Deployer). Find
your key in Dataiku under Profile & Settings → API keys. Keep the key in the setup page;
do not paste it into chat. Test the connection, save the instance, and select **Done**.
The profile stores credentials locally in plaintext with user-only file permissions. The
checkboxes to use the instance by default and switch to it after saving are selected by
default.

![Add a Dataiku instance, test the connection, and save it](../assets/installation/dataiku-instance-form.png)

Ask Claude Code to verify the connection or show the projects you can access.
Building or changing project logic requires a Design node with Cobuild available.

For multiple instances, certificate trust, or environment configuration, see
[Connecting to Dataiku](../connecting-to-dataiku.md).

[Back to the README](../../README.md)
