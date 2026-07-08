"""Tests for ${...} variable expansion in count/query table resolution and
the multi-sheet Excel upload warning."""

from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import MagicMock

from typer.testing import CliRunner

from dku_cli.commands.dataset import (
    _collect_dss_variables,
    _excel_sheet_names,
    _expand_dss_variables,
    _resolve_sql_table,
    _table_template_variables,
    _warn_multi_sheet_excel,
)
from dku_cli.main import app

runner = CliRunner()


# --- ${...} template expansion (#263) ---


def test_expand_dss_variables_basic():
    variables = {"NODE_ENV": "PRD", "projectKey": "P"}
    assert _expand_dss_variables("${NODE_ENV}_ORDERS", variables) == "PRD_ORDERS"
    assert _expand_dss_variables("${projectKey}_${NODE_ENV}", variables) == "P_PRD"


def test_expand_dss_variables_leaves_unknown_tokens():
    assert _expand_dss_variables("${UNKNOWN}_X", {"a": 1}) == "${UNKNOWN}_X"


def test_expand_dss_variables_stringifies_values():
    assert _expand_dss_variables("v${n}", {"n": 3}) == "v3"


def test_resolve_sql_table_expands_instance_variables():
    ds_def = {
        "type": "Snowflake",
        "params": {
            "connection": "SF",
            "table": "${NODE_PREFIX}_${projectKey}_ORDERS",
            "schema": "${NODE_SCHEMA}",
        },
    }
    resolved = _resolve_sql_table(
        ds_def, "PROJ", {"NODE_PREFIX": "PRD", "NODE_SCHEMA": "ANALYTICS"}
    )
    assert resolved == ("SF", "ANALYTICS.PRD_PROJ_ORDERS")


def test_resolve_sql_table_without_variables_keeps_project_key_only():
    ds_def = {
        "type": "Snowflake",
        "params": {"connection": "SF", "table": "${projectKey}_ORDERS"},
    }
    assert _resolve_sql_table(ds_def, "PROJ") == ("SF", "PROJ_ORDERS")


def test_table_template_variables_skips_untemplated():
    client = MagicMock()
    ds_def = {"params": {"connection": "SF", "table": "${projectKey}_ORDERS"}}
    assert _table_template_variables(client, "P", ds_def) is None
    client.get_global_variables.assert_not_called()
    client.get_project.assert_not_called()


def test_table_template_variables_fetches_when_templated():
    client = MagicMock()
    client.get_global_variables.return_value = {"NODE_ENV": "PRD"}
    client.get_project.return_value.get_variables.return_value = {
        "standard": {"tier": "gold"},
        "local": {"tier": "silver"},
    }
    ds_def = {"params": {"connection": "SF", "table": "${NODE_ENV}_ORDERS"}}
    variables = _table_template_variables(client, "P", ds_def)
    assert variables["NODE_ENV"] == "PRD"
    assert variables["tier"] == "silver"  # local overrides standard
    assert variables["projectKey"] == "P"


def test_collect_dss_variables_tolerates_permission_errors():
    client = MagicMock()
    client.get_global_variables.side_effect = Exception("403 admin only")
    client.get_project.return_value.get_variables.return_value = {
        "standard": {"env": "dev"},
        "local": {},
    }
    variables = _collect_dss_variables(client, "P")
    assert variables == {"env": "dev", "projectKey": "P"}


# --- multi-sheet Excel warning (#233) ---


def _write_xlsx(path: Path, sheet_names: list[str], hidden: list[str] | None = None):
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    sheets = "".join(
        f'<sheet name="{n}" sheetId="{i + 1}" r:id="rId{i + 1}"'
        + (' state="hidden"' if hidden and n in hidden else "")
        + "/>"
        for i, n in enumerate(sheet_names)
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{ns}" xmlns:r="{rel_ns}">'
            f"<sheets>{sheets}</sheets></workbook>",
        )


def test_excel_sheet_names_reads_workbook(tmp_path):
    path = tmp_path / "book.xlsx"
    _write_xlsx(path, ["Summary", "Data", "Extra"])
    assert _excel_sheet_names(path) == ["Summary", "Data", "Extra"]


def test_excel_sheet_names_skips_hidden_sheets(tmp_path):
    path = tmp_path / "book.xlsx"
    _write_xlsx(path, ["Summary", "Old"], hidden=["Old"])
    assert _excel_sheet_names(path) == ["Summary"]


def test_excel_sheet_names_tolerates_non_zip(tmp_path):
    path = tmp_path / "legacy.xls"
    path.write_bytes(b"\xd0\xcf\x11\xe0 not a zip")
    assert _excel_sheet_names(path) == []


def test_warn_multi_sheet_excel_warns(tmp_path, capsys):
    path = tmp_path / "multi.xlsx"
    _write_xlsx(path, ["Summary", "Data"])
    _warn_multi_sheet_excel(path, "ds1", "PROJ")
    err = capsys.readouterr().err
    assert "2 sheets" in err
    assert "'Summary'" in err
    assert "Data" in err
    assert "--sheet" in err


def test_warn_multi_sheet_excel_silent_for_single_sheet(tmp_path, capsys):
    path = tmp_path / "single.xlsx"
    _write_xlsx(path, ["Only"])
    _warn_multi_sheet_excel(path, "ds1", "PROJ")
    assert capsys.readouterr().err == ""


def test_warn_multi_sheet_excel_ignores_csv(tmp_path, capsys):
    path = tmp_path / "data.csv"
    path.write_text("a,b\n1,2\n")
    _warn_multi_sheet_excel(path, "ds1", "PROJ")
    assert capsys.readouterr().err == ""


def test_upload_multi_sheet_xlsx_warns(patch_client, tmp_path):
    path = tmp_path / "multi.xlsx"
    _write_xlsx(path, ["Summary", "Data", "Extra"])
    result = runner.invoke(
        app,
        [
            "dataset",
            "upload",
            "ds1",
            str(path),
            "--no-autodetect",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "only 'Summary' is bound" in result.output
    assert "ignored: Data, Extra" in result.output


def test_upload_with_sheet_flag_does_not_warn_multi_sheet(patch_client, tmp_path):
    """When the agent already targets a sheet, the multi-sheet nag is noise."""
    path = tmp_path / "data.csv"
    path.write_text("a,b\n1,2\n")
    result = runner.invoke(
        app,
        ["dataset", "upload", "ds1", str(path), "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "sheets" not in result.output.lower()
