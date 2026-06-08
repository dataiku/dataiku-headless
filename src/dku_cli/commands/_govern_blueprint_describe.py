"""Helpers for Govern blueprint version description and structural linting."""

from __future__ import annotations

from typing import Any


def _count_view_components(comp: object) -> int:
    """Recursively count leaf field components in a viewComponent tree.

    A view's `viewComponent` is either a leaf (`{type: "<x>-field", fieldId: ...}`)
    or a `container` whose `layout.viewComponents[]` holds children that may
    themselves be containers. We count any node with a `fieldId` as one
    component.
    """
    if not isinstance(comp, dict):
        return 0
    if comp.get("type") == "container":
        children = (comp.get("layout") or {}).get("viewComponents") or []
        return sum(_count_view_components(c) for c in children)
    return 1 if comp.get("fieldId") else 0


def _collect_view_field_ids(comp: object, sink: set[str]) -> None:
    """Walk a viewComponent tree and add every referenced fieldId to `sink`."""
    if not isinstance(comp, dict):
        return
    fid = comp.get("fieldId")
    if fid:
        sink.add(fid)
    if comp.get("type") == "container":
        for child in (comp.get("layout") or {}).get("viewComponents") or []:
            _collect_view_field_ids(child, sink)


def _lint_version_definition(raw: dict) -> list[str]:
    """Return structural-warning strings for a blueprint version definition.

    Catches the silent-failure patterns the Govern API accepts but render
    broken: empty views, empty/invalid artifactPageViewId, empty/invalid step
    viewIds, fields not referenced by any view. Called from describe-version
    (read) and set-version-definition (write, pre-push) so the same lint rules
    live in one place.

    Signoff-step-existence checks live in describe-version because they depend
    on a separate live API call (list_signoff_configurations), not the raw
    version definition.
    """
    warnings: list[str] = []
    if not isinstance(raw, dict):
        return warnings

    ui_def = raw.get("uiDefinition", {}) or {}
    views = ui_def.get("views", {}) or {}
    artifact_page_view_id = ui_def.get("artifactPageViewId", "") or ""
    ui_step_defs = ui_def.get("uiStepDefinitions", {}) or {}
    workflow = raw.get("workflowDefinition", {}) or {}
    steps = workflow.get("stepDefinitions", []) or []
    field_defs = raw.get("fieldDefinitions", {}) or {}

    if not views:
        warnings.append(
            "uiDefinition.views is empty — the artifact page will be BLANK in Govern. "
            "Define at least one view that lists every field."
        )
    if not artifact_page_view_id:
        warnings.append(
            "uiDefinition.artifactPageViewId is empty — set it to a real "
            "view id so the main artifact page renders."
        )
    elif views and artifact_page_view_id not in views:
        warnings.append(
            f"uiDefinition.artifactPageViewId='{artifact_page_view_id}' "
            f"does not match any view id (have: {sorted(views)})."
        )

    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = step.get("id", "")
        if not step_id:
            continue
        step_def = ui_step_defs.get(step_id) or {}
        view_id = step_def.get("viewId", "") or ""
        if not view_id and views:
            warnings.append(
                f"Step '{step_id}' has no viewId — its tab will render blank. "
                f"Set uiStepDefinitions['{step_id}'].viewId to a real view id."
            )
        elif view_id and views and view_id not in views:
            warnings.append(
                f"Step '{step_id}' viewId='{view_id}' does not match any view id "
                f"(have: {sorted(views)})."
            )

    if views and field_defs:
        referenced: set[str] = set()
        for view_def in views.values():
            if isinstance(view_def, dict):
                _collect_view_field_ids(view_def.get("viewComponent"), referenced)
        unreferenced = sorted(set(field_defs.keys()) - referenced)
        for field_id in unreferenced:
            warnings.append(
                f"Field '{field_id}' is not referenced by any view component — "
                f"users won't see it. Add it to a view's viewComponents."
            )

    return warnings


def _version_id_from_trace(raw: dict[str, Any]) -> str:
    bv = raw.get("blueprintVersion", raw)
    vid_obj = bv.get("id", {}) if isinstance(bv, dict) else {}
    return vid_obj.get("versionId", "") if isinstance(vid_obj, dict) else str(vid_obj)


def _resolve_version_status(bp, version_id: str) -> str:
    try:
        for item in bp.list_versions():
            trace_raw = item.get_raw()
            if _version_id_from_trace(trace_raw) == version_id:
                return trace_raw.get("blueprintVersionTrace", {}).get("status", "?")
    except Exception:
        return "?"
    return "?"


