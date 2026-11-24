# Cursor desktop app

This guide covers installing and connecting Dataiku Headless in Cursor.

## Before you start

Have your Dataiku instance URL and personal API key ready. Do not paste the key
into the conversation. Dataiku Headless also needs network access to the instance
and [uv 0.12.0 or later](https://docs.astral.sh/uv/getting-started/installation/).
The setup flow checks for uv and, with your approval, can install it.

## Install

Open **Customize → Plugins → + Add → From GitHub Repository**, enter
`https://github.com/dataiku/dataiku-headless`, and click **Import**. Then, in the
plugin homepage, find Dataiku Headless and click **Add**.

![In Cursor, open the plugin menu and choose From GitHub Repository](../assets/installation/cursor-desktop-1.png)

![Enter the Dataiku Headless GitHub repository and import it](../assets/installation/cursor-desktop-2.png)

![Find Dataiku Headless and add it](../assets/installation/cursor-desktop-3.png)

## Connect to Dataiku

In a new chat, ask **Set up Dataiku Headless**.

![Start setup in a new Cursor chat](../assets/installation/cursor-setup-prompt.png)

Approve the MCP server URL prompt if Cursor asks. In the setup page, add an instance
with a name, instance type, Dataiku URL, and personal API key. Select the type that
matches your node (Design, Automation, or Deployer). Find your key in Dataiku under
Profile & Settings → API keys. Keep the key in the setup page; do not paste it into
chat. Test the connection, save the instance, and select **Done**. The profile stores
credentials locally in plaintext with user-only file permissions. The checkboxes to use
the instance by default and switch to it after saving are selected by default.

![Add a Dataiku instance, test the connection, and save it](../assets/installation/dataiku-instance-form.png)

Ask Cursor to verify the connection or show the projects you can access.
Building or changing project logic requires a Design node with Cobuild available.

For multiple instances, certificate trust, or environment configuration, see
[Connecting to Dataiku](../connecting-to-dataiku.md).

[Back to the README](../../README.md)
