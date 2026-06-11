"""dku admin — DSS instance administration (logs, license, IAM, settings, infra).

**Safety rules for destructive ops:**

All destructive admin ops go through ``safety.guard()`` — a refusal exits with
``77`` (safety_blocked) and an AGENT INSTRUCTION block, never a silent exit 0.

- Tier-4 ADMIN (``license upload``, ``settings set``, ``sso/ldap/azure-ad set``):
  require ``--yes`` + ``--confirm-name <id>`` + ``--i-know-what-im-doing``, and are
  NOT bypassable by ``--dangerous`` / ``DKU_DANGEROUS``. ``sso/ldap/azure-ad set``
  additionally require ``--i-understand-lockout-risk`` (a bad config can lock every
  user out of the instance).
- Tier-3 CASCADE (``messaging delete``, ``users-sync resync-all``): require
  ``--yes`` + ``--confirm-name`` matching the target, because they affect resources
  the caller did not explicitly name (scenarios using a channel; users dropped
  from the external supplier).
- Tier-2 DELETE (``messaging create``, ``infra push-base-images``,
  ``infra apply-k8s-policies``): require ``--yes``.
- ``settings set`` is a FULL REPLACE, not a merge. Always GET → edit → SET.
  The CLI refuses to save if the payload is missing fields present in
  the live config (fail-closed).
- ``license upload`` overwrites the active license — there is no rollback.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import ALL_NODE_TYPES, get_client_from_ctx, read_json_input
from dku_cli.output import (
    hint,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)
from dku_cli.safety import Tier, guard

app = typer.Typer(help="DSS instance administration (admin only).")

# ---------------------------------------------------------------------------
# Sub-app registration happens at the bottom of this file after each Typer is
# defined. Keeping all admin verbs in one module makes the safety rules above
# easy to audit in one place.
# ---------------------------------------------------------------------------


def _require_lockout_ack(ack: bool, component: str) -> None:
    """Refuse IAM writes unless caller explicitly acknowledges lockout risk."""
    if ack:
        return
    exit_with_error(
        f"Refusing to write {component} settings without --i-understand-lockout-risk.",
        details=[
            "Misconfigured SSO/LDAP/AzureAD can lock every user out of DSS.",
            "Always GET current settings, diff against your change, and keep a",
            "session open in another browser window before saving.",
            "Re-run with: --yes --i-understand-lockout-risk",
        ],
    )


def _is_remote_host(host: str | None) -> bool:
    """Return whether the DSS client targets a NON-local instance.

    Used by ``code-studio-template inspect-build`` to decide whether probing
    the LOCAL docker daemon for a built image is meaningful. When the active
    profile points at a remote node the image lives on that host's daemon, so
    the local probe is guaranteed to miss and "not found" would be misleading.
    """
    if not host:
        return False
    from urllib.parse import urlparse

    parsed = urlparse(host if "://" in host else f"//{host}")
    hostname = (parsed.hostname or "").lower()
    return hostname not in {"localhost", "127.0.0.1", "::1", "0.0.0.0", ""}


@app.command()
def logs(
    ctx: typer.Context,
) -> None:
    """List available log files."""
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx, allowed_node_types=ALL_NODE_TYPES)
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
        client = get_client_from_ctx(ctx, allowed_node_types=ALL_NODE_TYPES)
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
) -> None:
    """Show global usage summary (projects, datasets, users, etc).

    Example:
      dku admin usage
      dku admin usage --per-project
    """
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx, allowed_node_types=ALL_NODE_TYPES)
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
) -> None:
    """Show DSS instance information (node ID, type, version, etc).

    Example:
      dku admin instance-info
    """
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx, allowed_node_types=ALL_NODE_TYPES)
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
) -> None:
    """Run an instance sanity check.

    Checks DSS configuration, connectivity, and health.

    Example:
      dku admin sanity-check
      dku admin sanity-check
    """
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx, allowed_node_types=ALL_NODE_TYPES)
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
) -> None:
    """Show licensing status (edition, expiry, user caps)."""
    fmt = resolve_output_format()
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
    confirm_name: str = typer.Option(
        None,
        "--confirm-name",
        help="Must equal 'license' literally to proceed (tier-4 guard).",
    ),
    i_know: bool = typer.Option(
        False,
        "--i-know-what-im-doing",
        help="Tier-4 admin acknowledgement (not bypassable by --dangerous).",
    ),
) -> None:
    """Install a new DSS license. Overwrites active license — NO ROLLBACK.

    Example:
      dku admin license upload ./new-license.json --yes --confirm-name license --i-know-what-im-doing
    """
    if not file.exists():
        exit_with_error(
            f"License file not found: {file}",
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
            details=["Download a fresh license from Dataiku — don't hand-edit."],
        )

    guard(
        ctx,
        tier=Tier.ADMIN,
        action="admin.license.upload",
        subject=f"the active DSS license (source: {file})",
        yes=yes,
        target_id="license",
        confirm_name=confirm_name,
        i_know=i_know,
        prompt=(
            f"Overwrite the active DSS license with {file}? This replaces it "
            "IMMEDIATELY with no rollback — confirm expiry, user caps, and edition first."
        ),
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
    "get_azure_ad_settings": "azuread_settings",
}


def _iam_get(ctx: typer.Context, getter: str, label: str, output: str | None) -> None:
    fmt = resolve_output_format()
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
    confirm_name: str | None,
    i_know: bool,
) -> None:
    new_settings = read_json_input(definition)
    if new_settings is None:
        exit_with_error(
            f"--definition is required for '{label} set'.",
            details=[
                f"Workflow: dku --format json admin {label} get > /tmp/{label}.json",
                "         # edit the file",
                f"         dku admin {label} set --definition @/tmp/{label}.json --yes "
                f"--confirm-name {label} --i-know-what-im-doing --i-understand-lockout-risk",
            ],
        )
    if not isinstance(new_settings, dict):
        exit_with_error(
            f"{label} settings must be a JSON object, not {type(new_settings).__name__}.",
        )
    _require_lockout_ack(ack, label)
    guard(
        ctx,
        tier=Tier.ADMIN,
        action=f"admin.{label}.set",
        subject=f"DSS {label.upper()} settings",
        yes=yes,
        target_id=label,
        confirm_name=confirm_name,
        i_know=i_know,
        prompt=(
            f"Overwrite DSS {label.upper()} settings? All authentication goes "
            "through this config — a bad value can lock every user out. GET and "
            "diff the live config first."
        ),
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
) -> None:
    """Dump current SSO settings as JSON."""
    _iam_get(ctx, "get_sso_settings", "sso", "json")


@sso_app.command("set")
def sso_set(
    ctx: typer.Context,
    definition: str | None = typer.Option(
        None, "--definition", "-d", help="JSON object (inline, @file, or - for stdin)"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm write"),
    confirm_name: str = typer.Option(
        None,
        "--confirm-name",
        help="Must equal 'sso' literally to proceed (tier-4 guard).",
    ),
    i_know: bool = typer.Option(
        False,
        "--i-know-what-im-doing",
        help="Tier-4 admin acknowledgement (not bypassable by --dangerous).",
    ),
    ack: bool = typer.Option(
        False,
        "--i-understand-lockout-risk",
        help="Acknowledge that a bad config can lock all users out of DSS",
    ),
) -> None:
    """Replace SSO settings.

    Tier-4: needs --yes, --confirm-name sso, --i-know-what-im-doing,
    and --i-understand-lockout-risk.
    """
    _iam_set(ctx, "get_sso_settings", "sso", definition, yes, ack, confirm_name, i_know)


ldap_app = typer.Typer(help="LDAP settings.")


@ldap_app.command("get")
def ldap_get(
    ctx: typer.Context,
) -> None:
    """Dump current LDAP settings as JSON."""
    _iam_get(ctx, "get_ldap_settings", "ldap", "json")


@ldap_app.command("set")
def ldap_set(
    ctx: typer.Context,
    definition: str | None = typer.Option(
        None, "--definition", "-d", help="JSON object (inline, @file, or -)"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm write"),
    confirm_name: str = typer.Option(
        None,
        "--confirm-name",
        help="Must equal 'ldap' literally to proceed (tier-4 guard).",
    ),
    i_know: bool = typer.Option(
        False,
        "--i-know-what-im-doing",
        help="Tier-4 admin acknowledgement (not bypassable by --dangerous).",
    ),
    ack: bool = typer.Option(
        False,
        "--i-understand-lockout-risk",
        help="Acknowledge lockout risk",
    ),
) -> None:
    """Replace LDAP settings.

    Tier-4: needs --yes, --confirm-name ldap, --i-know-what-im-doing,
    and --i-understand-lockout-risk.
    """
    _iam_set(
        ctx, "get_ldap_settings", "ldap", definition, yes, ack, confirm_name, i_know
    )


azure_ad_app = typer.Typer(help="Azure AD / Microsoft Entra ID settings.")


@azure_ad_app.command("get")
def azure_ad_get(
    ctx: typer.Context,
) -> None:
    """Dump current Azure AD settings as JSON."""
    _iam_get(ctx, "get_azure_ad_settings", "azure-ad", "json")


@azure_ad_app.command("set")
def azure_ad_set(
    ctx: typer.Context,
    definition: str | None = typer.Option(
        None, "--definition", "-d", help="JSON object (inline, @file, or -)"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm write"),
    confirm_name: str = typer.Option(
        None,
        "--confirm-name",
        help="Must equal 'azure-ad' literally to proceed (tier-4 guard).",
    ),
    i_know: bool = typer.Option(
        False,
        "--i-know-what-im-doing",
        help="Tier-4 admin acknowledgement (not bypassable by --dangerous).",
    ),
    ack: bool = typer.Option(
        False,
        "--i-understand-lockout-risk",
        help="Acknowledge lockout risk",
    ),
) -> None:
    """Replace Azure AD settings.

    Tier-4: needs --yes, --confirm-name azure-ad, --i-know-what-im-doing,
    and --i-understand-lockout-risk.
    """
    _iam_set(
        ctx,
        "get_azure_ad_settings",
        "azure-ad",
        definition,
        yes,
        ack,
        confirm_name,
        i_know,
    )


# =============================================================================
# dku admin settings — DSS general settings (impersonation, container-exec, etc)
# =============================================================================

settings_app = typer.Typer(help="DSS general settings (impersonation, container-exec).")


@settings_app.command("get")
def settings_get(
    ctx: typer.Context,
) -> None:
    """Dump general settings as JSON. Use as the starting point for 'set'."""
    fmt = resolve_output_format()
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
    confirm_name: str = typer.Option(
        None,
        "--confirm-name",
        help="Must equal 'general-settings' literally to proceed (tier-4 guard).",
    ),
    i_know: bool = typer.Option(
        False,
        "--i-know-what-im-doing",
        help="Tier-4 admin acknowledgement (not bypassable by --dangerous).",
    ),
) -> None:
    """Replace DSS general settings. Always GET → edit → SET.

    Example:
      dku admin settings get > /tmp/gs.json
      # edit /tmp/gs.json
      dku admin settings set -d @/tmp/gs.json --yes --confirm-name general-settings --i-know-what-im-doing
    """
    new_settings = read_json_input(definition)
    if not isinstance(new_settings, dict):
        exit_with_error(
            "General settings must be a JSON object.",
        )
    guard(
        ctx,
        tier=Tier.ADMIN,
        action="admin.settings.set",
        subject="DSS general settings",
        yes=yes,
        target_id="general-settings",
        confirm_name=confirm_name,
        i_know=i_know,
        prompt=(
            "Overwrite DSS general settings? This replaces impersonation rules, "
            "container-exec config, code-env permissions, and global policies. "
            "Always GET current settings first."
        ),
    )
    try:
        client = get_client_from_ctx(ctx)
        gs = client.get_general_settings()
        live_keys = set(gs.get_raw().keys())
        new_keys = set(new_settings.keys())
        missing = live_keys - new_keys
        if missing:
            exit_with_error(
                "Refusing to save — payload is missing "
                f"{len(missing)} key(s) present in live config.",
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
    confirm_name: str = typer.Option(
        None,
        "--confirm-name",
        help="Must equal 'resync-all' literally to proceed (tier-3 guard).",
    ),
    wait: bool = typer.Option(False, "--wait", help="Block until complete"),
) -> None:
    """Resync ALL existing users from their external supplier.

    May deactivate users no longer present in the external source.
    """
    guard(
        ctx,
        tier=Tier.CASCADE,
        action="admin.users-sync.resync-all",
        subject="all users from the external supplier",
        yes=yes,
        target_id="resync-all",
        confirm_name=confirm_name,
        prompt=(
            "Resync ALL users from the external supplier? Users removed from "
            "LDAP/AzureAD will be DEACTIVATED in DSS — their projects/tokens "
            "remain but they can no longer log in."
        ),
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
) -> None:
    """Search the external directory WITHOUT provisioning any DSS accounts."""
    if source not in {"LDAP", "AZURE_AD", "CUSTOM"}:
        exit_with_error(
            f"Invalid --source '{source}'. Must be LDAP, AZURE_AD, or CUSTOM.",
        )
    fmt = resolve_output_format()
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
) -> None:
    """List groups visible in the external directory."""
    if source not in {"LDAP", "AZURE_AD", "CUSTOM"}:
        exit_with_error(
            f"Invalid --source '{source}'. Must be LDAP, AZURE_AD, or CUSTOM.",
        )
    fmt = resolve_output_format()
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
) -> None:
    """List configured messaging channels."""
    fmt = resolve_output_format()
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
    confirm_name: str = typer.Option(
        None,
        "--confirm-name",
        help="Must match the channel ID literally to proceed (tier-3 guard).",
    ),
) -> None:
    """Delete a messaging channel.

    Scenarios that reference this channel will FAIL to send alerts after
    deletion. Check scenario definitions first.
    """
    guard(
        ctx,
        tier=Tier.CASCADE,
        action="admin.messaging.delete",
        subject=f"messaging channel '{channel_id}'",
        yes=yes,
        target_id=channel_id,
        confirm_name=confirm_name,
        prompt=(
            f"Delete messaging channel '{channel_id}'? Scenarios that reference "
            "it will fail to send alerts — grep scenario JSON for the channel id first."
        ),
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
        help=(
            "smtp | aws-ses-mail | microsoft-graph-mail | slack | "
            "msft-teams | google-chat | twilio | shell"
        ),
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
    guard(
        ctx,
        tier=Tier.DELETE,
        action="admin.messaging.create",
        subject=(
            f"messaging channel of type '{channel_type}' (id: {channel_id or '(auto)'})"
        ),
        yes=yes,
        prompt=(
            f"Create messaging channel of type '{channel_type}' "
            f"(id: {channel_id or '(auto)'}, config keys: {list(cfg or {})})?"
        ),
    )
    try:
        client = get_client_from_ctx(ctx)
        channel = client.create_messaging_channel(
            channel_type=channel_type, channel_id=channel_id, channel_configuration=cfg
        )
        raw = getattr(channel, "_data", None) or getattr(channel, "raw", {})
        success(f"Created channel {raw.get('id', '') if isinstance(raw, dict) else ''}")
        hint("dku admin messaging list")
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
    guard(
        ctx,
        tier=Tier.DELETE,
        action="admin.infra.push-base-images",
        subject="container-exec base images to the configured registry",
        yes=yes,
        prompt=(
            "Push container-exec base images to the configured registry? Requires "
            "container-exec configured and valid registry credentials. Can take "
            "minutes. Safe to retry."
        ),
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
    guard(
        ctx,
        tier=Tier.DELETE,
        action="admin.infra.apply-k8s-policies",
        subject="Kubernetes namespace policies",
        yes=yes,
        prompt=(
            "Apply Kubernetes namespace policies? Reads namespace policies from "
            "DSS general settings and pushes them to the target cluster. Verify "
            "policies first with 'settings get'."
        ),
    )
    try:
        client = get_client_from_ctx(ctx)
        result = client.apply_kubernetes_namespaces_policies()
        render_raw(result or {"status": "ok"}, output_format="json")
    except Exception as e:
        handle_api_error(e)


# =============================================================================
# dku admin code-studio-template — list / get / build / set-dockerfile-append /
# list-blocks / add-block / remove-block / inspect-build
# =============================================================================

cst_app = typer.Typer(help="Code studio templates (admin visibility + lifecycle).")


@cst_app.command("list")
def cst_list(
    ctx: typer.Context,
) -> None:
    """List registered code studio templates."""
    fmt = resolve_output_format()
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


@cst_app.command("get")
def cst_get(
    ctx: typer.Context,
    template_id: str = typer.Argument(help="Template ID"),
) -> None:
    """Get full template settings as JSON.

    Returns the complete settings dict — including ``params.blocks[]`` with
    every block's type and params. Pipe through ``jq '.params.blocks[] | "\\(.type)"'``
    to enumerate block types.
    """
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        tpl = client.get_code_studio_template(template_id)
        settings = tpl.get_settings()
        render_raw(settings.get_raw(), output_format=fmt)
    except Exception as e:
        handle_api_error(e)


@cst_app.command("list-blocks")
def cst_list_blocks(
    ctx: typer.Context,
    template_id: str = typer.Argument(help="Template ID"),
) -> None:
    """List blocks (index, type, label) in a template.

    Plugin-defined blocks have type ``pycdstdioblk_<plugin>_<block>`` (with
    underscores between plugin and block IDs — NOT colons).
    """
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        raw = client.get_code_studio_template(template_id).get_settings().get_raw()
        blocks = raw.get("params", {}).get("blocks", []) or []
        data = []
        for i, b in enumerate(blocks):
            params = b.get("params", {}) or {}
            data.append(
                {
                    "index": i,
                    "type": b.get("type", ""),
                    "label": (
                        params.get("label")
                        or params.get("name")
                        or params.get("entrypoint", "")[:40]
                        or ""
                    ),
                }
            )
        render(
            data,
            ["index", "type", "label"],
            output_format=fmt,
            title=f"Blocks of {template_id}",
        )
    except Exception as e:
        handle_api_error(e)


@cst_app.command("set-dockerfile-append")
def cst_set_dockerfile(
    ctx: typer.Context,
    template_id: str = typer.Argument(help="Template ID"),
    dockerfile: str = typer.Option(
        ...,
        "--dockerfile",
        "-f",
        help="Dockerfile content (literal, @file, or - for stdin).",
    ),
) -> None:
    """Replace the ``append_dockerfile`` block's content on a template.

    Idempotent: PUT-only, no rebuild. Run ``dku admin code-studio-template
    build`` afterwards to actually rebuild the image.

    The template MUST already have an ``append_dockerfile`` block — this
    verb replaces, it does not insert. Use ``add-block`` to insert a fresh
    block when needed.
    """
    from dku_cli.helpers import read_text_input

    new_content = read_text_input(dockerfile)
    try:
        client = get_client_from_ctx(ctx)
        settings = client.get_code_studio_template(template_id).get_settings()
        raw = settings.get_raw()
        blocks = raw.get("params", {}).get("blocks", []) or []
        replaced = 0
        for b in blocks:
            if b.get("type") == "append_dockerfile":
                params = b.setdefault("params", {})
                params["dockerfile"] = new_content
                replaced += 1
        if replaced == 0:
            from dku_cli.errors import exit_with_error

            exit_with_error(
                f"Template '{template_id}' has no append_dockerfile block.",
                details=[
                    "Add one first via the DSS UI, or via "
                    "`dku admin code-studio-template add-block`:",
                    "",
                    f"  dku admin code-studio-template add-block {template_id} \\\\",
                    "    --type append_dockerfile --params '{}'",
                ],
                status=2,
            )
        settings.save()
        success(
            f"Replaced append_dockerfile block ({replaced} found) on '{template_id}' "
            f"({len(new_content)} bytes). Run 'build' to rebuild the image."
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@cst_app.command("add-block")
def cst_add_block(
    ctx: typer.Context,
    template_id: str = typer.Argument(help="Template ID"),
    block_type: str = typer.Option(
        ...,
        "--type",
        "-t",
        help="Block type. Built-ins: append_dockerfile, entrypoint, "
        "dss_base_image, simple_deployment. Plugin blocks use "
        "pycdstdioblk_<plugin>_<block> (underscores, NOT colons).",
    ),
    params_json: str = typer.Option(
        "{}",
        "--params",
        "-p",
        help="Block params JSON (string, @file.json, or - for stdin). Defaults to {}.",
    ),
    at: int = typer.Option(
        -1, "--at", help="Insert position (default -1 = append at end)."
    ),
) -> None:
    """Append (or insert) a block into a template's ``params.blocks[]``."""
    params = read_json_input(params_json)
    if params is None:
        params = {}
    block = {"type": block_type, "params": params}
    try:
        client = get_client_from_ctx(ctx)
        settings = client.get_code_studio_template(template_id).get_settings()
        raw = settings.get_raw()
        blocks = raw.setdefault("params", {}).setdefault("blocks", [])
        if at < 0 or at >= len(blocks):
            blocks.append(block)
            position = len(blocks) - 1
        else:
            blocks.insert(at, block)
            position = at
        settings.save()
        success(
            f"Added block type='{block_type}' at index {position} on '{template_id}'. "
            "Run 'build' to rebuild the image."
        )
    except Exception as e:
        handle_api_error(e)