def _resolve_blueprint_name(bp) -> str:
    bp_def_raw = bp.get_definition().get_raw()
    bp_inner = bp_def_raw.get("blueprint", bp_def_raw)
    return bp_inner.get("name", "") if isinstance(bp_inner, dict) else ""


def _build_field_rows(raw: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for field_id, field_def in (raw.get("fieldDefinitions", {}) or {}).items():
        if not isinstance(field_def, dict):
            continue
        categories = field_def.get("categories") or []
        rows.append(
            {
                "id": field_id,
                "label": field_def.get("label", ""),
                "type": field_def.get("fieldType", ""),
                "source": field_def.get("sourceType", "STORE"),
                "list": "*" if "listConfig" in field_def else "",
                "required": "*"
                if field_def.get("isMandatory") or field_def.get("required")
                else "",
                "categories": ",".join(categories) if categories else "",
            }
        )
    return rows


def _workflow_steps(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    workflow = raw.get("workflowDefinition", {}) or {}
    steps = [
        step
        for step in workflow.get("stepDefinitions", []) or []
        if isinstance(step, dict)
    ]
    return steps, workflow.get("initialStepId", "")


def _build_step_rows(
    steps: list[dict[str, Any]], initial_step_id: str
) -> list[dict[str, str]]:
    return [
        {
            "id": step.get("id", ""),
            "name": step.get("name", ""),
            "initial": "*" if step.get("id", "") == initial_step_id else "",
        }
        for step in steps
    ]


def _build_signoff_rows(signoff_configs: list[object]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in signoff_configs:
        cfg = item.get_raw() if hasattr(item, "get_raw") else item
        if not isinstance(cfg, dict):
            continue
        cfg_id = cfg.get("id", {})
        step_id = cfg_id.get("stepId", "") if isinstance(cfg_id, dict) else ""
        groups = cfg.get("feedbackUsersGroups") or []
        approvers = cfg.get("approvers") or []
        approver_types = sorted(
            {
                (approver.get("usersContainer") or {}).get("type", "?")
                for approver in approvers
                if isinstance(approver, dict)
            }
        )
        rows.append(
            {
                "step": step_id,
                "title": cfg.get("title", ""),
                "mandatory": "*" if cfg.get("mandatory") else "",
                "approvers": str(len(approvers)),
                "approver_types": ",".join(approver_types),
                "feedback_groups": str(len(groups)),
            }
        )
    return rows


def _load_signoff_rows(version) -> list[dict[str, str]]:
    try:
        signoff_configs = list(version.list_signoff_configurations())
    except Exception:
        signoff_configs = []
    return _build_signoff_rows(signoff_configs)


def _view_to_steps(ui_step_defs: dict[str, Any]) -> dict[str, list[str]]:
    view_to_steps: dict[str, list[str]] = {}
    for step_id, step_def in ui_step_defs.items():
        view_id = step_def.get("viewId", "") if isinstance(step_def, dict) else ""
        if view_id:
            view_to_steps.setdefault(view_id, []).append(step_id)
    return view_to_steps


def _build_view_rows(raw: dict[str, Any]) -> list[dict[str, str]]:
    ui_def = raw.get("uiDefinition", {}) or {}
    views = ui_def.get("views", {}) or {}
    artifact_page_view_id = ui_def.get("artifactPageViewId", "") or ""
    view_to_steps = _view_to_steps(ui_def.get("uiStepDefinitions", {}) or {})

    rows: list[dict[str, str]] = []
    for view_id, view_def in views.items():
        if not isinstance(view_def, dict):
            continue
        comp = view_def.get("viewComponent", {})
        rows.append(
            {
                "id": view_id,
                "label": view_def.get("label", ""),
                "components": str(_count_view_components(comp)),
                "is_artifact_page": "*" if view_id == artifact_page_view_id else "",
                "used_by_steps": ",".join(sorted(view_to_steps.get(view_id, [])))
                or "—",
            }
        )
    return rows


def _describe_version_warnings(
    raw: dict[str, Any],
    valid_step_ids: set[str],
    signoff_rows: list[dict[str, str]],
) -> list[str]:
    warnings = _lint_version_definition(raw)
    for row in signoff_rows:
        step_id = row["step"]
        if step_id and step_id not in valid_step_ids:
            warnings.append(
                f"Signoff configured on step '{step_id}' which does not exist "
                f"in workflowDefinition.stepDefinitions."
            )
    return warnings
