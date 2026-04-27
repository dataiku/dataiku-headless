"""dku admin — DSS instance administration (logs, license, IAM, settings, infra).

**Safety rules for destructive ops:**

- Every admin mutation (`license upload`, `sso/ldap/azure-ad/settings set`,
  `infra push-base-images`, `infra apply-k8s-policies`, `messaging delete`)
  requires ``--yes`` to execute. Without it, the command prints what it WOULD do
  and exits with code 0. This prevents agent-driven lockouts.
- ``settings set`` is a FULL REPLACE, not a merge. Always GET → edit → SET.
  The CLI refuses to save if the payload is missing fields present in
  the live config (fail-closed).
- ``license upload`` overwrites the active license — there is no rollback.
- SSO/LDAP mis-config can lock every user out of the instance. The CLI warns
  and requires ``--yes`` + `--i-understand-lockout-risk` for ``sso/ldap/azure-ad set``.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import get_client_from_ctx, read_json_input
from dku_cli.output import (
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(help="DSS instance administration (admin only).")

# ---------------------------------------------------------------------------
# Sub-app registration happens at the bottom of this file after each Typer is
# defined. Keeping all admin verbs in one module makes the safety rules above
# easy to audit in one place.
# ---------------------------------------------------------------------------


def _require_confirmation(
    yes: bool, action: str, details: list[str] | None = None
) -> None:
    """Abort unless ``--yes`` was passed. Used for destructive admin ops.

    Prints the full action the user is about to take, then either returns
    (when yes=True) or exits 0 with a dry-run message.
    """
    if yes:
        return
    warn(f"Dry run — would {action}. Pass --yes to execute.")
    for line in details or []:
        info(f"  • {line}")
    raise typer.Exit(code=0)


def _require_lockout_ack(ack: bool, component: str) -> None:
    """Refuse IAM writes unless caller explicitly acknowledges lockout risk."""
    if ack:
        return
    exit_with_error(
        f"Refusing to write {component} settings without --i-understand-lockout-risk.",
        code="admin_lockout_guard",
        details=[
            "Misconfigured SSO/LDAP/AzureAD can lock every user out of DSS.",
            "Always GET current settings, diff against your change, and keep a",
            "session open in another browser window before saving.",
            "Re-run with: --yes --i-understand-lockout-risk",
        ],
    )


@app.command()
def logs(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List available log files."""
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        log_list = client.list_logs()

        if fmt == "json":
            render_raw(log_list, output_format="json")
        else:
            data = []
            for item in log_list:
                if isinstance(item, dict):
                    data.append(
                        {
                            "name": item.get("name", ""),
                            "size": str(item.get("totalSize", "")),
                        }
                    )
                else:
                    data.append({"name": str(item), "size": ""})
            render(
                data,
                ["name", "size"],
                output_format=fmt,
                title="Log Files",
                headers={"name": "NAME", "size": "SIZE"},
            )
    except Exception as e:
        handle_api_error(e)


@app.command("get-log")
def get_log(
    ctx: typer.Context,
    name: str = typer.Argument(help="Log file name (from 'dku admin logs')"),
) -> None:
    """Get contents of a specific log file.

    Example:
      dku admin get-log backend.log
    """
    try:
        client = get_client_from_ctx(ctx)
        content = client.get_log(name)
        if isinstance(content, str):
            print(content)
        else:
            # Some versions return the log as a dict or other structure
            render_raw(content, output_format="json")
    except Exception as e:
        handle_api_error(e)


