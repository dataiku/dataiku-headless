"""dku api-key — list, get, create, delete for global API key management."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx
from dku_cli.output import info, render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS global API keys (admin only).")


@app.command("list")
def list_keys(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List all global API keys."""
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        keys = client.list_global_api_keys()

        data = []
        for k in keys:
            data.append(
                {
                    "id": k.get("id", ""),
                    "label": k.get("label", ""),
                    "created_by": k.get("createdBy", ""),
                }
            )

        if fmt == "json":
            render_raw(data, output_format="json")
        else:
            if not data:
                info("No global API keys found.")
                return
            render(
                data,
                ["id", "label", "created_by"],
                output_format=fmt,
                title="Global API Keys",
                headers={"id": "ID", "label": "LABEL", "created_by": "CREATED BY"},
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    key_id: str = typer.Argument(help="API key ID"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get an API key's definition."""
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        key = client.get_global_api_key_by_id(key_id)
        definition = key.get_definition()
        render_raw(dict(definition), output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    label: str = typer.Option(..., "--label", "-l", help="Label for the API key"),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Description"
    ),
    admin: bool = typer.Option(False, "--admin", help="Grant admin rights"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Create a new global API key.

    Example:
      dku api-key create --label "CI/CD Key" --description "For automation"
      dku api-key create --label "Admin Key" --admin
    """
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        key = client.create_global_api_key(
            label=label, description=description, admin=admin
        )

        if fmt == "json":
            render_raw(
                {"id": key.id_, "key": key.key, "label": label},
                output_format="json",
            )
        else:
            success(f"Created API key '{label}' (ID: {key.id_})")
            info(f"Secret key: {key.key}")
            info("Store this key securely — it cannot be retrieved later.")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    key_id: str = typer.Argument(help="API key ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a global API key."""
    if not yes:
        confirm = typer.confirm(f"Delete API key '{key_id}'?")
        if not confirm:
            raise typer.Abort()
    try:
        client = get_client_from_ctx(ctx)
        key = client.get_global_api_key_by_id(key_id)
        key.delete()
        success(f"Deleted API key '{key_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("list-personal")
def list_personal(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List personal API keys visible to the caller (admin sees all).

    Useful for auditing keys before an offboarding or key-rotation sweep.
    """
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        keys = client.list_personal_api_keys(as_type="listitems")
        data = []
        for k in keys:
            raw = k if isinstance(k, dict) else getattr(k, "_data", {}) or {}
            data.append(
                {
                    "id": raw.get("id", ""),
                    "user": raw.get("user", ""),
                    "label": raw.get("label", ""),
                    "created": raw.get("createdOn", ""),
                }
            )
        if fmt == "json":
            render_raw(data, output_format="json")
            return
        if not data:
            info("No personal API keys.")
            return
        render(
            data,
            ["id", "user", "label", "created"],
            output_format=fmt,
            title="Personal API Keys",
        )
    except Exception as e:
        handle_api_error(e)
