"""Error handling: dataikuapi exceptions to user-friendly messages + exit codes.

Exit codes:
  1 — General DSS API error
  2 — Authentication / authorization failure (401, 403)
  3 — Resource not found (404)
  4 — Connection failure (cannot reach DSS)
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from functools import wraps
from typing import TypeVar, cast

from click.exceptions import Abort as CAbort, Exit as CExit, UsageError as CUsageError
from typer import Abort, BadParameter, Exit

from dku_cli.output import error

F = TypeVar("F", bound=Callable[..., object])


class AuthError(Exception):
    """Raised when DSS credentials cannot be resolved."""


def exit_with_error(
    message: str,
    *,
    details: list[str] | None = None,
    status: int = 1,
) -> None:
    """Render a single error payload and exit."""
    for line in [message, *(details or [])]:
        error(line)

    sys.exit(status)


def is_not_found_error(e: Exception) -> bool:
    """Return whether an exception represents a DSS not-found condition."""
    msg = str(e)
    return (
        "NotFoundException" in msg
        or "does not exist" in msg
        or "404" in msg
        or "not found" in msg.lower()
    )


def is_already_exists_error(e: Exception) -> bool:
    """Return whether an exception represents a DSS already-exists condition."""
    msg = str(e).lower()
    return "already exists" in msg or "409" in msg or "duplicate" in msg


def is_connection_required_error(e: Exception) -> bool:
    """Return whether an exception indicates a missing managed connection for output creation.

    DSS throws this when a code recipe tries to auto-create an output dataset
    but no default managed connection is configured at the project level.
    """
    msg = str(e)
    return "creationInfo" in msg or "Need to create output dataset" in msg


def _resolve_auth_context() -> tuple[str | None, str | None]:
    """Best-effort resolution of (url, profile) for prescriptive auth errors.

    Reads from env vars first (so explicit overrides win), then falls back to
    the CLI's TOML config (active profile + its url). Returns ``(None, None)``
    if neither source is available — callers should handle the missing case.
    """
    import os

    env_url = os.environ.get("DKU_URL") or os.environ.get("DKU_DSS_URL")
    env_profile = os.environ.get("DKU_PROFILE")

    config_url: str | None = None
    config_profile: str | None = None
    try:
        from dku_cli.config import get_active_profile, get_profile_config

        config_profile = get_active_profile()
        config_url = (get_profile_config(config_profile) or {}).get("url")
    except Exception:
        # Config read can fail for many benign reasons (no config file, malformed
        # TOML, platformdirs path issue). Don't let auth-error reporting cascade.
        pass

    return env_url or config_url, env_profile or config_profile


def _handle_invalid_api_key(msg: str) -> tuple[str, list[str]] | None:
    """Detect an invalid/unknown API key error and return prescriptive guidance.

    DSS rejects unknown or rotated API keys with messages like
    ``com.dataiku.dip.exceptions.NotAuthenticatedException: Unknown API Key``.
    The base 401/Unauthorized branch in ``handle_api_error`` doesn't catch this
    because the message contains neither ``401`` nor ``Unauthorized`` — so
    without this helper the user just sees the raw Java exception.

    Returns (message, details) or None if the input doesn't match.
    """
    if "NotAuthenticatedException" not in msg and "Unknown API Key" not in msg:
        return None

    url, profile = _resolve_auth_context()
    url_display = url or "<unknown URL — set DKU_URL or run `dku auth login --url ...`>"
    profile_display = profile or "default"

    recover_args = []
    if url:
        recover_args.append(f"--url {url}")
    recover_args.append("--api-key <new-key>")
    recover_cmd = "dku auth login " + " ".join(recover_args)

    return (
        f"DSS rejected the stored API key (URL: {url_display}, profile: {profile_display}).",
        [
            "The stored credentials are no longer valid — the key may have been",
            "rotated, deleted, or never had access to this DSS instance.",
            "",
            "Recover with:",
            f"  {recover_cmd}",
            "",
            "Or for an interactive prompt that asks for the key:",
            f"  dku auth login{' --url ' + url if url else ''}",
        ],
    )


def _handle_project_access_denied(
    msg: str, project_key: str | None = None
) -> tuple[str, list[str]] | None:
    """Detect a project-scoped 401 and prescribe key-vs-name, NOT re-auth.

    DSS returns ``UnauthorizedException: Failed to read project permissions`` for
    a project the caller cannot access — and it does NOT distinguish "project
    does not exist" from "exists but you lack permission" (it refuses to reveal
    existence). The generic 401/Unauthorized branch in ``handle_api_error`` then
    blames the API key, sending agents into a pointless re-auth loop even though
    their key is perfectly valid (``dku whoami`` works fine). This is the exact
    failure mode that wasted 6 agent steps in a live benchmark run.

    A genuinely invalid key surfaces earlier as ``NotAuthenticatedException`` /
    ``Unknown API Key`` (handled by ``_handle_invalid_api_key``), so by the time
    we reach this project-permissions failure the instance credentials are sound.

    Fires on either of two signals:
      * The exact DSS message ``Failed to read project permissions`` — catches
        ANY project-scoped command (dataset, recipe, scenario…), even when the
        caller did not thread a project key.
      * A 401/Unauthorized when the caller DID name a project (``project_key``
        set) — broader, and future-proofs the wired commands against DSS
        rewording the permissions message.

    Returns (message, details) or None if the error isn't this case.
    """
    perm_failure = "Failed to read project permissions" in msg
    named_project_401 = project_key is not None and (
        "Unauthorized" in msg or "401" in msg
    )
    if not (perm_failure or named_project_401):
        return None

    subject = f"Project '{project_key}'" if project_key else "That project key"
    details = [
        "DSS returns the same error whether the project does not exist or you",
        "lack permission on it — it will not say which.",
        "",
        "This is NOT an API-key problem: your instance credentials work",
        "(`dku whoami` confirms them). Do NOT run `dku auth login` again.",
        "",
        "Most likely cause: project KEY vs display NAME. A key is UPPERCASE with",
        "no spaces (e.g. ADVISORGPT) and differs from the display name (e.g.",
        "'AdvisorGPT'). Project-scoped commands require the KEY, not the name.",
        "",
        "List projects and read the KEY column (not NAME):",
        "  dku project list",
    ]
    if project_key:
        details.append(
            f"Find the row whose NAME is '{project_key}' and retry with its KEY."
        )
    return (
        f"{subject} was not found, or your account cannot access it.",
        details,
    )


def _handle_pivot_modality_scan(msg: str) -> tuple[str, list[str]] | None:
    """Detect a Pivot recipe modality-scan failure and prescribe restructuring.

    DSS only populates the output dataset's modality cache during a UI-driven
    scan; `dku` exposes no command for it, and even setting
    ``pivots[0].explicitValues`` in the recipe payload doesn't populate the
    cache. The build then fails with this exact error. The fix is rarely "set
    the modalities harder" — it's "redesign the flow to skip the pivot".

    Returns (message, details) or None if the error doesn't match.
    """
    if "Modality lists stored in output schema are not up-to-date" not in msg:
        return None

    return (
        "Pivot recipe modality scan is UI-only — `dku` cannot trigger it.",
        [
            "DSS populates the output dataset's modality cache only during a",
            "UI-driven scan. Setting `pivots[0].explicitValues` via",
            "`dku recipe set-settings` updates the recipe payload but NOT the",
            "output's modality cache, so the build still fails.",
            "",
            "Fix: redesign the flow to skip the pivot. If the pivot exists to",
            "fan a column-keyed value into N output columns for a downstream",
            "join, compute those N columns inline upstream with `add-formula`",
            "(one per modality) and skip the pivot entirely.",
        ],
    )


def _handle_fold_plugin_missing(msg: str) -> tuple[str, list[str]] | None:
    """Detect the FoldColumnsByName plugin-missing error.

    Older `dku` versions emitted `FoldColumnsByName` (plugin) from `add-fold`.
    Recent versions emit stock `MultiColumnFold`. If a user hits the plugin
    error, the immediate fix is to reinstall the global CLI; falling back to
    `pd.melt` is never the right answer.

    Returns (message, details) or None if the error doesn't match.
    """
    if "FoldColumnsByName" not in msg or "plugin that is not installed" not in msg:
        return None

    return (
        "`FoldColumnsByName` is a plugin processor not installed on this DSS.",
        [
            "Recent `dku` versions emit the stock `MultiColumnFold` processor",
            "from `add-fold` instead of the plugin variant. Reinstall the",
            "global CLI to pick up that fix:",
            "",
            "  uv tool install --from . dku-headless --force --reinstall",
            "",
            "Do NOT fall back to a Python `pd.melt` recipe. If the unpivot is",
            "still in your way after reinstalling, consider whether you need",
            "the unpivot at all — most are eliminated by computing per-group",
            "aggregates *before* the reshape.",
        ],
    )


def _handle_not_dev_plugin(msg: str) -> tuple[str, list[str]] | None:
    """Detect the dev-plugin-only limitation on plugin file access.

    ``DSSPlugin.get_file``/``list_files``/``put_file`` raise
    ``CodedRuntimeException: Plugin X is not a dev plugin`` for zip-uploaded
    plugins — the push is one-way and there is NO API readback. Without this
    mapping, agents burn rounds trying to verify pushed content.

    Returns (message, details) or None if the error doesn't match.
    """
    if "is not a dev plugin" not in msg:
        return None

    return (
        "Uploaded (zip-pushed) plugins are write-only via the API — file "
        "access works on DEV plugins only.",
        [
            "There is no API readback for a pushed plugin. Verify content in",
            "the zip BEFORE pushing:",
            "  unzip -p <plugin.zip> <path/inside/zip>",
            "After a push, trust the 'Updated plugin' ack; for Code Studios,",
            "recreate the studio (resources seed at creation).",
        ],
    )


def _handle_partial_output_read(msg: str) -> tuple[str, list[str]] | None:
    """Detect a read of a partial file left behind by a FAILED build.

    Reading a dataset right after its producing recipe failed surfaces
    ``CodedIOException ... EOFException: Unexpected end of ZLIB input stream``.
    It looks like data corruption; it is just a truncated ``out-s0.csv.gz``
    from the aborted build. The fix is to fix and re-run the producing
    recipe, not to investigate the data.

    Returns (message, details) or None if the error doesn't match.
    """
    if "Unexpected end of ZLIB input stream" not in msg:
        return None

    return (
        "The dataset's stored file is a PARTIAL file from a failed build — "
        "not data corruption.",
        [
            "A failed/aborted build of the producing recipe leaves a truncated",
            ".csv.gz behind; reading it raises this ZLIB EOF error.",
            "",
            "Fix the producing recipe and re-run it:",
            "  dku recipe run <producing-recipe> -P <project>",
            "Find the producer: dku dataset usage <dataset> -P <project>",
        ],
    )


def _handle_never_built_read(msg: str) -> tuple[str, list[str]] | None:
    """Detect a raw DataStoreIOException from reading a never-built dataset.

    DSS raises ``DataStoreIOException`` (e.g. "No such file or directory")
    when reading a managed dataset that has never been built or whose last
    build failed. The raw passthrough gives agents no next step.

    Returns (message, details) or None if the error doesn't match.
    """
    if "DataStoreIOException" not in msg and "Root path of the dataset" not in msg:
        return None

    return (
        "Cannot read the dataset's storage — it has no data yet (never "
        "built, last build failed, or nothing uploaded).",
        [
            f"Underlying error: {msg}",
            "",
            "Managed dataset — build it (RECURSIVE_BUILD also builds "
            "unbuilt upstreams):",
            "  dku dataset build <dataset> -P <project> --type RECURSIVE_BUILD --auto-update-schema --wait",
            "Uploaded dataset — upload the file first:",
            "  dku dataset upload <dataset> <file> -P <project>",
        ],
    )


def _handle_govern_field_type_enum(msg: str) -> tuple[str, list[str]] | None:
    """Detect ``IllegalArgumentException: No enum constant ...FieldType.X`` and
    return prescriptive guidance with the valid Govern field types.

    Govern's backend rejects unknown ``fieldType`` values with a raw Java
    IllegalArgumentException. The user has no idea what's valid because the
    9 accepted values aren't in the error. This rewrites the message to list
    them and points at the reference doc.

    Returns (message, details) or None if the input doesn't match.
    """
    import re

    m = re.search(r"No enum constant\s+(?:\S+\.)?FieldType\.(\w+)", msg)
    if not m:
        return None
    bad_value = m.group(1)
    return (
        f"'{bad_value}' is not a valid Govern fieldType.",
        [
            "Valid values: TEXT, NUMBER, BOOLEAN, DATE, CATEGORY, REFERENCE,",
            "UPLOADED_FILE, TIME_SERIES, JSON.",
            "",
            f"Common mistake: 'STRING' → use 'TEXT'. '{bad_value}' is not a Govern type.",
            "",
            "See: dataiku skill's references/govern-field-types.md for the full",
            "envelope of each type.",
        ],
    )


def _handle_govern_field_save_npe(msg: str) -> tuple[str, list[str]] | None:
    """Detect a Govern blueprint-version save NPE caused by missing required
    keys on a fieldDefinitions entry.

    DSS surfaces this as
    ``NullPointerException: Cannot invoke ...JsonObject.get(String)
    .getAsString() because return is null`` when an entry omits a required
    key (typically ``id``, ``fieldType``, ``sourceType``, or ``label``).
    The error doesn't say *which* key is missing, so list them all and
    flag the common-mistake renames.

    Returns (message, details) or None if the input doesn't match.
    """
    if "NullPointerException" not in msg or "JsonObject" not in msg:
        return None
    if ".getAsString" not in msg and "JsonObject.get(String)" not in msg:
        return None
    return (
        "Govern blueprint-version save failed: a fieldDefinitions entry is "
        "missing a required key.",
        [
            "Each entry under fieldDefinitions needs all four keys:",
            "  id          (the field identifier)",
            "  fieldType   (one of TEXT / NUMBER / BOOLEAN / DATE / CATEGORY /",
            "               REFERENCE / UPLOADED_FILE / TIME_SERIES / JSON)",
            "  sourceType  (usually 'STORE'; 'COMPUTE' for derived fields)",
            "  label       (human-readable label shown in the UI)",
            "",
            "Common mistakes:",
            "  - 'name' instead of 'id'",
            "  - 'type' instead of 'fieldType'",
            "  - missing 'sourceType' (defaults are NOT applied)",
            "",
            "See: dataiku skill's references/govern-field-types.md for the full",
            "envelope and per-type extras (CATEGORY needs 'categories', etc.).",
        ],
    )


def _handle_govern_validation(msg: str) -> tuple[str, list[str]] | None:
    """Parse Govern ValidationException messages into prescriptive guidance.

    Returns (message, details) or None if not a Govern validation error.
    """
    if "ValidationException" not in msg:
        return None

    import re

    # "Field `X` is a list in artifact: ar.N"
    m = re.search(r"Field `(\w+)` is a list in artifact", msg)
    if m:
        field = m.group(1)
        return (
            f"Field '{field}' is a list field — value must be a JSON array.",
            [
                f'Use: "{field}": ["value1", "value2"] (array), not "{field}": "value1" (string).',
                'Even single values must be wrapped: ["value"].',
                "Run: dku govern blueprint fields <BLUEPRINT_ID> to see which fields are lists (marked with * in LIST column).",
            ],
        )

    # "Invalid type for field value: double" (date field given a number)
    if "Invalid type for field value: double" in msg:
        return (
            "Invalid field value type — DATE fields require ISO 8601 strings, not numbers.",
            [
                'Use: "start_date": "2025-01-15T00:00:00.000Z" (ISO 8601 string).',
                'Do NOT use epoch milliseconds like "start_date": 1704067200000.',
            ],
        )

    # "Invalid type for field value: map" (field given a dict instead of a scalar)
    if "Invalid type for field value: map" in msg:
        return (
            "Invalid field value type — field values must be plain strings/numbers, not objects.",
            [
                'Use: "field_name": "value" (plain value), not "field_name": {"value": "..."}.',
                'REFERENCE fields accept artifact IDs: "business_initiative": "ar.123".',
            ],
        )

    # "'X' for field ID 'Y' is not a valid category"
    m = re.search(r"'(.+?)' for field ID '(\w+)' is not a valid category", msg)
    if m:
        value, field = m.group(1), m.group(2)
        return (
            f"'{value}' is not a valid category for field '{field}'.",
            [
                f"Run: dku govern blueprint fields <BLUEPRINT_ID> to see valid categories for '{field}'.",
                "Category values are case-sensitive and must match exactly.",
            ],
        )

    # "Cannot modify a sign-off on a not active step"
    if "not active step" in msg:
        return (
            "Cannot modify sign-off — the workflow step is not active.",
            [
                "Sign-off steps must be configured with feedback groups and approvers in the blueprint",
                "before they can be activated. Ask a Govern Architect to configure the workflow.",
                "Run: dku govern signoff list <ARTIFACT_ID> to see existing sign-offs.",
            ],
        )

    return None


def handle_api_error(e: Exception, *, project_key: str | None = None) -> None:
    """Convert dataikuapi exceptions to friendly messages and exit.

    Args:
        e: The exception raised by ``dataikuapi``.
        project_key: Key of the project the failed call targeted, if any. Lets a
            project-scoped 401 become a prescriptive key-vs-name message instead
            of a misleading "check your API key"; see
            ``_handle_project_access_denied`` for the full rationale.
    """
    if isinstance(e, (SystemExit, Exit, Abort, BadParameter, CUsageError)):
        raise e

    msg = str(e)
    # Guarantee a non-empty message — some dataikuapi exceptions surface with
    # an empty str() (UnboundLocalError, ValueError raised without args, etc.)
    # and the resulting Rich error box rendered with no body, leaving the
    # agent staring at the box footer with no diagnostic (PENDING 2026-05-28
    # `create-topn` silent-failure entry).
    if not msg.strip():
        msg = (
            f"<{type(e).__name__} with no message - inspect related object state "
            "with a JSON get command, for example "
            "`dku --format json recipe get-settings <RECIPE> -P <PROJECT>`>"
        )

    status = 1
    details: list[str] = []

    # Govern field-type enum miss (e.g. fieldType: 'STRING') — list the
    # accepted values BEFORE the generic 401/404 branches because the message
    # contains "IllegalArgumentException" not "404"/"401".
    field_type_result = _handle_govern_field_type_enum(msg)
    if field_type_result:
        exit_with_error(
            field_type_result[0],
            details=field_type_result[1],
            status=1,
        )

    # Govern blueprint-version save NPE on missing fieldDefinitions key
    field_npe_result = _handle_govern_field_save_npe(msg)
    if field_npe_result:
        exit_with_error(
            field_npe_result[0],
            details=field_npe_result[1],
            status=1,
        )

    # Govern-specific validation errors — prescriptive guidance
    govern_result = _handle_govern_validation(msg)
    if govern_result:
        exit_with_error(
            govern_result[0],
            details=govern_result[1],
            status=1,
        )

    # Dev-plugin-only file access — pushed plugins have no API readback
    not_dev_result = _handle_not_dev_plugin(msg)
    if not_dev_result:
        exit_with_error(
            not_dev_result[0],
            details=not_dev_result[1],
            status=1,
        )

    # Partial output file from a failed build — reads as data corruption
    partial_result = _handle_partial_output_read(msg)
    if partial_result:
        exit_with_error(
            partial_result[0],
            details=partial_result[1],
            status=1,
        )

    # Never-built dataset read — raw DataStoreIOException passthrough
    never_built_result = _handle_never_built_read(msg)
    if never_built_result:
        exit_with_error(
            never_built_result[0],
            details=never_built_result[1],
            status=1,
        )

    # Pivot recipe modality scan — UI-only, restructure to fix
    pivot_result = _handle_pivot_modality_scan(msg)
    if pivot_result:
        exit_with_error(
            pivot_result[0],
            details=pivot_result[1],
            status=1,
        )

    # FoldColumnsByName plugin missing — reinstall CLI; never pd.melt
    fold_result = _handle_fold_plugin_missing(msg)
    if fold_result:
        exit_with_error(
            fold_result[0],
            details=fold_result[1],
            status=1,
        )

    # Invalid / rotated API key — DSS returns NotAuthenticatedException with
    # "Unknown API Key" and neither the substring "401" nor "Unauthorized",
    # so the generic branch below doesn't catch it. Handle this BEFORE the
    # 401 branch so the friendlier message wins.
    invalid_key_result = _handle_invalid_api_key(msg)
    if invalid_key_result:
        exit_with_error(
            invalid_key_result[0],
            details=invalid_key_result[1],
            status=2,
        )

    # Project-scoped 401 — an unknown OR inaccessible project, NOT a bad key.
    # Must run BEFORE the generic 401/Unauthorized branch (the DSS message
    # "Failed to read project permissions" contains "Unauthorized") so agents
    # get key-vs-name guidance instead of a bogus "check your API key". Status 3
    # (not_found), not 2 (auth), so the recovery path is "use the right project
    # key", not "re-authenticate".
    project_denied = _handle_project_access_denied(msg, project_key)
    if project_denied:
        exit_with_error(
            project_denied[0],
            details=project_denied[1],
            status=3,
        )

    # dataikuapi raises generic Exceptions with HTTP status info
    # Check "not found" before "unauthorized" — DSS wraps NotFoundException in UnauthorizedException
    if (
        "NotFoundException" in msg
        or "does not exist" in msg
        or "404" in msg
        or "not found" in msg.lower()
    ):
        status = 3
        details = [
            f"Not found: {msg}",
            "Check the name and project (-P), then list what exists with the",
            "matching `dku <noun> list -P <project>` (e.g. dku dataset list, dku recipe list).",
        ]
    elif "401" in msg or "Unauthorized" in msg:
        status = 2
        details = [
            "Authentication failed — check your API key.",
            "Run 'dku auth login' to re-authenticate.",
        ]
    elif "403" in msg or "Forbidden" in msg:
        status = 2
        details = ["Permission denied — your API key lacks access to this resource."]
    # Match capital-C "Connection" only — NOT a lowercased "connect" substring,
    # which collides with DSS payload fields like "connectionOK".
    elif "Connection" in msg:
        status = 4
        details = [
            f"Cannot connect to DSS: {msg}",
            "Check the URL and ensure DSS is running.",
        ]
    elif is_already_exists_error(e):
        status = 1
        details = [
            f"Resource already exists: {msg}",
            "Use --if-not-exists to skip creation when the resource exists.",
            "Or delete it first with --yes to skip confirmation.",
        ]
    elif "format type" in msg.lower() or "formatType" in msg:
        status = 1
        details = [
            "Dataset has no file format configured.",
            f"DSS: {msg}",
            "Set the dataset format, then rebuild:",
            "  dku dataset set-definition <DATASET> -d "
            '\'{"formatType":"csv","formatParams":{"separator":",",'
            '"parseHeaderRow":true}}\' --deep-merge -P <PROJECT>',
            "  dku recipe run <RECIPE> -P <PROJECT> --wait",
        ]
    elif "projectKey" in msg and "missing" in msg.lower():
        status = 1
        details = [
            "Definition JSON is incomplete.",
            f"DSS: {msg}",
            "set-definition replaces the full object unless you pass "
            "--merge/--deep-merge.",
            "Patch one field with:",
            "  dku dataset set-definition <DATASET> -d '<partial-json>' "
            "--deep-merge -P <PROJECT>",
        ]
    else:
        details = [f"DSS API error: {msg}"]

    exit_with_error(details[0], details=details[1:], status=status)


def handle_errors(func: F) -> F:
    """Decorate a command function with the standard DSS API error mapper.

    When the wrapped command was invoked with a ``project`` keyword (the ``-P`` /
    ``--project`` value, even if it's a display name rather than a KEY), that
    hint is threaded into ``handle_api_error`` so a project-scoped 401 surfaces
    the prescriptive key-vs-name guidance instead of a bogus "check your API
    key" re-auth loop — matching the per-call ``handle_api_error(e,
    project_key=...)`` sites elsewhere.
    """

    @wraps(func)
    def wrapper(*args: object, **kwargs: object) -> object:
        try:
            return func(*args, **kwargs)
        except (Exit, Abort, BadParameter, CUsageError, CExit, CAbort):
            raise
        except Exception as e:
            project_hint = kwargs.get("project")
            handle_api_error(
                e,
                project_key=project_hint if isinstance(project_hint, str) else None,
            )
            return None

    return cast(F, wrapper)