@app.command()
def usage(
    ctx: typer.Context,
    per_project: bool = typer.Option(
        False, "--per-project", help="Include per-project breakdown"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show global usage summary (projects, datasets, users, etc).

    Example:
      dku admin usage
      dku admin usage --per-project -o json
    """
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        summary = client.get_global_usage_summary(with_per_project=per_project)
        raw = summary.raw

        if fmt == "json":
            render_raw(raw, output_format="json")
        else:
            data = [
                {"metric": k, "value": str(v)}
                for k, v in raw.items()
                if not isinstance(v, (dict, list))
            ]
            render(
                data,
                ["metric", "value"],
                output_format=fmt,
                title="Usage Summary",
                headers={"metric": "METRIC", "value": "VALUE"},
            )
    except Exception as e:
        handle_api_error(e)


@app.command("instance-info")
def instance_info(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show DSS instance information (node ID, type, version, etc).

    Example:
      dku admin instance-info
    """
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        info_obj = client.get_instance_info()
        raw = info_obj.raw

        if fmt == "json":
            render_raw(raw, output_format="json")
        else:
            data = [
                {"field": k, "value": str(v)}
                for k, v in raw.items()
                if not isinstance(v, (dict, list))
            ]
            render(
                data,
                ["field", "value"],
                output_format=fmt,
                title="Instance Info",
            )
    except Exception as e:
        handle_api_error(e)


@app.command("sanity-check")
def sanity_check(
    ctx: typer.Context,
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for completion"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Run an instance sanity check.

    Checks DSS configuration, connectivity, and health.

    Example:
      dku admin sanity-check
      dku admin sanity-check -o json
    """
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        info("Running sanity check...")
        result = client.perform_instance_sanity_check(wait=wait)

        if not wait:
            success("Sanity check started (use --wait to see results)")
            return

        if fmt == "json":
            # DSSInfoMessages has a .messages property
            if hasattr(result, "messages"):
                render_raw(result.messages, output_format="json")
            else:
                render_raw(result, output_format="json")
        else:
            if hasattr(result, "messages"):
                msgs = result.messages
                if not msgs:
                    success("Sanity check passed — no issues found.")
                else:
                    data = []
                    for msg in msgs:
                        data.append(
                            {
                                "severity": msg.get("severity", ""),
                                "code": msg.get("code", ""),
                                "message": msg.get("message", msg.get("title", "")),
                            }
                        )
                    render(
                        data,
                        ["severity", "code", "message"],
                        output_format=fmt,
                        title="Sanity Check Results",
                        headers={
                            "severity": "SEVERITY",
                            "code": "CODE",
                            "message": "MESSAGE",
                        },
                    )
            else:
                success("Sanity check completed.")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


# =============================================================================
# dku admin license — licensing status + upload
# =============================================================================

license_app = typer.Typer(help="License status and upload.")


@license_app.command("status")
def license_status(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show licensing status (edition, expiry, user caps)."""
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        status = client.get_licensing_status()
        if fmt == "json":
            render_raw(status, output_format="json")
        else:
            flat = {k: v for k, v in status.items() if not isinstance(v, (dict, list))}
            render(
                [{"field": k, "value": str(v)} for k, v in flat.items()],
                ["field", "value"],
                output_format=fmt,
                title="License Status",
            )
    except Exception as e:
        handle_api_error(e)


@license_app.command("upload")
def license_upload(
    ctx: typer.Context,
    file: Path = typer.Argument(
        ..., help="Path to license JSON file (e.g. license.json from Dataiku)"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Confirm license overwrite (no rollback)."
    ),
) -> None:
    """Install a new DSS license. Overwrites active license — NO ROLLBACK.

    Example:
      dku admin license upload ./new-license.json --yes
    """
    if not file.exists():
        exit_with_error(
            f"License file not found: {file}",
            code="license_file_missing",
            details=[
                "Provide a path to a valid DSS license JSON (typically from",
                "https://account.dataiku.com/ or your Dataiku account manager).",
            ],
        )
    try:
        content = file.read_text()
        json.loads(content)  # Validate before sending to DSS.
    except json.JSONDecodeError as exc:
        exit_with_error(
            f"License file is not valid JSON: {exc}",
            code="license_invalid_json",
            details=["Download a fresh license from Dataiku — don't hand-edit."],
        )

    _require_confirmation(
        yes,
        "overwrite the active DSS license",
        details=[
            f"source: {file}",
            "This replaces the current license IMMEDIATELY with no rollback.",
            "Confirm expiry, user caps, and edition BEFORE running with --yes.",
        ],
    )

    try:
        client = get_client_from_ctx(ctx)
        client.set_license(content)
        success("License installed. Run 'dku admin license status' to verify.")
    except Exception as e:
        handle_api_error(e)


# =============================================================================
# dku admin sso / ldap / azure-ad — IAM settings
# =============================================================================


_IAM_DICT_ATTR = {
    "get_sso_settings": "sso_settings",
    "get_ldap_settings": "ldap_settings",
    "get_azure_ad_settings": "azure_ad_settings",
}


def _iam_get(ctx: typer.Context, getter: str, label: str, output: str | None) -> None:
    fmt = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        settings_obj = getattr(client, getter)()
        attr = _IAM_DICT_ATTR[getter]
        raw = getattr(settings_obj, attr)
        render_raw(raw, output_format=fmt)
    except Exception as e:
        handle_api_error(e)


def _iam_set(
    ctx: typer.Context,
    getter: str,
    label: str,
    definition: str | None,
    yes: bool,
    ack: bool,
) -> None:
    new_settings = read_json_input(definition)
    if new_settings is None:
        exit_with_error(
            f"--definition is required for '{label} set'.",
            code="admin_missing_definition",
            details=[
                f"Workflow: dku admin {label} get -o json > /tmp/{label}.json",
                "         # edit the file",
                f"         dku admin {label} set --definition @/tmp/{label}.json --yes --i-understand-lockout-risk",
            ],
        )
    if not isinstance(new_settings, dict):
        exit_with_error(
            f"{label} settings must be a JSON object, not {type(new_settings).__name__}.",
            code="admin_bad_payload",
        )
    _require_lockout_ack(ack, label)
    _require_confirmation(
        yes,
        f"overwrite DSS {label.upper()} settings",
        details=[
            "All authentication goes through this config — a bad value can lock",
            "every user out. Test in a dry run first by GET-ing and diff-ing.",
        ],
    )

    try:
        client = get_client_from_ctx(ctx)
        settings_obj = getattr(client, getter)()
        attr = _IAM_DICT_ATTR[getter]
        setattr(settings_obj, attr, new_settings)
        settings_obj.save()
        success(
            f"{label.upper()} settings saved. VERIFY LOGIN in a separate browser "
            "NOW before closing your current session."
        )
    except Exception as e:
        handle_api_error(e)


sso_app = typer.Typer(help="SSO (OpenID / SAML) settings.")


@sso_app.command("get")
def sso_get(
    ctx: typer.Context,
    output: str | None = typer.Option("json", "-o", "--output", help="Output format"),
) -> None:
    """Dump current SSO settings as JSON."""
    _iam_get(ctx, "get_sso_settings", "sso", output)


@sso_app.command("set")
def sso_set(
    ctx: typer.Context,
    definition: str | None = typer.Option(
        None, "--definition", "-d", help="JSON object (inline, @file, or - for stdin)"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm write"),
    ack: bool = typer.Option(
        False,
        "--i-understand-lockout-risk",
        help="Acknowledge that a bad config can lock all users out of DSS",
    ),
) -> None:
    """Replace SSO settings. Refuses without --yes AND --i-understand-lockout-risk."""
    _iam_set(ctx, "get_sso_settings", "sso", definition, yes, ack)


ldap_app = typer.Typer(help="LDAP settings.")


@ldap_app.command("get")
def ldap_get(
    ctx: typer.Context,
    output: str | None = typer.Option("json", "-o", "--output", help="Output format"),
) -> None:
    """Dump current LDAP settings as JSON."""
    _iam_get(ctx, "get_ldap_settings", "ldap", output)


@ldap_app.command("set")
def ldap_set(
    ctx: typer.Context,
    definition: str | None = typer.Option(
        None, "--definition", "-d", help="JSON object (inline, @file, or -)"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm write"),
    ack: bool = typer.Option(
        False,
        "--i-understand-lockout-risk",
        help="Acknowledge lockout risk",
    ),
) -> None:
    """Replace LDAP settings. Refuses without --yes AND --i-understand-lockout-risk."""
    _iam_set(ctx, "get_ldap_settings", "ldap", definition, yes, ack)


azure_ad_app = typer.Typer(help="Azure AD / Microsoft Entra ID settings.")


@azure_ad_app.command("get")
def azure_ad_get(
    ctx: typer.Context,
    output: str | None = typer.Option("json", "-o", "--output", help="Output format"),
) -> None:
    """Dump current Azure AD settings as JSON."""
    _iam_get(ctx, "get_azure_ad_settings", "azure-ad", output)


@azure_ad_app.command("set")
def azure_ad_set(
    ctx: typer.Context,
    definition: str | None = typer.Option(
        None, "--definition", "-d", help="JSON object (inline, @file, or -)"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm write"),
    ack: bool = typer.Option(
        False,
        "--i-understand-lockout-risk",
        help="Acknowledge lockout risk",
    ),
) -> None:
    """Replace Azure AD settings. Refuses without --yes AND --i-understand-lockout-risk."""
    _iam_set(ctx, "get_azure_ad_settings", "azure-ad", definition, yes, ack)


# =============================================================================
# dku admin settings — DSS general settings (impersonation, container-exec, etc)
# =============================================================================

settings_app = typer.Typer(help="DSS general settings (impersonation, container-exec).")


@settings_app.command("get")
def settings_get(
    ctx: typer.Context,
    output: str | None = typer.Option("json", "-o", "--output", help="Output format"),
) -> None:
    """Dump general settings as JSON. Use as the starting point for 'set'."""
    fmt = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        gs = client.get_general_settings()
        render_raw(gs.get_raw(), output_format=fmt)
    except Exception as e:
        handle_api_error(e)


@settings_app.command("set")
def settings_set(
    ctx: typer.Context,
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="JSON object from 'settings get' (inline, @file, or -)",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm write"),
) -> None:
    """Replace DSS general settings. Always GET → edit → SET.

    Example:
      dku admin settings get > /tmp/gs.json
      # edit /tmp/gs.json
      dku admin settings set -d @/tmp/gs.json --yes
    """
    new_settings = read_json_input(definition)
    if not isinstance(new_settings, dict):
        exit_with_error(
            "General settings must be a JSON object.",
            code="admin_bad_payload",
        )
    _require_confirmation(
        yes,
        "overwrite DSS general settings",
        details=[
            "This replaces impersonation rules, container-exec config, code-env",
            "permissions, and global policies. Always GET current settings first.",
        ],
    )
    try:
        client = get_client_from_ctx(ctx)
        gs = client.get_general_settings()
        live_keys = set(gs.get_raw().keys())
        new_keys = set(new_settings.keys())
        missing = live_keys - new_keys
        if missing:
            exit_with_error(
                f"Refusing to save — payload is missing {len(missing)} key(s) present in live config.",
                code="admin_settings_partial",
                details=[
                    f"Missing: {sorted(missing)[:10]}",
                    "General settings save is a FULL replace, not a merge.",
                    "Run 'dku admin settings get' → edit → 'set' with the full object.",
                ],
            )
        gs.settings = new_settings
        gs.save()
        success("General settings saved.")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


# =============================================================================
# dku admin users-sync — external user/group sync (LDAP, Azure AD, custom)
# =============================================================================

users_sync_app = typer.Typer(help="External user/group sync from LDAP/Azure AD/custom.")


@users_sync_app.command("resync-all")
def users_sync_resync_all(
    ctx: typer.Context,
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm resync"),
    wait: bool = typer.Option(False, "--wait", help="Block until complete"),
) -> None:
    """Resync ALL existing users from their external supplier.

    May deactivate users no longer present in the external source.
    """
    _require_confirmation(
        yes,
        "resync all users from the external supplier",
        details=[
            "Users removed from LDAP/AzureAD will be deactivated in DSS.",
            "Their projects/tokens remain but they can no longer log in.",
        ],
    )
    try:
        client = get_client_from_ctx(ctx)
        future = client.start_resync_all_users_from_supplier()
        if wait:
            result = future.wait_for_result()
            render_raw(result, output_format="json")
        else:
            info(f"Resync started (future {future.job_id}). Use --wait to block.")
    except Exception as e:
        handle_api_error(e)


@users_sync_app.command("fetch-external-users")
def users_sync_fetch_users(
    ctx: typer.Context,
    source: str = typer.Option(
        ..., "--source", help="Source type: LDAP | AZURE_AD | CUSTOM"
    ),
    login: str | None = typer.Option(None, "--login", help="Exact external login"),
    email: str | None = typer.Option(None, "--email", help="Exact external email"),
    group_name: str | None = typer.Option(
        None, "--group", help="External group members"
    ),
    output: str | None = typer.Option("json", "-o", "--output", help="Output format"),
) -> None:
    """Search the external directory WITHOUT provisioning any DSS accounts."""
    if source not in {"LDAP", "AZURE_AD", "CUSTOM"}:
        exit_with_error(
            f"Invalid --source '{source}'. Must be LDAP, AZURE_AD, or CUSTOM.",
            code="admin_bad_source",
        )
    fmt = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        future = client.start_fetch_external_users(
            user_source_type=source, login=login, email=email, group_name=group_name
        )
        result = future.wait_for_result()
        render_raw(result, output_format=fmt)
    except Exception as e:
        handle_api_error(e)


@users_sync_app.command("fetch-external-groups")
def users_sync_fetch_groups(
    ctx: typer.Context,
    source: str = typer.Option(
        ..., "--source", help="Source type: LDAP | AZURE_AD | CUSTOM"
    ),
    output: str | None = typer.Option("json", "-o", "--output", help="Output format"),
) -> None:
    """List groups visible in the external directory."""
    if source not in {"LDAP", "AZURE_AD", "CUSTOM"}:
        exit_with_error(
            f"Invalid --source '{source}'. Must be LDAP, AZURE_AD, or CUSTOM.",
            code="admin_bad_source",
        )
    fmt = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        future = client.start_fetch_external_groups(user_source_type=source)
        result = future.wait_for_result()
        render_raw(result, output_format=fmt)
    except Exception as e:
        handle_api_error(e)


# =============================================================================
# dku admin messaging — SMTP / Slack / Teams channels
# =============================================================================

messaging_app = typer.Typer(help="Messaging channels (SMTP, Slack, Teams, etc).")


@messaging_app.command("list")
def messaging_list(
    ctx: typer.Context,
    channel_type: str | None = typer.Option(None, "--type", help="Filter by type"),
    family: str | None = typer.Option(
        None, "--family", help="Filter by family (e.g. mail)"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List configured messaging channels."""
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        channels = client.list_messaging_channels(
            as_type="listitems", channel_type=channel_type, channel_family=family
        )
        data = []
        for c in channels:
            raw = c._data if hasattr(c, "_data") else getattr(c, "raw", c)
            if not isinstance(raw, dict):
                raw = {}
            data.append(
                {
                    "id": raw.get("id", ""),
                    "type": raw.get("type", ""),
                    "family": raw.get("family", ""),
                }
            )
        if fmt == "json":
            render_raw(data, output_format="json")
        else:
            if not data:
                info("No messaging channels configured.")
                return
            render(
                data,
                ["id", "type", "family"],
                output_format=fmt,
                title="Messaging Channels",
            )
    except Exception as e:
        handle_api_error(e)


@messaging_app.command("delete")
def messaging_delete(
    ctx: typer.Context,
    channel_id: str = typer.Argument(help="Channel ID (from 'messaging list')"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm deletion"),
) -> None:
    """Delete a messaging channel.

    Scenarios that reference this channel will FAIL to send alerts after
    deletion. Check scenario definitions first.
    """
    _require_confirmation(
        yes,
        f"delete messaging channel '{channel_id}'",
        details=[
            "Scenarios that reference this channel will fail to send alerts.",
            "Grep scenario JSON for the channel id before deleting.",
        ],
    )
    try:
        client = get_client_from_ctx(ctx)
        channel = client.get_messaging_channel(channel_id)
        channel.delete()
        success(f"Deleted messaging channel '{channel_id}'")
    except Exception as e:
        handle_api_error(e)


@messaging_app.command("send-test")
def messaging_send_test(
    ctx: typer.Context,
    channel_id: str = typer.Option(..., "--id", help="Channel ID"),
    project: str = typer.Option(..., "--project", "-P", help="Source project key"),
    to: str = typer.Option(..., "--to", help="Comma-separated recipient list"),
    subject: str = typer.Option("DSS channel test", "--subject"),
    body: str = typer.Option(
        "Test message sent via 'dku admin messaging send-test'.", "--body"
    ),
    plain_text: bool = typer.Option(
        True, "--plain-text/--html", help="plain-text vs HTML body"
    ),
) -> None:
    """Send a test message via a mail channel. Verifies creds."""
    try:
        client = get_client_from_ctx(ctx)
        channel = client.get_messaging_channel(channel_id)
        if not hasattr(channel, "send"):
            exit_with_error(
                f"Channel '{channel_id}' is not a mail channel (no send method).",
                code="messaging_not_mail",
                details=[
                    "send-test is supported on smtp / aws-ses-mail / microsoft-graph-mail.",
                ],
            )
        recipients = [addr.strip() for addr in to.split(",") if addr.strip()]
        channel.send(
            project_key=project,
            to=recipients,
            subject=subject,
            body=body,
            plain_text=plain_text,
        )
        success(f"Test message dispatched via '{channel_id}' to {recipients}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@messaging_app.command("create")
def messaging_create(
    ctx: typer.Context,
    channel_type: str = typer.Option(
        ...,
        "--type",
        help="smtp | aws-ses-mail | microsoft-graph-mail | slack | msft-teams | google-chat | twilio | shell",
    ),
    channel_id: str | None = typer.Option(
        None, "--id", help="Channel ID (auto if omitted)"
    ),
    config: str | None = typer.Option(
        None, "--config", "-c", help="JSON channel_configuration (inline, @file, -)"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm creation"),
) -> None:
    """Create a messaging channel.

    Example:
      dku admin messaging create --type smtp --id ops-smtp \\
        --config '{"host":"smtp.example.com","port":587,"sender":"dss@example.com"}' --yes
    """
    cfg = read_json_input(config) if config else None
    _require_confirmation(
        yes,
        f"create messaging channel of type '{channel_type}'",
        details=[f"id: {channel_id or '(auto)'}", f"config keys: {list(cfg or {})}"],
    )
    try:
        client = get_client_from_ctx(ctx)
        channel = client.create_messaging_channel(
            channel_type=channel_type, channel_id=channel_id, channel_configuration=cfg
        )
        raw = getattr(channel, "_data", None) or getattr(channel, "raw", {})
        success(f"Created channel {raw.get('id', '') if isinstance(raw, dict) else ''}")
        render_raw(raw, output_format="json")
    except Exception as e:
        handle_api_error(e)


# =============================================================================
# dku admin infra — container-exec base images, K8s namespace policies
# =============================================================================

infra_app = typer.Typer(help="Infrastructure: base images, K8s policies.")


@infra_app.command("push-base-images")
def infra_push_base_images(
    ctx: typer.Context,
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm push"),
) -> None:
    """Push container-exec base images to the configured registry."""
    _require_confirmation(
        yes,
        "push container-exec base images to the configured registry",
        details=[
            "Requires: container-exec configured in general settings AND registry",
            "credentials valid. Can take minutes. Safe to retry.",
        ],
    )
    try:
        client = get_client_from_ctx(ctx)
        result = client.push_base_images()
        render_raw(result or {"status": "ok"}, output_format="json")
    except Exception as e:
        handle_api_error(e)


@infra_app.command("apply-k8s-policies")
def infra_apply_k8s_policies(
    ctx: typer.Context,
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm apply"),
) -> None:
    """Apply Kubernetes namespace policies from general settings to the cluster."""
    _require_confirmation(
        yes,
        "apply Kubernetes namespace policies",
        details=[
            "Reads namespace policies from DSS general settings and pushes them",
            "to the target cluster. Verify policies first with 'settings get'.",
        ],
    )
    try:
        client = get_client_from_ctx(ctx)
        result = client.apply_kubernetes_namespaces_policies()
        render_raw(result or {"status": "ok"}, output_format="json")
    except Exception as e:
        handle_api_error(e)


# =============================================================================
# dku admin code-studio-template — list templates
# =============================================================================

cst_app = typer.Typer(help="Code studio templates (admin visibility).")


@cst_app.command("list")
def cst_list(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List registered code studio templates."""
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        templates = client.list_code_studio_templates(as_type="listitems")
        data = []
        for t in templates:
            raw = getattr(t, "_data", None) or getattr(t, "raw", t)
            if not isinstance(raw, dict):
                raw = {}
            data.append(
                {
                    "id": raw.get("id", ""),
                    "label": raw.get("label", ""),
                    "description": (raw.get("description") or "")[:60],
                }
            )
        if fmt == "json":
            render_raw(data, output_format="json")
        else:
            if not data:
                info("No code studio templates registered.")
                return
            render(
                data,
                ["id", "label", "description"],
                output_format=fmt,
                title="Code Studio Templates",
            )
    except Exception as e:
        handle_api_error(e)


# =============================================================================
# Register sub-apps
# =============================================================================

app.add_typer(license_app, name="license")
app.add_typer(sso_app, name="sso")
app.add_typer(ldap_app, name="ldap")
app.add_typer(azure_ad_app, name="azure-ad")
app.add_typer(settings_app, name="settings")
app.add_typer(users_sync_app, name="users-sync")
app.add_typer(messaging_app, name="messaging")
app.add_typer(infra_app, name="infra")
app.add_typer(cst_app, name="code-studio-template")


# =============================================================================
# dku admin llm-cost — LLM Mesh cost-limiting counters (read-only in SDK)
# =============================================================================

llm_cost_app = typer.Typer(help="LLM Mesh cost-limiting counters (read-only).")


@llm_cost_app.command("counters")
def llm_cost_counters(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List all LLM cost-limiting counters and their current state.

    Counter quotas (limits, period, scope) are configured in the UI only —
    the SDK exposes read access. Use this to monitor how close projects /
    users / LLMs are to their caps.
    """
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        counters_obj = client.get_llm_cost_limiting_counters()
        raw = counters_obj.get_raw()
        items = raw.get("counters", []) if isinstance(raw, dict) else []
        if fmt == "json":
            render_raw(raw, output_format="json")
            return
        if not items:
            info("No LLM cost-limiting counters configured.")
            return
        data = []
        for c in items:
            data.append(
                {
                    "id": c.get("id", ""),
                    "scope": c.get("scope", ""),
                    "period": c.get("period", ""),
                    "used": str(c.get("used", "")),
                    "limit": str(c.get("limit", "")),
                }
            )
        render(
            data,
            ["id", "scope", "period", "used", "limit"],
            output_format=fmt,
            title="LLM Cost Counters",
        )
    except Exception as e:
        handle_api_error(e)


@llm_cost_app.command("get")
def llm_cost_get(
    ctx: typer.Context,
    counter_id: str = typer.Argument(help="Counter ID (from 'llm-cost counters')"),
) -> None:
    """Get a specific LLM cost counter by ID."""
    try:
        client = get_client_from_ctx(ctx)
        counters_obj = client.get_llm_cost_limiting_counters()
        counter = counters_obj.get_counter(counter_id)
        if counter is None:
            exit_with_error(
                f"No counter found with id '{counter_id}'.",
                code="llm_cost_counter_not_found",
                details=[
                    "Run 'dku admin llm-cost counters' to list available counter IDs.",
                    "Counter configuration is UI-only — add/edit quotas in",
                    "Admin → LLM Mesh → Cost limiting.",
                ],
            )
        render_raw(counter, output_format="json")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


app.add_typer(llm_cost_app, name="llm-cost")


# =============================================================================
# dku admin disk-footprint — data directories footprint (read-only)
# =============================================================================

footprint_app = typer.Typer(help="Data directories footprint (read-only disk usage).")


def _format_footprint(fp) -> list[dict]:
    """Flatten a Footprint into a small rows-of-dicts for table output."""
    if fp is None:
        return []
    raw = dict(fp) if hasattr(fp, "items") else {}
    rows: list[dict] = []
    base = {
        "name": raw.get("name", raw.get("projectKey", raw.get("path", "ROOT"))),
        "size_bytes": str(raw.get("size", "")),
        "n_files": str(raw.get("nbFiles", "")),
        "n_folders": str(raw.get("nbFolders", "")),
    }
    rows.append(base)
    # Shallow children
    for item in raw.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "name": item.get(
                    "projectKey",
                    item.get("name", item.get("path", "?")),
                ),
                "size_bytes": str(item.get("size", "")),
                "n_files": str(item.get("nbFiles", "")),
                "n_folders": str(item.get("nbFolders", "")),
            }
        )
    return rows


@footprint_app.command("global")
def global_(  # noqa: A001 — "global" is a Python keyword
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Size of instance-wide directories (code envs, plugins, libs)."""
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        fp = client.get_data_directories_footprint().compute_global_only_footprint(
            wait=True
        )
        if fmt == "json":
            render_raw(dict(fp) if hasattr(fp, "items") else fp, output_format="json")
        else:
            render(
                _format_footprint(fp),
                ["name", "size_bytes", "n_files", "n_folders"],
                output_format=fmt,
                title="Global data directories footprint",
            )
    except Exception as e:
        handle_api_error(e)


@footprint_app.command()
def project(
    ctx: typer.Context,
    project_key: str = typer.Argument(help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Size of a single project's owned directories."""
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        fp = client.get_data_directories_footprint().compute_project_footprint(
            project_key, wait=True
        )
        if fmt == "json":
            render_raw(dict(fp) if hasattr(fp, "items") else fp, output_format="json")
        else:
            render(
                _format_footprint(fp),
                ["name", "size_bytes", "n_files", "n_folders"],
                output_format=fmt,
                title=f"Footprint — {project_key}",
            )
    except Exception as e:
        handle_api_error(e)


@footprint_app.command("all")
def all_footprint(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Size of ALL DSS data directories (global + all projects). Can be slow."""
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        fp = client.get_data_directories_footprint().compute_all_dss_footprint(
            wait=True
        )
        if fmt == "json":
            render_raw(dict(fp) if hasattr(fp, "items") else fp, output_format="json")
        else:
            render(
                _format_footprint(fp),
                ["name", "size_bytes", "n_files", "n_folders"],
                output_format=fmt,
                title="Full DSS footprint",
            )
    except Exception as e:
        handle_api_error(e)


@footprint_app.command()
def unknown(
    ctx: typer.Context,
    summary_only: bool = typer.Option(
        True, "--summary-only/--detailed", help="Aggregate per location"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Directories in the data root that don't belong to DSS (leaked data)."""
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        fp = client.get_data_directories_footprint().compute_unknown_footprint(
            show_summary_only=summary_only, wait=True
        )
        if fmt == "json":
            render_raw(
                fp if isinstance(fp, (dict, list)) else dict(fp), output_format="json"
            )
        else:
            rows = _format_footprint(fp) if not isinstance(fp, list) else []
            render(
                rows,
                ["name", "size_bytes", "n_files", "n_folders"],
                output_format=fmt,
                title="Unknown directories",
            )
    except Exception as e:
        handle_api_error(e)


# =============================================================================
# dku admin catalog-index — trigger data catalog indexing (idempotent)
# =============================================================================


@app.command("catalog-index")
def catalog_index(
    ctx: typer.Context,
    all_conns: bool = typer.Option(False, "--all", help="Index every connection"),
    connections: str | None = typer.Option(
        None,
        "--connections",
        "-c",
        help="Comma-separated connection names to index",
    ),
    mode: str = typer.Option(
        "FULL", "--mode", help="Indexing mode: FULL | INCREMENTAL"
    ),
) -> None:
    """Trigger data catalog indexing for one or more connections.

    Idempotent — safe to re-run. Large connections can take minutes.
    """
    if not all_conns and not connections:
        exit_with_error(
            "Pass --all or --connections NAME1,NAME2.",
            code="catalog_index_no_target",
        )
    if mode not in {"FULL", "INCREMENTAL"}:
        exit_with_error(
            f"--mode must be FULL or INCREMENTAL, got '{mode}'.",
            code="catalog_index_bad_mode",
        )
    names = (
        [n.strip() for n in connections.split(",") if n.strip()] if connections else []
    )
    try:
        client = get_client_from_ctx(ctx)
        result = client.catalog_index_connections(
            connection_names=names, all_connections=all_conns, indexing_mode=mode
        )
        render_raw(result or {"status": "ok"}, output_format="json")
    except Exception as e:
        handle_api_error(e)


# =============================================================================
# dku admin assets — Enterprise Asset Library (read-only)
# =============================================================================

assets_app = typer.Typer(help="Enterprise Asset Library (read-only).")


@assets_app.command("list-collections")
def assets_list_collections(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List enterprise asset collections."""
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        eal = client.get_enterprise_asset_library()
        collections = eal.list_collections()
        if fmt == "json":
            render_raw(collections, output_format="json")
            return
        if not collections:
            info("No collections found.")
            return
        data = []
        for c in collections:
            raw = c if isinstance(c, dict) else getattr(c, "_data", {}) or {}
            data.append(
                {
                    "id": raw.get("id", ""),
                    "name": raw.get("name", raw.get("label", "")),
                    "description": (raw.get("description") or "")[:60],
                }
            )
        render(
            data,
            ["id", "name", "description"],
            output_format=fmt,
            title="Enterprise Asset Collections",
        )
    except Exception as e:
        handle_api_error(e)


@assets_app.command("list-prompts")
def assets_list_prompts(
    ctx: typer.Context,
    collections: str | None = typer.Option(
        None,
        "--collections",
        help="Comma-separated collection IDs to restrict to",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List enterprise prompts (optionally filtered by collection)."""
    fmt = resolve_output_format(output)
    restrict = (
        [c.strip() for c in collections.split(",") if c.strip()]
        if collections
        else None
    )
    try:
        client = get_client_from_ctx(ctx)
        eal = client.get_enterprise_asset_library()
        prompts = eal.list_prompts(restrict_collections=restrict)
        if fmt == "json":
            render_raw(prompts, output_format="json")
            return
        if not prompts:
            info("No prompts found.")
            return
        data = []
        for p in prompts:
            raw = p if isinstance(p, dict) else getattr(p, "_data", {}) or {}
            data.append(
                {
                    "id": raw.get("id", ""),
                    "name": raw.get("name", ""),
                    "collection": raw.get("collectionId", ""),
                }
            )
        render(
            data,
            ["id", "name", "collection"],
            output_format=fmt,
            title="Enterprise Prompts",
        )
    except Exception as e:
        handle_api_error(e)


# =============================================================================
# dku admin audit-log — write a custom audit entry (self-scoped, non-destructive)
# =============================================================================


@app.command("audit-log")
def audit_log(
    ctx: typer.Context,
    entry_type: str = typer.Option(..., "--type", help="Custom audit type string"),
    params: str | None = typer.Option(
        None, "--params", help="JSON object of custom params (inline, @file, -)"
    ),
) -> None:
    """Write a custom entry to the DSS audit log.

    Self-scoped — the entry is attributed to the calling user/API key and has
    no effect on DSS state. Use for marking CI/CD events, migrations, or
    external ops that should appear in the audit trail.
    """
    parsed = read_json_input(params) if params else None
    if parsed is not None and not isinstance(parsed, dict):
        exit_with_error(
            "--params must be a JSON object.",
            code="audit_log_bad_params",
        )
    try:
        client = get_client_from_ctx(ctx)
        client.log_custom_audit(custom_type=entry_type, custom_params=parsed or {})
        success(f"Logged audit entry (type={entry_type})")
    except Exception as e:
        handle_api_error(e)


# =============================================================================
# Register new sub-apps
# =============================================================================

app.add_typer(footprint_app, name="disk-footprint")
app.add_typer(assets_app, name="assets")
