"""dku cluster — list, get, create, start, stop, status, delete for cluster management."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx
from dku_cli.output import (
    hint,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
)

app = typer.Typer(help="Manage DSS clusters (admin only).")


@app.command("list")
def list_clusters(
    ctx: typer.Context,
) -> None:
    """List all clusters."""
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        clusters = client.list_clusters()

        if fmt == "json":
            render_raw(clusters, output_format="json")
        else:
            if not clusters:
                info("No clusters configured.")
                return
            data = []
            for c in clusters:
                data.append(
                    {
                        "name": c.get("name", ""),
                        "type": c.get("type", ""),
                        "state": c.get("state", ""),
                        "architecture": c.get("architecture", ""),
                    }
                )
            render(
                data,
                ["name", "type", "state", "architecture"],
                output_format=fmt,
                title="Clusters",
                headers={
                    "name": "NAME",
                    "type": "TYPE",
                    "state": "STATE",
                    "architecture": "ARCH",
                },
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    cluster_id: str = typer.Argument(help="Cluster ID/name"),
) -> None:
    """Get cluster settings."""
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        cluster = client.get_cluster(cluster_id)
        settings = cluster.get_settings()
        render_raw(settings.get_raw(), output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Cluster name"),
    cluster_type: str = typer.Option(
        "manual", "--type", "-t", help="Cluster type (manual, or plugin type)"
    ),
    architecture: str = typer.Option(
        "KUBERNETES",
        "--arch",
        help="Architecture: HADOOP or KUBERNETES",
    ),
) -> None:
    """Create a new cluster.

    Example:
      dku cluster create my-k8s --type manual --arch KUBERNETES
    """
    try:
        client = get_client_from_ctx(ctx)
        client.create_cluster(
            name, cluster_type=cluster_type, cluster_architecture=architecture
        )
        success(
            f"Created cluster '{name}' (type: {cluster_type}, arch: {architecture})"
        )
        hint(f"dku cluster get {name}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def start(
    ctx: typer.Context,
    cluster_id: str = typer.Argument(help="Cluster ID/name"),
) -> None:
    """Start or attach a managed cluster.

    Example:
      dku cluster start my-k8s
    """
    try:
        client = get_client_from_ctx(ctx)
        cluster = client.get_cluster(cluster_id)
        cluster.start()
        success(f"Started cluster '{cluster_id}'")
        hint(f"dku cluster status {cluster_id}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def stop(
    ctx: typer.Context,
    cluster_id: str = typer.Argument(help="Cluster ID/name"),
    terminate: bool = typer.Option(
        True, "--terminate/--no-terminate", help="Delete cluster after stopping"
    ),
) -> None:
    """Stop or detach a managed cluster.

    Example:
      dku cluster stop my-k8s
      dku cluster stop my-k8s --no-terminate
    """
    try:
        client = get_client_from_ctx(ctx)
        cluster = client.get_cluster(cluster_id)
        cluster.stop(terminate=terminate)
        action = "Stopped and terminated" if terminate else "Stopped"
        success(f"{action} cluster '{cluster_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def status(
    ctx: typer.Context,
    cluster_id: str = typer.Argument(help="Cluster ID/name"),
) -> None:
    """Get cluster status and usage.

    Example:
      dku cluster status my-k8s
    """
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        cluster = client.get_cluster(cluster_id)
        st = cluster.get_status()
        raw = st.get_raw()

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
                title=f"Cluster Status: {cluster_id}",
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    cluster_id: str = typer.Argument(help="Cluster ID/name"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a cluster (does not stop it first)."""
    from dku_cli.safety import Tier, guard

    guard(
        ctx,
        tier=Tier.DELETE,
        action="cluster.delete",
        subject=f"cluster '{cluster_id}'",
        yes=yes,
        prompt=f"Delete cluster '{cluster_id}'? (This does not stop the cluster first.)",
    )
    try:
        client = get_client_from_ctx(ctx)
        cluster = client.get_cluster(cluster_id)
        cluster.delete()
        success(f"Deleted cluster '{cluster_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
