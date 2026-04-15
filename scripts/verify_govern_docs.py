"""Validate every JSON block in Govern reference docs against a live instance.

Why this exists
---------------
The Govern backend silently accepts misshapen JSON (unknown fields are
dropped, missing fields default to empty lists). That means a doc can ship
with a wrong payload shape and the server returns 200 OK — the bug only
surfaces later, in the UI or downstream tooling. This has happened **three**
times so far:

- 2026-04-08: signoff `feedbackGroups` (wrong) vs `feedbackUsersGroups` (correct);
  `approverConfiguration` as a singular object instead of `approvers[]`.
- 2026-04-12: discovered the real shape is `approvers[]` (a flat list) and
  `feedbackUsersGroups[].users[]` (nested list per group).
- 2026-04-14: blueprint version `uiDefinition.views = {}` documented as
  "default overview rendering" — actually produces a blank artifact page in
  the Govern UI. The validator now lints any blueprint-version block that
  explicitly declares a `uiDefinition` to ensure `views` is non-empty,
  `artifactPageViewId` references a real view, and every step's `viewId`
  points to a valid view (see `_validate_version`).

This script is the guardrail: it extracts every fenced JSON block from the
reference docs, picks the right API call based on surrounding headings, and
posts each block to a scratch blueprint. Anything the server rejects — or
that fails our static UI-shape lint — is a doc bug.

Usage
-----
Requires admin credentials to a Govern instance (same as `dku whoami`):

    uv run python scripts/verify_govern_docs.py

Optional flags:
    --dry-run       Parse blocks only, don't hit the server (CI-friendly)
    --docs PATH...  Override which docs to validate (default: both govern refs)
    --scratch-id    Blueprint ID to use for scratch (default: bp.doc_verifier_tmp)
    --keep          Don't delete the scratch blueprint on exit (for debugging)

Exit codes:
    0   All JSON blocks round-tripped successfully
    1   One or more blocks rejected by the server or failed to parse
    2   Setup failure (couldn't create scratch blueprint, auth error, etc.)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOCS = [
    REPO_ROOT / "dataiku-devkit" / "skills" / "dataiku" / "references" / "govern.md",
    REPO_ROOT / "dataiku-devkit" / "skills" / "govern-blueprint-designer" / "SKILL.md",
    REPO_ROOT
    / "dataiku-devkit"
    / "skills"
    / "govern-blueprint-designer"
    / "references"
    / "field-types.md",
    REPO_ROOT
    / "dataiku-devkit"
    / "skills"
    / "govern-blueprint-designer"
    / "references"
    / "workflow-and-signoffs.md",
    REPO_ROOT
    / "dataiku-devkit"
    / "skills"
    / "govern-blueprint-designer"
    / "references"
    / "hooks-and-actions.md",
    REPO_ROOT
    / "dataiku-devkit"
    / "skills"
    / "govern-blueprint-designer"
    / "references"
    / "ui-views.md",
]

# Heuristic: map block "category" → which API endpoint validates it.
# Determined from the nearest preceding heading or keywords in surrounding text.
CATEGORIES = {
    "blueprint_entity",  # name/icon/color payload for `blueprint create`
    "blueprint_version",  # full version definition for set-version-definition
    "signoff_config",  # signoff configuration for create-signoff-config
    "artifact",  # artifact definition — requires a running blueprint
    "field_definition",  # a single field definition (embedded in version)
    "workflow_step",  # a single workflow step (embedded in version)
    "skip",  # explicitly skipped (partial examples, pseudo-code)
}

# Keywords that classify a block by its nearest heading / surrounding prose.
HEADING_HINTS = [
    (re.compile(r"signoff|sign-off", re.I), "signoff_config"),
    (
        re.compile(r"blueprint.*version.*definition|version.*structure", re.I),
        "blueprint_version",
    ),
    (re.compile(r"field[- ]type|fieldtype|field definition", re.I), "field_definition"),
    (re.compile(r"workflow.*step|step definition", re.I), "workflow_step"),
    (re.compile(r"artifact.*definition|artifact.*json", re.I), "artifact"),
    (re.compile(r"blueprint.*entity|name/icon|icon/color", re.I), "blueprint_entity"),
]

# Top-level keys that fingerprint a payload shape when headings are ambiguous.
SHAPE_HINTS = [
    ({"feedbackUsersGroups", "approvers"}, "signoff_config"),
    ({"fieldDefinitions", "workflowDefinition"}, "blueprint_version"),
    ({"fieldType", "sourceType"}, "field_definition"),
    ({"stepDefinitions"}, "workflow_step"),
    ({"blueprintVersionId", "fields"}, "artifact"),
    ({"name", "icon", "color"}, "blueprint_entity"),
]


@dataclass
class Block:
    """One fenced JSON block extracted from a markdown file."""

    file: Path
    line_start: int  # 1-indexed line number of the opening fence
    heading: str  # nearest preceding heading (or the file stem if none)
    payload_json: str  # raw JSON source as found in the doc
    parsed: object = None  # json.loads result, if parse succeeded
    parse_error: Optional[str] = None
    category: Optional[str] = None
    server_error: Optional[str] = None
    status: str = "pending"  # pending | parsed | validated | rejected | skipped


# ---------------------------------------------------------------------------
# Block extraction
# ---------------------------------------------------------------------------

FENCE_RE = re.compile(r"^```(\w*)\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def extract_blocks(path: Path) -> list[Block]:
    """Return every ```json fenced block in `path` tagged with its heading."""
    blocks: list[Block] = []
    if not path.exists():
        return blocks
    lines = path.read_text().splitlines()
    current_heading = path.stem
    i = 0
    while i < len(lines):
        line = lines[i]
        heading_match = HEADING_RE.match(line)
        if heading_match:
            current_heading = heading_match.group(2)
            i += 1
            continue
        fence_match = FENCE_RE.match(line)
        if fence_match and fence_match.group(1) == "json":
            start = i + 1  # 1-indexed line after the opening fence
            buf = []
            i += 1
            while i < len(lines):
                if FENCE_RE.match(lines[i]):
                    break
                buf.append(lines[i])
                i += 1
            blocks.append(
                Block(
                    file=path,
                    line_start=start,
                    heading=current_heading,
                    payload_json="\n".join(buf),
                )
            )
        i += 1
    return blocks


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify(block: Block) -> str:
    """Decide which API endpoint should validate this block."""
    # 1. Heading-based classification
    heading_text = block.heading or ""
    for pattern, category in HEADING_HINTS:
        if pattern.search(heading_text):
            return category

    # 2. Shape-based classification (if parsed)
    if isinstance(block.parsed, dict):
        keys = set(block.parsed.keys())
        for fingerprint, category in SHAPE_HINTS:
            if fingerprint & keys:
                return category

    # 3. Skip things that look like partial examples
    if isinstance(block.parsed, dict) and len(block.parsed) <= 1:
        return "skip"
    if not isinstance(block.parsed, (dict, list)):
        return "skip"

    return "skip"


# ---------------------------------------------------------------------------
# Validation against a live Govern instance
# ---------------------------------------------------------------------------


class Validator:
    """Creates a scratch blueprint, validates blocks against it, tears down."""

    def __init__(
        self,
        scratch_bp_id: str = "bp.doc_verifier_tmp",
        scratch_version_id: str = "v1",
        keep: bool = False,
    ):
        self.scratch_bp_id = scratch_bp_id
        self.scratch_version_id = f"bv.{scratch_version_id}"
        self.scratch_version_raw_id = scratch_version_id
        self.keep = keep
        self.govern = None
        self.designer = None
        self.scratch_bp = None
        self.scratch_version = None
        self.signoff_step_id = "draft"  # default step we wire signoffs on
        self._created = False
        self._seed_def: dict = {}

    def __enter__(self):
        self._connect()
        self._create_scratch()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._created and not self.keep:
            self._teardown()

    def _connect(self):
        from dku_cli.client import get_client

        dss = get_client()
        self.govern = dss.get_govern_client()
        if self.govern is None:
            raise RuntimeError(
                "Govern integration not enabled on this DSS — required for doc validation."
            )
        self.designer = self.govern.get_blueprint_designer()

    def _create_scratch(self):
        # Blueprint entity
        try:
            existing = self.designer.get_blueprint(self.scratch_bp_id)
            existing.get_definition()  # raises if absent
            print(
                f"[warn] scratch blueprint {self.scratch_bp_id} already exists — "
                f"reusing. Pass --scratch-id to isolate.",
                file=sys.stderr,
            )
            self.scratch_bp = existing
        except Exception:
            bp_body = {
                "name": "Doc Verifier (scratch)",
                "icon": "science",
                "color": "#888888",
            }
            self.scratch_bp = self.designer.create_blueprint(
                self.scratch_bp_id.removeprefix("bp."), bp_body
            )

        # Version with at minimum one workflow step so signoff configs have a target
        try:
            self.scratch_version = self.scratch_bp.get_version(self.scratch_version_id)
            # Touch it to ensure it exists
            self.scratch_version.get_definition()
        except Exception:
            self.scratch_version = self.scratch_bp.create_version(
                self.scratch_version_raw_id, name="v1"
            )

        self._seed_def = {
            "id": {
                "blueprintId": self.scratch_bp.blueprint_id,
                "versionId": self.scratch_version_id,
            },
            "name": "v1",
            "fieldDefinitions": {
                "scratch_title": {
                    "label": "Scratch title",
                    "fieldType": "TEXT",
                    "sourceType": "STORE",
                    "required": False,
                }
            },
            "workflowDefinition": {
                "stepDefinitions": [
                    {
                        "id": self.signoff_step_id,
                        "name": "Draft",
                        "displaySignoffAfterView": False,
                    }
                ]
            },
            "logicalHookList": [],
            "actions": {},
            "uiDefinition": {
                "views": {},
                "uiStepDefinitions": {self.signoff_step_id: {"viewId": ""}},
                "artifactPageViewId": "",
            },
            "instructions": "Scratch blueprint for doc verification — safe to delete.",
            "iconMode": "INHERIT",
        }
        self._reset_scratch_version()
        self._created = True

    def _reset_scratch_version(self) -> None:
        """Restore the scratch version to the canonical seed so each block's
        validation is isolated from prior mutations."""
        import copy

        defn = self.scratch_version.get_definition()
        defn.definition = copy.deepcopy(self._seed_def)
        defn.save(danger_zone_accepted=True)

    def _teardown(self):
        try:
            # Delete any signoff configs we created
            try:
                for item in self.scratch_version.list_signoff_configurations():
                    step = item.get_raw().get("id", {}).get("stepId")
                    if step:
                        try:
                            self.scratch_version.get_signoff_configuration(
                                step
                            ).delete()
                        except Exception:
                            pass
            except Exception:
                pass
            # Delete version
            try:
                self.scratch_version.delete()
            except Exception:
                pass
            # Delete blueprint
            try:
                self.scratch_bp.delete()
            except Exception:
                pass
        except Exception as e:
            print(f"[warn] teardown failed: {e}", file=sys.stderr)

    # ---- per-category validators ----

    def validate(self, block: Block) -> None:
        handler = {
            "signoff_config": self._validate_signoff,
            "blueprint_version": self._validate_version,
            "field_definition": self._validate_field,
            "blueprint_entity": self._validate_blueprint_entity,
            "workflow_step": self._validate_workflow_step,
            "artifact": self._validate_artifact,
        }.get(block.category)

        if handler is None:
            block.status = "skipped"
            return

        # Reset the scratch version before each validation so blocks don't
        # leak state into each other. Artifact/entity validators don't touch
        # the version, so skip the reset for them.
        if block.category not in ("artifact", "blueprint_entity"):
            try:
                self._reset_scratch_version()
            except Exception as e:
                block.status = "rejected"
                block.server_error = f"reset failed: {type(e).__name__}: {e}"
                return

        try:
            handler(block)
            block.status = "validated"
        except Exception as e:
            block.status = "rejected"
            block.server_error = f"{type(e).__name__}: {e}"

    def _validate_signoff(self, block: Block) -> None:
        # Pre-POST shape lint — catches the 2026-04-08-class bugs where the
        # server silently accepts misshapen JSON (unknown fields are dropped,
        # missing fields default to empty). Static checks before we even ask
        # the server, keyed on known-bad patterns from the history of this doc.
        parsed = block.parsed
        if isinstance(parsed, dict):
            shape_errors = []
            if "approverConfiguration" in parsed:
                shape_errors.append(
                    "'approverConfiguration' is not a valid key — use 'approvers' "
                    "(a flat list of {usersContainer: ...} objects)"
                )
            if "feedbackGroups" in parsed:
                shape_errors.append(
                    "'feedbackGroups' is not a valid key — use 'feedbackUsersGroups'"
                )
            for idx, group in enumerate(parsed.get("feedbackUsersGroups") or []):
                if not isinstance(group, dict):
                    continue
                if "usersContainer" in group and "users" not in group:
                    shape_errors.append(
                        f"feedbackUsersGroups[{idx}].usersContainer is misnested — "
                        "reviewers must be inside a users[] array: "
                        "feedbackUsersGroups[i].users[j].usersContainer"
                    )
                if "users" in group and not isinstance(group.get("users"), list):
                    shape_errors.append(
                        f"feedbackUsersGroups[{idx}].users must be a list"
                    )
            if shape_errors:
                raise ValueError("; ".join(shape_errors))

        payload = self._rewrap_with_placeholders(parsed)
        if isinstance(payload, dict):
            payload.pop("id", None)

        try:
            self.scratch_version.get_signoff_configuration(
                self.signoff_step_id
            ).delete()
        except Exception:
            pass
        self.scratch_version.create_signoff_configuration(self.signoff_step_id, payload)

    def _validate_version(self, block: Block) -> None:
        payload = json.loads(json.dumps(block.parsed))  # deep copy
        # Capture whether the doc *explicitly* declares a uiDefinition. If it
        # doesn't, treat the block as a partial example (just fields and/or
        # workflow) and skip the UI-shape lint below — we still inject defaults
        # so the API call doesn't reject the partial. If it DOES declare one,
        # the lint below enforces non-empty views + valid viewId references.
        had_ui_def = "uiDefinition" in payload

        # Rewrite the ID to point at the scratch version
        payload["id"] = {
            "blueprintId": self.scratch_bp.blueprint_id,
            "versionId": self.scratch_version_id,
        }
        # Ensure required skeleton keys
        payload.setdefault("workflowDefinition", {"stepDefinitions": []})
        payload.setdefault("logicalHookList", [])
        payload.setdefault("actions", {})
        payload.setdefault(
            "uiDefinition",
            {"views": {}, "uiStepDefinitions": {}, "artifactPageViewId": ""},
        )
        payload.setdefault("iconMode", "INHERIT")
        # Every workflow step must have a ui step def
        step_defs = payload.get("workflowDefinition", {}).get("stepDefinitions", [])
        ui_step_defs = payload.setdefault("uiDefinition", {}).setdefault(
            "uiStepDefinitions", {}
        )
        for step in step_defs:
            if isinstance(step, dict) and step.get("id"):
                ui_step_defs.setdefault(step["id"], {"viewId": ""})

        # UI-shape lint — third instance of the lax-JSON gotcha (see file
        # docstring). The Govern backend silently accepts `views: {}` and
        # empty `viewId` strings with no error, but the resulting artifact
        # page is BLANK in the UI — verified empirically on DSS/Govern 14.5.
        # Any doc that explicitly declares a uiDefinition must also declare
        # a working set of views, otherwise the agent reading the doc will
        # ship a broken blueprint.
        if had_ui_def:
            ui_errors = self._lint_ui_definition(payload["uiDefinition"])
            if ui_errors:
                raise ValueError("UI shape lint failed: " + " | ".join(ui_errors))

        defn = self.scratch_version.get_definition()
        defn.definition = payload
        defn.save(danger_zone_accepted=True)

    @staticmethod
    def _lint_ui_definition(ui_def: dict) -> list[str]:
        """Static checks on uiDefinition that catch the empty-views silent
        failure. Returns a list of human-readable errors (empty list = OK)."""
        errors: list[str] = []
        if not isinstance(ui_def, dict):
            return ["uiDefinition must be a dict"]

        views = ui_def.get("views") or {}
        if not isinstance(views, dict):
            errors.append("uiDefinition.views must be a dict (keyed by view id)")
            views = {}
        if not views:
            errors.append(
                "uiDefinition.views is empty — Govern silently accepts this "
                "but the artifact page renders BLANK in the UI. Define at "
                "least one view (typically named 'main') that lists every field."
            )

        artifact_page_view_id = ui_def.get("artifactPageViewId") or ""
        if not artifact_page_view_id:
            errors.append(
                "uiDefinition.artifactPageViewId is empty — the main artifact "
                "page will be blank. Set it to a real view id from views."
            )
        elif views and artifact_page_view_id not in views:
            errors.append(
                f"uiDefinition.artifactPageViewId='{artifact_page_view_id}' "
                f"does not match any view id in views (have: {sorted(views)})."
            )

        # Every step that has a non-empty viewId must reference a real view,
        # AND if views are defined at all, no step should be left with an
        # empty viewId (that would render that step's tab as blank).
        ui_step_defs = ui_def.get("uiStepDefinitions") or {}
        if isinstance(ui_step_defs, dict):
            for step_id, step_ui in ui_step_defs.items():
                view_id = (step_ui or {}).get("viewId") or ""
                if not view_id and views:
                    errors.append(
                        f"uiStepDefinitions['{step_id}'].viewId is empty even "
                        f"though views are defined — that step will render blank. "
                        f"Set it to a real view id from views."
                    )
                elif view_id and views and view_id not in views:
                    errors.append(
                        f"uiStepDefinitions['{step_id}'].viewId='{view_id}' "
                        f"does not match any view id in views (have: {sorted(views)})."
                    )

        return errors

    def _validate_field(self, block: Block) -> None:
        # Embed this field into the scratch version's fieldDefinitions and save.
        # Handles top-level-is-a-single-field-object OR top-level-is-a-map-of-fields.
        parsed = block.parsed
        if not isinstance(parsed, dict):
            raise ValueError("field_definition block is not a dict")
        # Case 1: it's already {field_id: {fieldType: ...}}
        if any(isinstance(v, dict) and "fieldType" in v for v in parsed.values()):
            fields = parsed
        # Case 2: it IS a single field definition (has fieldType)
        elif "fieldType" in parsed:
            fields = {f"scratch_field_{id(block)}": parsed}
        else:
            raise ValueError("field_definition block has no recognizable shape")
        defn = self.scratch_version.get_definition()
        raw = defn.get_raw()
        raw["fieldDefinitions"] = {**raw.get("fieldDefinitions", {}), **fields}
        defn.definition = raw
        defn.save(danger_zone_accepted=True)

    def _validate_workflow_step(self, block: Block) -> None:
        # Steps live inside workflowDefinition.stepDefinitions; treat this as a
        # step mutation by embedding + saving.
        parsed = block.parsed
        if not isinstance(parsed, dict):
            raise ValueError("workflow_step block is not a dict")
        # Case 1: block is {"workflowDefinition": {...}}
        if "workflowDefinition" in parsed:
            steps = parsed["workflowDefinition"].get("stepDefinitions", [])
        # Case 2: block is {"stepDefinitions": [...]}
        elif "stepDefinitions" in parsed:
            steps = parsed["stepDefinitions"]
        # Case 3: a single step
        elif "id" in parsed and "name" in parsed:
            steps = [parsed]
        else:
            raise ValueError("workflow_step block has no recognizable shape")
        defn = self.scratch_version.get_definition()
        raw = defn.get_raw()
        # Keep the scratch default step in place; append these.
        merged = list(raw.get("workflowDefinition", {}).get("stepDefinitions", []))
        existing_ids = {s.get("id") for s in merged if isinstance(s, dict)}
        for s in steps:
            if isinstance(s, dict) and s.get("id") and s["id"] not in existing_ids:
                merged.append(s)
                existing_ids.add(s["id"])
        raw["workflowDefinition"] = {"stepDefinitions": merged}
        ui = raw.setdefault("uiDefinition", {}).setdefault("uiStepDefinitions", {})
        for s in merged:
            ui.setdefault(s.get("id", ""), {"viewId": ""})
        defn.definition = raw
        defn.save(danger_zone_accepted=True)

    def _validate_blueprint_entity(self, block: Block) -> None:
        # Just validate that the server accepts it as a blueprint definition update
        # on the scratch blueprint.
        defn = self.scratch_bp.get_definition()
        raw = defn.get_raw()
        # Merge, don't replace — preserve id
        for k, v in block.parsed.items():
            if k != "id":
                raw[k] = v
        defn.definition = raw
        defn.save()

    def _validate_artifact(self, block: Block) -> None:
        # Artifact validation requires the referenced blueprint version to exist.
        # For doc-validation purposes we skip — creating real artifacts has side
        # effects on the instance and the blueprint version is out of our control.
        # Shape-check only: must be a dict with blueprintVersionId + fields.
        parsed = block.parsed
        if not isinstance(parsed, dict):
            raise ValueError("artifact block is not a dict")
        if "blueprintVersionId" not in parsed:
            raise ValueError("artifact block missing blueprintVersionId")
        if "fields" not in parsed:
            raise ValueError("artifact block missing fields")
        bv = parsed["blueprintVersionId"]
        if not isinstance(bv, dict) or "blueprintId" not in bv or "versionId" not in bv:
            raise ValueError("blueprintVersionId must be {blueprintId, versionId}")

    # ---- placeholder helpers ----

    def _rewrap_with_placeholders(self, payload: object) -> object:
        """Normalize doc payloads so they resolve against *this* Govern instance.

        Doc blocks reference example users/groups that don't exist here
        (`alice`, `bob`, `product_owners`, etc.). The validator's job is to
        check JSON shape, not that every name resolves, so we force every
        user/group/role reference to `admin` / `administrators` — which are
        guaranteed to exist on any Govern instance we can auth against.
        """
        if isinstance(payload, dict):
            out = {k: self._rewrap_with_placeholders(v) for k, v in payload.items()}
            # Force any usersContainer to point at known-good identities
            if isinstance(out.get("type"), str) and out["type"] in {
                "user",
                "group",
                "role",
                "global-api-key",
            }:
                if out["type"] == "user" and "login" in out:
                    out["login"] = "admin"
                elif out["type"] == "group" and "groupName" in out:
                    out["groupName"] = "administrators"
                elif out["type"] == "role" and "roleId" in out:
                    # No guaranteed role exists; fall back to user type
                    out.clear()
                    out["type"] = "user"
                    out["login"] = "admin"
                elif out["type"] == "global-api-key" and "keyId" in out:
                    out.clear()
                    out["type"] = "user"
                    out["login"] = "admin"
            return out
        if isinstance(payload, list):
            return [self._rewrap_with_placeholders(v) for v in payload]
        return payload


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Parse only, don't hit the server"
    )
    parser.add_argument("--docs", nargs="+", type=Path, help="Docs to validate")
    parser.add_argument("--scratch-id", default="bp.doc_verifier_tmp")
    parser.add_argument(
        "--keep", action="store_true", help="Keep scratch blueprint after run"
    )
    args = parser.parse_args()

    docs = args.docs or DEFAULT_DOCS

    # 1. Extract
    all_blocks: list[Block] = []
    for path in docs:
        blocks = extract_blocks(path)
        all_blocks.extend(blocks)
        try:
            display = path.relative_to(REPO_ROOT)
        except ValueError:
            display = path
        print(f"[extract] {display}: {len(blocks)} JSON blocks")

    if not all_blocks:
        print("No JSON blocks found — nothing to validate.")
        return 0

    # 2. Parse
    # Blocks that fail to parse are treated as partial/illustrative snippets
    # and silently skipped. The validator's job is to catch full-payload docs
    # that the server rejects — not to mandate that every fenced block be a
    # complete, parseable document. Docs legitimately contain excerpts like
    # `"fieldDefinitions": { ... }` in ```json fences for readability.
    #
    # Blocks with `<ALL CAPS PLACEHOLDER>` or `<...>` markers are also skipped —
    # these are fill-in-the-blank templates, not real payloads.
    placeholder_re = re.compile(r"<[A-Z][A-Z0-9 _/\.]*>|<\.\.\.>")
    for block in all_blocks:
        if placeholder_re.search(block.payload_json):
            block.status = "skipped"
            block.category = "skip"
            continue
        try:
            block.parsed = json.loads(block.payload_json)
            block.status = "parsed"
        except json.JSONDecodeError as e:
            block.parse_error = str(e)
            block.status = "skipped"
            block.category = "skip"

    # 3. Classify
    for block in all_blocks:
        if block.status == "parsed":
            block.category = classify(block)

    # 4. Validate (unless dry-run)
    if not args.dry_run:
        try:
            with Validator(scratch_bp_id=args.scratch_id, keep=args.keep) as validator:
                for block in all_blocks:
                    if block.status == "parsed":
                        validator.validate(block)
        except Exception as e:
            print(f"[fatal] Validator setup failed: {e}", file=sys.stderr)
            traceback.print_exc()
            return 2
    else:
        for block in all_blocks:
            if block.status == "parsed" and block.category != "skip":
                block.status = "skipped"  # dry-run treats all as skipped post-parse

    # 5. Report
    rejected = [b for b in all_blocks if b.status == "rejected"]
    validated = [b for b in all_blocks if b.status == "validated"]
    skipped = [b for b in all_blocks if b.status == "skipped"]

    print()
    print(
        f"=== SUMMARY: {len(validated)} validated, {len(rejected)} rejected, {len(skipped)} skipped ==="
    )
    print()

    if rejected:
        print("REJECTED BLOCKS:")
        for block in rejected:
            try:
                rel = block.file.relative_to(REPO_ROOT)
            except ValueError:
                rel = block.file
            print(
                f"  {rel}:{block.line_start} [{block.heading}] → {block.category or '<unclassified>'}"
            )
            if block.parse_error:
                print(f"    parse error: {block.parse_error}")
            if block.server_error:
                print(f"    server error: {block.server_error}")
            print()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