@cst_app.command("remove-block")
def cst_remove_block(
    ctx: typer.Context,
    template_id: str = typer.Argument(help="Template ID"),
    index: int = typer.Option(
        ..., "--index", "-i", help="Block index to remove (zero-based)."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Remove a block from a template by index."""
    from dku_cli.safety import Tier, guard

    guard(
        ctx,
        tier=Tier.DELETE,
        action="code-studio-template.remove-block",
        subject=f"block #{index} of code studio template '{template_id}'",
        yes=yes,
        prompt=f"Remove block index {index} from template '{template_id}'?",
    )
    try:
        client = get_client_from_ctx(ctx)
        settings = client.get_code_studio_template(template_id).get_settings()
        raw = settings.get_raw()
        blocks = raw.get("params", {}).get("blocks", []) or []
        if index < 0 or index >= len(blocks):
            from dku_cli.errors import exit_with_error

            exit_with_error(
                f"Block index {index} out of range (template has {len(blocks)} block(s)).",
                details=[
                    f"List blocks: dku admin code-studio-template list-blocks {template_id}"
                ],
                status=2,
            )
        removed = blocks.pop(index)
        settings.save()
        success(
            f"Removed block index={index} type={removed.get('type', '?')!r} "
            f"from '{template_id}'."
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@cst_app.command("set-block-params")
def cst_set_block_params(
    ctx: typer.Context,
    template_id: str = typer.Argument(help="Template ID"),
    index: int = typer.Option(
        ..., "--index", "-i", help="Block index to edit (zero-based; see list-blocks)."
    ),
    params_json: str = typer.Option(
        ...,
        "--params",
        "-p",
        help="Params JSON (string, @file.json, or - for stdin).",
    ),
    replace: bool = typer.Option(
        False,
        "--replace",
        help="Overwrite the block's params wholesale. Default does a shallow "
        "MERGE so you can set one key (e.g. llmmesh_model) without "
        "clobbering the rest.",
    ),
) -> None:
    """Set params on an existing block in ``params.blocks[]``.

    Default is a shallow MERGE — the given keys are written over the block's
    current params, everything else is preserved (the common case: set
    ``llmmesh_model``/``webapp_port`` on a plugin block without re-sending the
    whole object). Pass ``--replace`` to swap the entire params object.
    PUT-only: run ``build`` afterwards to materialize the change as an image.
    """
    new_params = read_json_input(params_json)
    if not isinstance(new_params, dict):
        exit_with_error(
            "--params must be a JSON object.",
            details=['Example: --params \'{"llmmesh_model": "openai:gpt-4o"}\''],
            status=2,
        )
    try:
        client = get_client_from_ctx(ctx)
        settings = client.get_code_studio_template(template_id).get_settings()
        raw = settings.get_raw()
        blocks = raw.get("params", {}).get("blocks", []) or []
        if index < 0 or index >= len(blocks):
            exit_with_error(
                f"Block index {index} out of range "
                f"(template has {len(blocks)} block(s)).",
                details=[
                    f"List blocks: dku admin code-studio-template "
                    f"list-blocks {template_id}"
                ],
                status=2,
            )
        block = blocks[index]
        if replace:
            block["params"] = new_params
        else:
            block.setdefault("params", {}).update(new_params)
        settings.save()
        success(
            f"Updated params on block index={index} "
            f"type={block.get('type', '?')!r} of '{template_id}' "
            f"({'replaced' if replace else 'merged'} {len(new_params)} key(s)). "
            "Run 'build' to rebuild the image."
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@cst_app.command()
def build(
    ctx: typer.Context,
    template_id: str = typer.Argument(help="Template ID"),
    no_cache: bool = typer.Option(
        False, "--no-cache", help="Build with Docker --no-cache."
    ),
    wait: bool = typer.Option(
        False, "--wait", help="Wait for the build future to complete."
    ),
    timeout: int = typer.Option(
        1800, "--timeout", help="--wait timeout in seconds (default 1800)."
    ),
) -> None:
    """Trigger an image build for a template.

    Returns the build's jobId immediately. Pass ``--wait`` to poll until
    ``alive=False`` and then fetch the full result on the same tick (DSS
    GCs futures within seconds, so a delay loses the messages array).
    """
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        tpl = client.get_code_studio_template(template_id)
        future = tpl.build(disable_docker_cache=no_cache)
        job_id = getattr(future, "job_id", None) or getattr(future, "jobId", None)
        if not wait:
            payload = {"jobId": job_id, "template": template_id}
            if fmt == "json":
                render_raw(payload, output_format="json")
            else:
                success(f"Build triggered for '{template_id}' (jobId={job_id}).")
                info(
                    f"Wait via: dku admin code-studio-template build {template_id} --wait"
                )
            return

        # Wait loop: peek every 6s, fetch full result on the same tick alive flips.
        import time

        start = time.time()
        while True:
            peek = client._perform_json(
                "GET", f"/futures/{job_id}", params={"peek": "true"}
            )
            if not peek.get("alive", False):
                break
            if time.time() - start > timeout:
                from dku_cli.errors import exit_with_error

                exit_with_error(
                    f"Build for '{template_id}' did not finish within {timeout}s.",
                    details=[
                        "Future jobId: " + (job_id or "?"),
                        "The build is still running on DSS — check via the UI "
                        "or re-poll later. Increase --timeout if your image is large.",
                    ],
                    status=4,
                )
            time.sleep(6)

        full = client._perform_json("GET", f"/futures/{job_id}")
        has_result = bool(full.get("hasResult"))
        # The build outcome lives in result.messages (an InfoMessages with
        # authoritative error/fatal booleans) — NOT in top-level success/
        # messages keys, which the futures payload does not have. The build
        # thread never fails the future itself: Dockerfile and Docker errors
        # are only recorded here.
        result = full.get("result")
        result = result if isinstance(result, dict) else {}
        im = result.get("messages")
        im = im if isinstance(im, dict) else {}
        msgs = [m for m in (im.get("messages") or []) if isinstance(m, dict)]
        failed = bool(im.get("error") or im.get("fatal"))
        if fmt == "json":
            render_raw(full, output_format="json")
            if has_result and failed:
                raise typer.Exit(1)
            return

        if has_result and not failed:
            success(f"Build succeeded for '{template_id}' (jobId={job_id}).")
            return

        if has_result:
            error_msgs = [
                m
                for m in msgs
                if str(m.get("severity", "")).upper() == "ERROR" or m.get("isFatal")
            ]
            from dku_cli.output import error as render_error

            render_error(f"Build FAILED for '{template_id}' (jobId={job_id}).")
            for m in (error_msgs or msgs)[-5:]:
                info(f"  [{m.get('severity', '?')}] {m.get('message', m)}")
            raise typer.Exit(1)

        # No result at all: the future was GC'd before we could fetch it (DSS
        # collects finished futures within seconds — multi-config layer-cache
        # hits make sub-second builds especially prone to this). Ambiguous,
        # don't cry wolf.
        warn(
            f"Build future for '{template_id}' finished but returned no result "
            "(likely GC'd before fetch) — the outcome is unknown, NOT "
            "necessarily a failure."
        )
        info(
            "Verify the actual image state: "
            f"dku admin code-studio-template inspect-build {template_id}"
        )
        info(
            "If the expected images are present, the build succeeded. Re-run "
            "with --no-cache for an unambiguous result."
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@cst_app.command("inspect-build")
def cst_inspect_build(
    ctx: typer.Context,
    template_id: str = typer.Argument(help="Template ID"),
) -> None:
    """Show last-build metadata: container configs, last-built timestamp,
    and the live image arch via ``docker image inspect`` if reachable.

    Designed to answer "did I just build an arm64 image on an amd64 node?"
    without dropping out of the CLI. The Docker probe is best-effort —
    if Docker isn't on PATH or doesn't see the image, only DSS-side fields
    are reported.
    """
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        raw = client.get_code_studio_template(template_id).get_settings().get_raw()
    except Exception as e:
        handle_api_error(e)
        return

    info_dict: dict[str, object] = {
        "id": raw.get("id"),
        "label": raw.get("label"),
        "type": raw.get("type"),
        "allContainerConfs": raw.get("allContainerConfs"),
        "containerConfs": raw.get("containerConfs", []),
    }

    # Probe local docker for image arch (best-effort) — but ONLY when the
    # active profile targets this machine. If the build ran on a remote DSS
    # node, the image lives on THAT host's docker daemon, never here, so a
    # local probe is guaranteed to miss and the "not found" line is misleading.
    image_probe: dict[str, object] = {}
    remote = _is_remote_host(client.host)
    if remote:
        info_dict["dockerImage"] = (
            "local docker check skipped — image built on remote instance "
            "(verify via last_built / images-built.json on the instance)"
        )
    else:
        import shutil
        import subprocess

        docker_bin = shutil.which("docker")
        if docker_bin:
            # DSS-built CS image tags follow the pattern dku-kub-<template>:<conf>.
            # We probe a few tag variants — first match wins.
            candidates = [
                f"dku-kub-{template_id}:dss-dev_doesnotmatter",
                f"dku-kub-{template_id}:latest",
            ]
            for tag in candidates:
                try:
                    proc = subprocess.run(
                        [
                            docker_bin,
                            "image",
                            "inspect",
                            tag,
                            "--format",
                            "{{.Os}}/{{.Architecture}}",
                        ],
                        capture_output=True,
                        timeout=5,
                        text=True,
                        stdin=subprocess.DEVNULL,
                    )
                    if proc.returncode == 0 and proc.stdout.strip():
                        image_probe = {
                            "tag": tag,
                            "platform": proc.stdout.strip(),
                        }
                        break
                except (subprocess.TimeoutExpired, OSError):
                    continue
        info_dict["dockerImage"] = image_probe or "not found via local docker"

    if fmt == "json":
        render_raw(info_dict, output_format="json")
        return

    from rich.console import Console

    console = Console()
    console.print(f"[bold]{template_id}[/bold] — {raw.get('label', '')}")
    console.print(
        f"  type:                   {raw.get('type', '?')}\n"
        f"  allContainerConfs:      {raw.get('allContainerConfs', '?')}\n"
        f"  containerConfs:         {raw.get('containerConfs', [])}\n"
        f"  blocks:                 {len(raw.get('params', {}).get('blocks', []))}"
    )
    if image_probe:
        console.print(
            f"  dockerImage:            {image_probe['tag']} "
            f"({image_probe['platform']})"
        )
    elif remote:
        console.print(
            "  dockerImage:            local docker check skipped — image "
            "built on remote instance\n"
            "                          (verify via last_built / "
            "images-built.json on the instance)"
        )
    else:
        console.print("  dockerImage:            not found via local docker")


# =============================================================================
# Namespace redirects — `connection` and `code-env` are TOP-LEVEL groups, not
# admin sub-commands. Agents keep typing `dku admin connection ...` /
# `dku admin code-env ...` and used to hit a bare "No such command". Capture
# those nouns here and emit a prescriptive redirect to the real group instead
# of dead-ending. Extra args are swallowed so `dku admin connection list`
# (and any verb/flags after it) is captured rather than parsed.
# =============================================================================


def _emit_namespace_redirect(noun: str, extra: list[str]) -> None:
    """Print the top-level group an admin-prefixed noun really belongs to."""
    verb = " ".join(extra) if extra else "<verb>"
    example = f"dku {noun} {extra[0] if extra else 'list'}"
    exit_with_error(
        f"`{noun}` is a top-level group, not an `admin` sub-command.",
        details=[
            f"Drop `admin` — run: dku {noun} {verb}",
            f"e.g. {example}",
            f"See all verbs: dku {noun} --help",
        ],
    )


@app.command(
    "connection",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def _redirect_connection(ctx: typer.Context) -> None:
    """`connection` is a TOP-LEVEL group — use `dku connection ...`."""
    _emit_namespace_redirect("connection", ctx.args)


@app.command(
    "code-env",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def _redirect_code_env(ctx: typer.Context) -> None:
    """`code-env` is a TOP-LEVEL group — use `dku code-env ...`."""
    _emit_namespace_redirect("code-env", ctx.args)


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
) -> None:
    """List all LLM cost-limiting counters and their current state.

    Counter quotas (limits, period, scope) are configured in the UI only —
    the SDK exposes read access. Use this to monitor how close projects /
    users / LLMs are to their caps.
    """
    fmt = resolve_output_format()
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
) -> None:
    """Size of instance-wide directories (code envs, plugins, libs)."""
    fmt = resolve_output_format()
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
) -> None:
    """Size of a single project's owned directories."""
    fmt = resolve_output_format()
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
) -> None:
    """Size of ALL DSS data directories (global + all projects). Can be slow."""
    fmt = resolve_output_format()
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
) -> None:
    """Directories in the data root that don't belong to DSS (leaked data)."""
    fmt = resolve_output_format()
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
        )
    if mode not in {"FULL", "INCREMENTAL"}:
        exit_with_error(
            f"--mode must be FULL or INCREMENTAL, got '{mode}'.",
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
) -> None:
    """List enterprise asset collections."""
    fmt = resolve_output_format()
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
) -> None:
    """List enterprise prompts (optionally filtered by collection)."""
    fmt = resolve_output_format()
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
