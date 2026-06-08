"""dku govern artifact — list (search), get, create, delete, set-definition."""

from __future__ import annotations

import re
from typing import Optional

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import get_govern_client_from_ctx, read_json_input
from dku_cli.output import render, render_raw, resolve_output_format, success
from dku_cli.safety import Tier, guard

app = typer.Typer(
    help="Manage Govern artifacts. Use 'govern blueprint fields' to discover field schemas."
)

_AR_ID_RE = re.compile(r"^ar\.\d+$")


def _get_version_field_defs(govern, blueprint_id: str, version_id: str) -> dict:
    """Fetch fieldDefinitions for a blueprint version. Returns {} on any failure."""
    try:
        bp = govern.get_blueprint(blueprint_id)
        version = bp.get_version(version_id)
        defn = version.get_definition()
        return defn.get_raw().get("fieldDefinitions", {}) or {}
    except Exception:
        return {}


def _validate_reference_fields(
    field_defs: dict,
    fields_dict: dict,
) -> None:
    """Catch REFERENCE fields set to non-artifact-ID values before POST.

    The Govern server rejects bad REFERENCE values with a flat validation error
    that doesn't explain the expected shape, so agents typically waste a round
    trying logins/names. This helper turns the failure into a prescriptive
    error pointing at `dku govern artifact list --blueprint <allowed_bp>`.
    """
    if not field_defs:
        return  # Couldn't fetch schema — let the server validate

    problems: list[tuple[str, object, list[str]]] = []
    for key, value in fields_dict.items():
        fd = field_defs.get(key)
        if not fd or fd.get("fieldType") != "REFERENCE":
            continue
        if fd.get("sourceType") == "COMPUTE":
            continue  # computed references are backend-managed

        allowed = fd.get("allowedBlueprints") or []
        values = value if isinstance(value, list) else [value]
        for v in values:
            if v is None or (isinstance(v, str) and v == ""):
                continue
            if not isinstance(v, str) or not _AR_ID_RE.match(v):
                problems.append((key, v, allowed))

    if not problems:
        return

    first_key, first_val, first_allowed = problems[0]
    details: list[str] = [
        f"Got: {first_val!r}",
        "REFERENCE field values must be artifact IDs in the form 'ar.<number>'.",
        "",
    ]
    if first_allowed:
        details.append(f"Allowed blueprints: {', '.join(first_allowed)}")
        details.append("Find candidate artifact IDs with:")
        for bp_ref in first_allowed:
            details.append(f"  dku govern artifact list --blueprint {bp_ref}")
        details.append("")
    if len(problems) > 1:
        details.append(
            f"({len(problems) - 1} more invalid REFERENCE value(s) on this artifact.)"
        )
        details.append(
            "Run 'dku govern blueprint fields <BP_ID>' to see all REFERENCE fields and their allowed blueprints."
        )

    exit_with_error(
        f"REFERENCE field '{first_key}' expects an artifact ID, not {first_val!r}.",
        code="invalid_reference_value",
        details=details,
    )


