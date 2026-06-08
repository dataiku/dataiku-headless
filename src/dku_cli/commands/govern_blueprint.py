"""dku govern blueprint — blueprint + version designer and signoff config."""

from __future__ import annotations

from typing import Optional

import typer

from dku_cli.commands._govern_blueprint_describe import (
    _build_field_rows,
    _build_signoff_rows as _build_signoff_rows,
    _build_step_rows,
    _build_view_rows,
    _describe_version_warnings,
    _lint_version_definition,
    _load_signoff_rows,
    _resolve_blueprint_name,
    _resolve_version_status,
    _workflow_steps,
)
from dku_cli.enums import (
    BlueprintStatus,
    MigrationBehavior,
    SignoffImportRole,
)
from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import get_govern_client_from_ctx, read_json_input
from dku_cli.output import (
    console,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)
from dku_cli.safety import Tier, guard

app = typer.Typer(
    help="Manage Govern blueprints. Use 'fields' subcommand to discover field schemas for artifact creation."
)


@app.command("list")
def list_blueprints(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List all Govern blueprints."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        blueprints = govern.list_blueprints()
        data = []
        for item in blueprints:
            raw = item.get_raw()
            bp = raw.get("blueprint", raw)
            data.append(
                {
                    "id": bp.get("id", ""),
                    "name": bp.get("name", ""),
                    "icon": bp.get("icon", ""),
                }
            )
        render(
            data,
            ["id", "name", "icon"],
            output_format=output,
            title="Govern Blueprints",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(
        help="Blueprint ID (e.g. bp.system.govern_project)"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get a blueprint definition."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        bp = govern.get_blueprint(blueprint_id)
        defn = bp.get_definition()
        render_raw(defn.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("list-versions")
def list_versions(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(help="Blueprint ID"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List all versions of a blueprint, including DRAFT and ARCHIVED.

    Uses the admin designer path so authoring workflows can see DRAFT versions.
    The non-admin /blueprint/{id}/versions endpoint hides DRAFTs.
    """
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        designer = govern.get_blueprint_designer()
        bp = designer.get_blueprint(blueprint_id)
        versions = bp.list_versions()
        data = []
        for item in versions:
            raw = item.get_raw()
            bv = raw.get("blueprintVersion", raw)
            vid = bv.get("id", {})
            trace = raw.get("blueprintVersionTrace", {})
            data.append(
                {
                    "version_id": vid.get("versionId", "")
                    if isinstance(vid, dict)
                    else str(vid),
                    "name": bv.get("name", ""),
                    "status": trace.get("status", ""),
                }
            )
        render(
            data,
            ["version_id", "name", "status"],
            output_format=output,
            title=f"Versions of {blueprint_id}",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("get-version")
@app.command("get-version-definition")
def get_version(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(help="Blueprint ID"),
    version_id: str = typer.Argument(help="Version ID (e.g. bv.system.default)"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get a blueprint version definition.

    Both `get-version` and `get-version-definition` resolve to this command —
    the longer name mirrors `set-version-definition` for symmetry.
    """
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        bp = govern.get_blueprint(blueprint_id)
        ver = bp.get_version(version_id)
        defn = ver.get_definition()
        render_raw(defn.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("describe-version")
def describe_version(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(help="Blueprint ID"),
    version_id: str = typer.Argument(help="Version ID (e.g. bv.v1)"),
) -> None:
    """Pretty-print a blueprint version: fields, workflow, signoffs, views, and structural warnings.

    Use this instead of `get-version | jq` when authoring or auditing a
    blueprint — the tables are easier to scan and the bottom of the output
    flags structural bugs (empty views, missing artifactPageViewId, fields not
    in any view, signoffs on non-existent steps, etc.) that the Govern API
    silently accepts but break the UI.
    """
    try:
        govern = get_govern_client_from_ctx(ctx)
        designer = govern.get_blueprint_designer()
        bp = designer.get_blueprint(blueprint_id)
        version = bp.get_version(version_id)
        defn = version.get_definition()
        raw = defn.get_raw()
        status = _resolve_version_status(bp, version_id)

        # Header
        bp_name = _resolve_blueprint_name(bp)
        console.print(
            f"[bold]Blueprint:[/bold] [cyan]{blueprint_id}[/cyan] — {bp_name}"
        )
        console.print(
            f"[bold]Version:[/bold] [cyan]{version_id}[/cyan] — [magenta]{status}[/magenta]"
        )
        console.print()

        # Fields
        field_rows = _build_field_rows(raw)
        render(
            field_rows,
            ["id", "label", "type", "source", "list", "required", "categories"],
            output_format="table",
            title=f"Fields ({len(field_rows)})",
            headers={
                "id": "ID",
                "label": "LABEL",
                "type": "TYPE",
                "source": "SRC",
                "list": "LIST",
                "required": "REQ",
                "categories": "CATEGORIES",
            },
        )

        # Workflow steps
        steps, initial_id = _workflow_steps(raw)
        step_rows = _build_step_rows(steps, initial_id)
        render(
            step_rows,
            ["id", "name", "initial"],
            output_format="table",
            title=f"Workflow steps ({len(step_rows)})",
            headers={"id": "STEP ID", "name": "NAME", "initial": "INIT"},
        )

        # Signoffs
        signoff_rows = _load_signoff_rows(version)
        render(
            signoff_rows,
            [
                "step",
                "title",
                "mandatory",
                "approvers",
                "approver_types",
                "feedback_groups",
            ],
            output_format="table",
            title=f"Signoffs ({len(signoff_rows)})",
            headers={
                "step": "STEP ID",
                "title": "TITLE",
                "mandatory": "REQ",
                "approvers": "#APPROVERS",
                "approver_types": "APPROVER TYPES",
                "feedback_groups": "#GROUPS",
            },
        )

        # Views
        view_rows = _build_view_rows(raw)
        render(
            view_rows,
            ["id", "label", "components", "is_artifact_page", "used_by_steps"],
            output_format="table",
            title=f"Views ({len(view_rows)})",
            headers={
                "id": "VIEW ID",
                "label": "LABEL",
                "components": "#COMPONENTS",
                "is_artifact_page": "MAIN",
                "used_by_steps": "USED BY STEPS",
            },
        )

        # Structural warnings — the whole point of this command. Catches the
        # silent-failure patterns the Govern API will accept but render broken.
        # Most rules live in the shared _lint_version_definition helper so
        # set-version-definition can reuse them on push. The signoff-step
        # check stays here because it depends on a separate live API call.
        valid_step_ids = {step.get("id", "") for step in steps if step.get("id")}
        warnings = _describe_version_warnings(raw, valid_step_ids, signoff_rows)

        console.print()
        if warnings:
            console.print("[bold yellow]Structural warnings:[/bold yellow]")
            for w in warnings:
                warn(w)
        else:
            success("No structural issues detected.")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


def _resolve_active_version(govern, blueprint_id: str) -> str:
    """Find the ACTIVE version ID for a blueprint, falling back to the first version."""
    bp = govern.get_blueprint(blueprint_id)
    versions = bp.list_versions()
    for item in versions:
        raw = item.get_raw()
        trace = raw.get("blueprintVersionTrace", {})
        if trace.get("status") == "ACTIVE":
            bv = raw.get("blueprintVersion", raw)
            vid = bv.get("id", {})
            return vid.get("versionId", "") if isinstance(vid, dict) else str(vid)
    # Fallback: first version
    if versions:
        raw = versions[0].get_raw()
        bv = raw.get("blueprintVersion", raw)
        vid = bv.get("id", {})
        return vid.get("versionId", "") if isinstance(vid, dict) else str(vid)
    return "bv.system.default"


@app.command()
def fields(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(
        help="Blueprint ID (e.g. bp.system.govern_project)"
    ),
    version_id: Optional[str] = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List fields for a blueprint with type, list/scalar, required, and valid categories.

    Shows the field schema agents and scripts need to construct artifact definitions.
    DATE fields accept ISO 8601 strings (e.g. "2025-01-15T00:00:00.000Z").
    REFERENCE fields accept artifact IDs (e.g. "ar.123").
    List fields (marked with * in LIST column) must be JSON arrays, even for a single value.
    """
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        if not version_id:
            version_id = _resolve_active_version(govern, blueprint_id)
        bp = govern.get_blueprint(blueprint_id)
        ver = bp.get_version(version_id)
        defn = ver.get_definition()
        raw = defn.get_raw()
        field_defs = raw.get("fieldDefinitions", {})

        data = []
        for field_id, fd in field_defs.items():
            is_list = "listConfig" in fd
            source = fd.get("sourceType", "")
            # Skip COMPUTE fields — agents can't set them
            if source == "COMPUTE":
                continue
            categories = fd.get("categories", [])
            if categories:
                if output == "json":
                    cat_display = ", ".join(categories)
                elif len(categories) > 10:
                    cat_display = (
                        ", ".join(categories[:10]) + f" ... ({len(categories)} total)"
                    )
                else:
                    cat_display = ", ".join(categories)
            else:
                cat_display = ""
            allowed_bps = fd.get("allowedBlueprints", [])
            if allowed_bps and not cat_display:
                cat_display = "refs: " + ", ".join(allowed_bps)
            data.append(
                {
                    "field": field_id,
                    "type": fd.get("fieldType", ""),
                    "list": "*" if is_list else "",
                    "required": "*" if fd.get("required") else "",
                    "label": fd.get("label", ""),
                    "values": cat_display,
                }
            )

        render(
            data,
            ["field", "type", "list", "required", "label", "values"],
            output_format=output,
            title=f"Fields for {blueprint_id} ({version_id})",
            headers={
                "field": "FIELD ID",
                "type": "TYPE",
                "list": "LIST",
                "required": "REQ",
                "label": "LABEL",
                "values": "CATEGORIES / ALLOWED REFS",
            },
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    identifier: str = typer.Argument(
        help="New blueprint identifier (letters, digits, hyphen, underscore)"
    ),
    definition: str = typer.Option(
        ...,
        "--definition",
        help="Blueprint definition JSON (string, @file.json, or - for stdin)",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Create a new blueprint (admin/architect). Provide definition as JSON."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        designer = govern.get_blueprint_designer()
        bp_data = read_json_input(definition)
        bp = designer.create_blueprint(identifier, bp_data)
        defn = bp.get_definition()
        success(f"Created blueprint '{bp.blueprint_id}'")
        render_raw(defn.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(help="Blueprint ID"),
    definition: str = typer.Option(
        ...,
        "--definition",
        help="New blueprint definition JSON (string, @file.json, or - for stdin)",
    ),
) -> None:
    """Update a blueprint definition (admin/architect)."""
    try:
        govern = get_govern_client_from_ctx(ctx)
        designer = govern.get_blueprint_designer()
        bp = designer.get_blueprint(blueprint_id)
        defn = bp.get_definition()
        new_def = read_json_input(definition)
        defn.definition = new_def
        defn.save()
        success(f"Updated definition for blueprint '{blueprint_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(help="Blueprint ID (e.g. bp.custom_bp)"),
    confirm: bool = typer.Option(
        False, "--confirm", "--yes", "-y", help="Confirm deletion (required)"
    ),
) -> None:
    """Delete a blueprint (admin/architect). All versions and artifacts must be deleted first."""
    guard(
        ctx,
        tier=Tier.DELETE,
        action="govern.blueprint.delete",
        subject=f"blueprint '{blueprint_id}'",
        yes=confirm,
        prompt=f"Delete Govern blueprint '{blueprint_id}'?",
    )
    try:
        govern = get_govern_client_from_ctx(ctx)
        designer = govern.get_blueprint_designer()
        designer.get_blueprint(blueprint_id).delete()
        success(f"Deleted blueprint '{blueprint_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# Blueprint version designer (version-level: fields, workflow, hooks, UI)
# ---------------------------------------------------------------------------


@app.command("create-version")
def create_version(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(help="Parent blueprint ID (e.g. bp.custom_bp)"),
    new_identifier: str = typer.Argument(
        help="New version identifier (letters, digits, hyphen, underscore). Becomes 'bv.<identifier>'."
    ),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Human-readable version name"
    ),
    origin_version_id: Optional[str] = typer.Option(
        None,
        "--from",
        "-f",
        help="Fork from an existing version (recommended). E.g. 'bv.system.default'.",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Create a new blueprint version (DRAFT by default).

    STRONGLY RECOMMENDED: pass --from to fork from an existing ACTIVE version —
    system blueprints contain under-the-hood fields and workflow steps that are
    needed for Govern to function correctly. Starting blank is for advanced users.

    The new version is created in DRAFT status and cannot be applied to artifacts
    until activated. Use 'dku govern blueprint set-version-status BP VER ACTIVE'.
    """
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        designer = govern.get_blueprint_designer()
        bp = designer.get_blueprint(blueprint_id)
        version = bp.create_version(
            new_identifier, name=name, origin_version_id=origin_version_id
        )
        defn = version.get_definition()
        success(
            f"Created version '{version.version_id}' of blueprint '{blueprint_id}' (status: DRAFT)"
        )
        render_raw(defn.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-version-definition")
def set_version_definition(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(help="Blueprint ID"),
    version_id: str = typer.Argument(help="Version ID (e.g. bv.v1)"),
    definition: str = typer.Option(
        ...,
        "--definition",
        help="Full BlueprintVersion JSON (string, @file.json, or - for stdin)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Set dangerZoneAccepted=true. Required when the version has existing artifacts AND the change may break them (e.g. removing fields, changing field types). DATA MAY BE LOST in artifacts.",
    ),
) -> None:
    """Save a full BlueprintVersion definition (fields, workflow, hooks, views, actions).

    This is where real blueprint design happens: fieldDefinitions, workflowDefinition.stepDefinitions,
    logicalHookList, actions, uiDefinition, hierarchicalParentFieldId, instructions.

    Typical loop:
      1. dku govern blueprint get-version BP VER -o json > bv.json
      2. edit bv.json
      3. dku govern blueprint set-version-definition BP VER --definition @bv.json

    If the blueprint version is applied to existing artifacts and your edit removes
    a field or changes its type, the server will refuse the save unless --force is
    set. Using --force may destroy data in existing artifacts — confirm with the
    user before enabling it.
    """
    try:
        govern = get_govern_client_from_ctx(ctx)
        designer = govern.get_blueprint_designer()
        bp = designer.get_blueprint(blueprint_id)
        version = bp.get_version(version_id)
        defn = version.get_definition()
        new_def = read_json_input(definition)
        if not isinstance(new_def, dict):
            exit_with_error(
                "Definition must be a JSON object (got list or scalar).",
                code="invalid_definition",
            )
        defn.definition = new_def
        lint_warnings = _lint_version_definition(new_def)
        defn.save(danger_zone_accepted=force)
        success(
            f"Saved definition for blueprint version '{blueprint_id}/{version_id}'"
            + (" (force)" if force else "")
        )
        if lint_warnings:
            warn(
                f"Pushed a definition with {len(lint_warnings)} structural issue(s) — "
                "the Govern API accepted it but the UI may render broken:"
            )
            for w in lint_warnings:
                warn(f"  - {w}")
            warn(
                f"Run 'dku govern blueprint describe-version {blueprint_id} {version_id}' "
                "to re-verify, or fix the definition and re-push."
            )
    except SystemExit:
        raise
    except Exception as e:
        # Prescriptive guidance for the dangerZone-blocked case
        msg = str(e).lower()
        if "dangerzone" in msg or "danger zone" in msg or "existing artifacts" in msg:
            exit_with_error(
                "Save blocked: this version has existing artifacts and your change may break them.",
                code="danger_zone",
                details=[
                    "Review the diff against the current definition:",
                    f"  dku govern blueprint get-version {blueprint_id} {version_id} -o json",
                    "If you understand that field removals / type changes will destroy",
                    "data in existing artifacts, retry with --force.",
                    "Safer alternative: create a new version and migrate artifacts to it.",
                ],
            )
        handle_api_error(e)


@app.command("delete-version")
def delete_version(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(help="Blueprint ID"),
    version_id: str = typer.Argument(help="Version ID"),
    confirm: bool = typer.Option(
        False, "--confirm", "--yes", "-y", help="Confirm deletion (required)"
    ),
) -> None:
    """Delete a blueprint version. All artifacts using this version must be deleted first."""
    guard(
        ctx,
        tier=Tier.DELETE,
        action="govern.blueprint.delete_version",
        subject=f"blueprint version '{version_id}' on '{blueprint_id}'",
        yes=confirm,
        prompt=f"Delete Govern blueprint version '{version_id}' on '{blueprint_id}'?",
    )
    try:
        govern = get_govern_client_from_ctx(ctx)
        designer = govern.get_blueprint_designer()
        bp = designer.get_blueprint(blueprint_id)
        bp.get_version(version_id).delete()
        success(f"Deleted blueprint version '{blueprint_id}/{version_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("version-status")
def version_status(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(help="Blueprint ID"),
    version_id: str = typer.Argument(help="Version ID"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show the current status of a blueprint version (DRAFT/ACTIVE/ARCHIVED) and its trace."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        designer = govern.get_blueprint_designer()
        bp = designer.get_blueprint(blueprint_id)
        trace = bp.get_version(version_id).get_trace()
        render_raw(trace.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-version-status")
def set_version_status(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(help="Blueprint ID"),
    version_id: str = typer.Argument(help="Version ID"),
    status: BlueprintStatus = typer.Argument(
        case_sensitive=False,
        help="New status: DRAFT, ACTIVE, or ARCHIVED. Only ACTIVE versions can be applied to artifacts.",
    ),
) -> None:
    """Update blueprint version status. Typical flow: DRAFT → ACTIVE (publish) → ARCHIVED (retire)."""
    status = status.upper()
    try:
        govern = get_govern_client_from_ctx(ctx)
        designer = govern.get_blueprint_designer()
        bp = designer.get_blueprint(blueprint_id)
        trace = bp.get_version(version_id).get_trace()
        trace.set_status(status)
        success(f"Set status of '{blueprint_id}/{version_id}' to {status}")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# Signoff configuration designer (per workflow step, on a blueprint version)
# ---------------------------------------------------------------------------


def _signoff_row(raw: dict) -> dict:
    """Flatten a SignoffConfiguration dict into a scannable row."""
    sid = raw.get("id", {}) or {}
    step_id = sid.get("stepId", "")
    groups = raw.get("feedbackUsersGroups") or []
    approvers = raw.get("approvers") or []
    rec = raw.get("recurrenceConfiguration") or {}
    return {
        "step": step_id,
        "title": raw.get("title", ""),
        "mandatory": "*" if raw.get("mandatory") else "",
        "feedback_groups": str(len(groups)),
        "approvers": str(len(approvers)),
        "recurrence": "*" if rec.get("activated") else "",
    }


@app.command("list-signoff-configs")
def list_signoff_configs(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(help="Blueprint ID"),
    version_id: str = typer.Argument(help="Version ID"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List signoff configurations wired to a blueprint version's workflow steps."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        designer = govern.get_blueprint_designer()
        bp = designer.get_blueprint(blueprint_id)
        version = bp.get_version(version_id)
        configs = version.list_signoff_configurations()
        data = [_signoff_row(item.get_raw()) for item in configs]
        render(
            data,
            [
                "step",
                "title",
                "mandatory",
                "feedback_groups",
                "approvers",
                "recurrence",
            ],
            output_format=output,
            title=f"Signoff configs for {blueprint_id}/{version_id}",
            headers={
                "step": "STEP ID",
                "title": "TITLE",
                "mandatory": "REQ",
                "feedback_groups": "#GROUPS",
                "approvers": "#APPROVERS",
                "recurrence": "REC",
            },
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("get-signoff-config")
def get_signoff_config(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(help="Blueprint ID"),
    version_id: str = typer.Argument(help="Version ID"),
    step_id: str = typer.Argument(
        help="Workflow step ID (from workflowDefinition.stepDefinitions)"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get the signoff configuration for a specific workflow step."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        designer = govern.get_blueprint_designer()
        bp = designer.get_blueprint(blueprint_id)
        version = bp.get_version(version_id)
        cfg = version.get_signoff_configuration(step_id)
        defn = cfg.get_definition()
        render_raw(defn.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-signoff-config")
def create_signoff_config(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(help="Blueprint ID"),
    version_id: str = typer.Argument(help="Version ID"),
    step_id: str = typer.Argument(
        help="Workflow step ID. Must reference an existing step in this version's workflowDefinition."
    ),
    definition: str = typer.Option(
        ...,
        "--definition",
        help="SignoffConfiguration JSON (string, @file.json, or - for stdin). Must NOT include 'id'.",
    ),
) -> None:
    """Create a signoff configuration on a workflow step.

    Body shape (minimal):
      {
        "title": "Review",
        "mandatory": true,
        "feedbackUsersGroups": [{"id": "g1", "title": "Reviewers", "users": [{"usersContainer": {"type": "USER", "login": "admin"}}]}],
        "approvers": [{"usersContainer": {"type": "USER", "login": "admin"}}],
        "recurrenceConfiguration": {"activated": false, "days": 0, "weeks": 0, "months": 0, "years": 0, "reloadConf": false}
      }

    The 'id' field is server-assigned from the URL — strip it from the body if present.
    """
    try:
        govern = get_govern_client_from_ctx(ctx)
        designer = govern.get_blueprint_designer()
        bp = designer.get_blueprint(blueprint_id)
        version = bp.get_version(version_id)
        body = read_json_input(definition)
        if not isinstance(body, dict):
            exit_with_error(
                "Signoff configuration must be a JSON object.",
                code="invalid_signoff",
            )
        # Server rejects create if id is set; strip it defensively.
        body.pop("id", None)
        version.create_signoff_configuration(step_id, body)
        success(
            f"Created signoff config on step '{step_id}' of '{blueprint_id}/{version_id}'"
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-signoff-config")
def set_signoff_config(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(help="Blueprint ID"),
    version_id: str = typer.Argument(help="Version ID"),
    step_id: str = typer.Argument(help="Workflow step ID"),
    definition: str = typer.Option(
        ...,
        "--definition",
        help="Full SignoffConfiguration JSON (string, @file.json, or - for stdin)",
    ),
) -> None:
    """Update an existing signoff configuration on a workflow step."""
    try:
        govern = get_govern_client_from_ctx(ctx)
        designer = govern.get_blueprint_designer()
        bp = designer.get_blueprint(blueprint_id)
        version = bp.get_version(version_id)
        cfg = version.get_signoff_configuration(step_id)
        defn = cfg.get_definition()
        new_def = read_json_input(definition)
        if not isinstance(new_def, dict):
            exit_with_error(
                "Signoff configuration must be a JSON object.",
                code="invalid_signoff",
            )
        defn.definition = new_def
        defn.save()
        success(
            f"Updated signoff config on step '{step_id}' of '{blueprint_id}/{version_id}'"
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("delete-signoff-config")
def delete_signoff_config(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(help="Blueprint ID"),
    version_id: str = typer.Argument(help="Version ID"),
    step_id: str = typer.Argument(help="Workflow step ID"),
    confirm: bool = typer.Option(
        False, "--confirm", "--yes", "-y", help="Confirm deletion (required)"
    ),
) -> None:
    """Delete the signoff configuration on a workflow step."""
    guard(
        ctx,
        tier=Tier.DELETE,
        action="govern.blueprint.delete_signoff_config",
        subject=(
            f"sign-off configuration '{step_id}' on blueprint version "
            f"'{blueprint_id}/{version_id}'"
        ),
        yes=confirm,
        prompt=(
            f"Delete sign-off configuration '{step_id}' on Govern blueprint "
            f"version '{blueprint_id}/{version_id}'?"
        ),
    )
    try:
        govern = get_govern_client_from_ctx(ctx)
        designer = govern.get_blueprint_designer()
        bp = designer.get_blueprint(blueprint_id)
        version = bp.get_version(version_id)
        version.get_signoff_configuration(step_id).delete()
        success(
            f"Deleted signoff config on step '{step_id}' of '{blueprint_id}/{version_id}'"
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# Import / export — fork-across-instances, backup, migration
# ---------------------------------------------------------------------------


def _filter_signoff_users_for_export(signoff_cfg: dict) -> dict:
    """Mirror the server's `BlueprintVersionExport.buildFromAndFilterUsers`.

    Only role-based reviewers survive the Govern export→import round-trip.
    The server's import hardcodes `forUsers=NONE, forGroups=NONE, forApiKeys=NONE`
    and NONE means "drop the entire collection" (not "skip validation and keep").
    So user/group/api-key reviewers are always stripped on import — we apply
    the same filter on export to keep the envelope honest.

    Also clears server-stamped `addedBy` / `addedOn` fields so the envelope
    is portable across instances (they'll be re-stamped with the target
    instance's auth identity on import).
    """
    out = dict(signoff_cfg)
    for group in out.get("feedbackUsersGroups") or []:
        if isinstance(group, dict):
            group["users"] = _keep_only_role_users(group.get("users"))
    out["approvers"] = _keep_only_role_users(out.get("approvers"))
    return out


def _keep_only_role_users(users: object) -> list:
    """Return only SignoffUser entries whose usersContainer.type == 'role'."""
    if not isinstance(users, list):
        return []
    kept = []
    for u in users:
        if not isinstance(u, dict):
            continue
        uc = u.get("usersContainer") or {}
        if isinstance(uc, dict) and uc.get("type") == "role":
            cleaned = dict(u)
            cleaned["addedBy"] = ""
            cleaned["addedOn"] = ""
            kept.append(cleaned)
    return kept


@app.command("export-version")
def export_version(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(help="Blueprint ID"),
    version_id: str = typer.Argument(help="Version ID"),
    keep_non_role_users: bool = typer.Option(
        False,
        "--keep-non-role-users",
        help="Preserve user/group/api-key reviewers in the envelope. By default these are stripped because Govern's import endpoint silently drops them — the resulting envelope is not importable as-is. Only enable this when you intend to hand-edit reviewers before importing.",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Export a blueprint version as a BlueprintVersionExport envelope.

    Bundles the full version definition, its origin version ID (from the
    trace), and all signoff configurations into the exact JSON shape that
    `import-version` accepts. Round-trip this to fork a blueprint version
    across Govern instances (e.g. staging → prod) or to back one up before a
    destructive edit.

    IMPORTANT: only role-based reviewers survive the export → import round-trip.
    Govern's import endpoint hardcodes user/group/api-key validation to NONE,
    and NONE mode drops those reviewers rather than preserving them. By
    default we apply the same filter server-side, matching the Govern UI's
    export behavior. Pass --keep-non-role-users if you need to hand-edit the
    envelope before importing (e.g. to remap logins).

    Migration paths (if any) are NOT included — they can only be authored via
    the Govern UI today.

    Pipe to a file and re-import:
      dku govern blueprint export-version bp.my_bp bv.v1 -o json > bv_export.json
      # on the target instance:
      dku govern blueprint import-version bp.my_bp --definition @bv_export.json
    """
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        designer = govern.get_blueprint_designer()
        bp = designer.get_blueprint(blueprint_id)
        version = bp.get_version(version_id)

        defn_raw = version.get_definition().get_raw()
        trace_raw = version.get_trace().get_raw()
        signoff_configs = [
            item.get_raw() for item in version.list_signoff_configurations()
        ]
        if not keep_non_role_users:
            signoff_configs = [
                _filter_signoff_users_for_export(s) for s in signoff_configs
            ]

        export = {
            "blueprintVersion": defn_raw,
            "originVersionId": trace_raw.get("originVersionId"),
            "signoffsConfigurations": signoff_configs,
        }
        render_raw(export, output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("import-version")
def import_version(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(help="Target blueprint ID"),
    definition: str = typer.Option(
        ...,
        "--definition",
        help="BlueprintVersionExport JSON envelope (string, @file.json, or - for stdin). Must contain 'blueprintVersion' at minimum.",
    ),
    ignore_origin_errors: bool = typer.Option(
        False,
        "--ignore-origin-errors",
        help="Don't fail if the origin version referenced in the export no longer exists on this instance.",
    ),
    signoff_roles: SignoffImportRole = typer.Option(
        SignoffImportRole.ALL,
        "--signoff-roles",
        case_sensitive=False,
        help="How strictly to validate signoff reviewer/approver references: ALL (strict — fail if any user/group/role/key missing), EXISTING (keep only existing, drop missing silently), NONE (skip validation, drop everything).",
    ),
    migration_behavior: Optional[MigrationBehavior] = typer.Option(
        None,
        "--migration-behavior",
        case_sensitive=False,
        help="How to handle migration paths in the envelope: FAIL_IMPORT_ON_EXISTING_MIGRATION_OR_MISSING_VERSION (default), IGNORE_MIGRATION_ON_EXISTING_MIGRATION_OR_MISSING_VERSION, or IMPORT_WITHOUT_MIGRATIONS.",
    ),
) -> None:
    """Import a blueprint version from an exported envelope.

    Pair with `export-version`. The envelope must contain at least
    `blueprintVersion` (the full definition). `originVersionId`,
    `signoffsConfigurations`, and `migrationPaths` are optional.

    The target blueprint must already exist on this instance — this command
    adds a new version to it, it doesn't create the blueprint. Use
    `dku govern blueprint create` first if needed.

    The imported version lands in DRAFT status regardless of its status on
    the source instance. Activate with `set-version-status BP VER ACTIVE`
    after verifying the import.
    """
    signoff_roles = signoff_roles.upper()
    if migration_behavior is not None:
        migration_behavior = migration_behavior.upper()

    try:
        govern = get_govern_client_from_ctx(ctx)
        body = read_json_input(definition)
        if not isinstance(body, dict):
            exit_with_error(
                "Import envelope must be a JSON object.",
                code="invalid_envelope",
            )
        if "blueprintVersion" not in body:
            exit_with_error(
                "Import envelope must contain a 'blueprintVersion' key.",
                code="invalid_envelope",
                details=[
                    "Expected shape: {'blueprintVersion': {...}, 'originVersionId': '...', 'signoffsConfigurations': [...]}",
                    "Generate a valid envelope with: dku govern blueprint export-version BP VER -o json",
                ],
            )

        # Server enforces that the body's blueprint ID matches the URL's,
        # AND that every signoff config's id.blueprintVersionId equals the
        # outer blueprintVersion.id. Rewrite both so imports across instances
        # / cross-blueprint forks work without hand-editing the envelope.
        bv = body.get("blueprintVersion") or {}
        if isinstance(bv, dict) and isinstance(bv.get("id"), dict):
            bv["id"]["blueprintId"] = blueprint_id
            target_version_id = bv["id"].get("versionId")
            # Propagate the rewritten version id into every signoff config
            for cfg in body.get("signoffsConfigurations") or []:
                if not isinstance(cfg, dict):
                    continue
                sid = cfg.get("id")
                if not isinstance(sid, dict):
                    sid = {}
                    cfg["id"] = sid
                sid_bvid = sid.get("blueprintVersionId")
                if not isinstance(sid_bvid, dict):
                    sid_bvid = {}
                    sid["blueprintVersionId"] = sid_bvid
                sid_bvid["blueprintId"] = blueprint_id
                if target_version_id:
                    sid_bvid["versionId"] = target_version_id

        params: dict[str, str] = {}
        if ignore_origin_errors:
            params["ignoreOriginVersionErrors"] = "true"
        if signoff_roles:
            params["signoffImportRoles"] = signoff_roles
        if migration_behavior:
            params["migrationPathImportBehavior"] = migration_behavior

        result = govern._perform_json(
            "POST",
            f"/admin/blueprint/{blueprint_id}/versions/import",
            params=params,
            body=body,
        )
        imported_ver = (
            result.get("blueprintVersion", {}).get("id", {}).get("versionId", "?")
            if isinstance(result, dict)
            else "?"
        )
        success(
            f"Imported version '{imported_ver}' into blueprint '{blueprint_id}' (status: DRAFT until activated)"
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