@app.command("list")
def list_artifacts(
    ctx: typer.Context,
    blueprint: Optional[str] = typer.Option(
        None, "--blueprint", "-b", help="Filter by blueprint ID"
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="Filter by artifact name (contains, case-insensitive)",
    ),
    archived: Optional[bool] = typer.Option(
        None, "--archived/--no-archived", help="Filter by archived status"
    ),
    page_size: int = typer.Option(
        50, "--page-size", help="Results per page (default 50)"
    ),
    all_pages: bool = typer.Option(
        False, "--all", "-a", help="Fetch all pages (not just the first)"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Search and list Govern artifacts."""
    from dataikuapi.govern.artifact_search import (
        GovernArtifactFilterArchivedStatus,
        GovernArtifactFilterBlueprints,
        GovernArtifactFilterFieldValue,
        GovernArtifactSearchQuery,
        GovernArtifactSearchSourceAll,
    )

    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)

        query = GovernArtifactSearchQuery()
        query.set_artifact_search_source(GovernArtifactSearchSourceAll())

        if blueprint:
            query.add_artifact_filter(GovernArtifactFilterBlueprints([blueprint]))
        if archived is not None:
            query.add_artifact_filter(GovernArtifactFilterArchivedStatus(archived))
        if name:
            query.add_artifact_filter(
                GovernArtifactFilterFieldValue(
                    "CONTAINS", condition=name, case_sensitive=False
                )
            )

        req = govern.new_artifact_search_request(query)

        data = []
        while True:
            resp = req.fetch_next_batch(page_size=page_size)
            hits = resp.get_response_hits()
            if not hits:
                break

            for hit in hits:
                raw = hit.get_raw()
                art = raw.get("artifact", raw)
                bp_ver = art.get("blueprintVersionId", {})
                data.append(
                    {
                        "id": art.get("id", ""),
                        "name": art.get("name", ""),
                        "blueprint": bp_ver.get("blueprintId", ""),
                        "archived": str(art.get("status", {}).get("archived", False)),
                    }
                )

            if not all_pages:
                break

        render(
            data,
            ["id", "name", "blueprint", "archived"],
            output_format=output,
            title="Govern Artifacts",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="Artifact ID (e.g. ar.5)"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get an artifact definition."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        art = govern.get_artifact(artifact_id)
        defn = art.get_definition()
        render_raw(defn.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    blueprint: Optional[str] = typer.Option(
        None,
        "--blueprint",
        "-b",
        help="Blueprint ID (e.g. bp.system.govern_project). Auto-resolves active version.",
    ),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Artifact name"),
    field: Optional[list[str]] = typer.Option(
        None,
        "--field",
        "-f",
        help='Set a field: key=value. Repeat for multiple fields. Lists: key=["a","b"].',
    ),
    definition: Optional[str] = typer.Option(
        None,
        "--definition",
        help="Full artifact JSON (string, @file.json, or - for stdin). Overrides --blueprint/--name/--field.",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Create a new Govern artifact.

    Two modes:

    1) Ergonomic: --blueprint + --name + --field flags (no JSON needed)

       dku govern artifact create -b bp.system.govern_project -n "My Project" -f description="A project" -f cost_rating=High

    2) Raw JSON: --definition for full control

       dku govern artifact create --definition @artifact.json

    DATE fields: use ISO 8601 strings ("2025-01-15T00:00:00.000Z").
    REFERENCE fields: use artifact IDs ("ar.123").
    List fields: use JSON arrays ('["val1","val2"]') or repeat --field for the same key.
    Run 'dku govern blueprint fields <BLUEPRINT_ID>' to see available fields.
    """
    import json as json_mod

    output = resolve_output_format(output)

    if definition is None and blueprint is None:
        exit_with_error(
            "Either --blueprint or --definition is required.",
            code="missing_argument",
            details=[
                "Ergonomic: dku govern artifact create -b bp.system.govern_project -n 'Name' -f key=value",
                "Raw JSON:  dku govern artifact create --definition '{...}'",
                "Run: dku govern blueprint list to see available blueprints.",
            ],
        )

    try:
        govern = get_govern_client_from_ctx(ctx)

        if definition is not None:
            artifact_data = read_json_input(definition)
            # Validate REFERENCE fields on raw-JSON path too
            if isinstance(artifact_data, dict):
                bv = artifact_data.get("blueprintVersionId") or {}
                bp_id = bv.get("blueprintId")
                ver_id = bv.get("versionId")
                fields_dict = artifact_data.get("fields") or {}
                if bp_id and ver_id and isinstance(fields_dict, dict):
                    field_defs = _get_version_field_defs(govern, bp_id, ver_id)
                    _validate_reference_fields(field_defs, fields_dict)
        else:
            # Build artifact from --blueprint, --name, --field
            from dku_cli.commands.govern_blueprint import _resolve_active_version

            version_id = _resolve_active_version(govern, blueprint)
            fields_dict = {}
            for f in field or []:
                eq_idx = f.find("=")
                if eq_idx < 1:
                    raise typer.BadParameter(
                        f"Invalid --field format: '{f}'. Use key=value."
                    )
                k, v = f[:eq_idx], f[eq_idx + 1 :]
                # Try parsing as JSON for arrays/numbers/booleans
                try:
                    parsed = json_mod.loads(v)
                    # If key already exists, merge arrays
                    if k in fields_dict and isinstance(fields_dict[k], list):
                        if isinstance(parsed, list):
                            fields_dict[k].extend(parsed)
                        else:
                            fields_dict[k].append(parsed)
                    else:
                        fields_dict[k] = parsed
                except (json_mod.JSONDecodeError, ValueError):
                    fields_dict[k] = v

            # Prescriptive REFERENCE-field validation before POST
            field_defs = _get_version_field_defs(govern, blueprint, version_id)
            _validate_reference_fields(field_defs, fields_dict)

            artifact_data = {
                "blueprintVersionId": {
                    "blueprintId": blueprint,
                    "versionId": version_id,
                },
                "name": name or "",
                "fields": fields_dict,
            }

        art = govern.create_artifact(artifact_data)
        success(f"Created artifact '{art.artifact_id}'")
        defn = art.get_definition()
        render_raw(defn.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="Artifact ID"),
    confirm: bool = typer.Option(
        False, "--confirm", "--yes", "-y", help="Confirm deletion (required)"
    ),
) -> None:
    """Delete a Govern artifact. Requires --confirm / --yes flag."""
    guard(
        ctx,
        tier=Tier.DELETE,
        action="govern.artifact.delete",
        subject=f"artifact '{artifact_id}'",
        yes=confirm,
        prompt=f"Delete Govern artifact '{artifact_id}'?",
    )
    try:
        govern = get_govern_client_from_ctx(ctx)
        art = govern.get_artifact(artifact_id)
        art.delete()
        success(f"Deleted artifact '{artifact_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-field")
def set_field(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="Artifact ID (e.g. ar.5)"),
    field_id: str = typer.Argument(help="Field ID (e.g. description, cost_rating)"),
    value: str = typer.Argument(
        help='Field value. Plain string, JSON array (\'["a","b"]\'), or number.'
    ),
) -> None:
    """Set a single field on an artifact without replacing the full definition.

    Examples:
      dku govern artifact set-field ar.5 description "New description"
      dku govern artifact set-field ar.5 cost_rating High
      dku govern artifact set-field ar.5 countries '["France","Germany"]'
      dku govern artifact set-field ar.5 business_initiative ar.10

    DATE fields: use ISO 8601 strings ("2025-01-15T00:00:00.000Z").
    List fields: use JSON arrays. Run 'dku govern blueprint fields' to check.
    """
    import json as json_mod

    try:
        govern = get_govern_client_from_ctx(ctx)
        art = govern.get_artifact(artifact_id)
        defn = art.get_definition()
        raw = defn.get_raw()

        # Parse value: try JSON first (for arrays, numbers, booleans)
        try:
            parsed = json_mod.loads(value)
        except (json_mod.JSONDecodeError, ValueError):
            parsed = value

        # Prescriptive REFERENCE-field validation
        bv = raw.get("blueprintVersionId") or {}
        bp_id = bv.get("blueprintId")
        ver_id = bv.get("versionId")
        if bp_id and ver_id:
            field_defs = _get_version_field_defs(govern, bp_id, ver_id)
            _validate_reference_fields(field_defs, {field_id: parsed})

        raw.setdefault("fields", {})[field_id] = parsed
        defn.definition = raw
        defn.save()
        success(f"Set '{field_id}' on artifact '{artifact_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="Artifact ID"),
    definition: str = typer.Option(
        ...,
        "--definition",
        help="New definition JSON (string, @file.json, or - for stdin)",
    ),
) -> None:
    """Update an artifact definition from JSON. Use set-field for single field updates."""
    try:
        govern = get_govern_client_from_ctx(ctx)
        new_def = read_json_input(definition)
        art = govern.get_artifact(artifact_id)
        defn = art.get_definition()
        # GovernArtifactDefinition stores the raw dict internally and save() PUTs it
        defn.definition = new_def
        defn.save()
        success(f"Updated definition for artifact '{artifact_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
