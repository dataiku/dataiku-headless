"""Excel sheet-targeting flags (upload/create-from-file) and detect --keep-format."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tests.commands.dataset.helpers import app, runner


def _excel_settings(format_type: str = "excel") -> MagicMock:
    settings = MagicMock()
    settings.get_raw.return_value = {
        "formatType": format_type,
        "formatParams": {
            "sheetSelectionMode": "NAMES",
            "sheets": "*First Sheet",
            "parseHeaderRow": False,
        },
        "schema": {"columns": []},
    }
    return settings


DETECTED_COLS = [
    {"name": "ID", "type": "bigint"},
    {"name": "Gender", "type": "string"},
]


def test_upload_sheet_targets_named_sheet(patch_client, tmp_path):
    """--sheet rewrites formatParams (NAMES + '*<name>' + parseHeaderRow) and
    saves the re-detected schema."""
    book = tmp_path / "book.xlsx"
    book.write_bytes(b"fake")
    ds = patch_client.get_project("PROJ1").get_dataset("book")
    settings = _excel_settings()
    ds.get_settings.return_value = settings

    with patch(
        "dku_cli.commands.dataset._redetect_schema_keeping_format",
        return_value=(settings, DETECTED_COLS, []),
    ) as redetect:
        result = runner.invoke(
            app,
            [
                "dataset",
                "upload",
                "book",
                str(book),
                "--sheet",
                "Cleaned Data",
                "--project",
                "PROJ1",
            ],
        )
    assert result.exit_code == 0, result.output
    raw = settings.get_raw.return_value
    assert raw["formatParams"]["sheets"] == "*Cleaned Data"
    assert raw["formatParams"]["sheetSelectionMode"] == "NAMES"
    assert raw["formatParams"]["parseHeaderRow"] is True
    assert raw["schema"] == {"columns": DETECTED_COLS, "userModified": True}
    redetect.assert_called_once()
    assert "Targeted sheet 'Cleaned Data': 2 columns" in result.output


def test_upload_sheet_indices_and_sheets_to_column(patch_client, tmp_path):
    book = tmp_path / "book.xlsx"
    book.write_bytes(b"fake")
    ds = patch_client.get_project("PROJ1").get_dataset("book")
    settings = _excel_settings()
    ds.get_settings.return_value = settings

    with patch(
        "dku_cli.commands.dataset._redetect_schema_keeping_format",
        return_value=(settings, DETECTED_COLS, []),
    ):
        result = runner.invoke(
            app,
            [
                "dataset",
                "upload",
                "book",
                str(book),
                "--sheet-indices",
                "0,1",
                "--sheets-to-column",
                "--project",
                "PROJ1",
            ],
        )
    assert result.exit_code == 0, result.output
    raw = settings.get_raw.return_value
    assert raw["formatParams"]["sheetSelectionMode"] == "INDICES"
    assert raw["formatParams"]["sheets"] == "0,1"
    assert raw["formatParams"]["sheetsToColumn"] is True
    assert "FIRST column" in result.output


def test_upload_sheet_flags_mutually_exclusive(patch_client, tmp_path):
    book = tmp_path / "book.xlsx"
    book.write_bytes(b"fake")
    result = runner.invoke(
        app,
        [
            "dataset",
            "upload",
            "book",
            str(book),
            "--sheet",
            "A",
            "--all-sheets",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "at most one of" in result.output


def test_upload_sheet_rejects_no_autodetect(patch_client, tmp_path):
    book = tmp_path / "book.xlsx"
    book.write_bytes(b"fake")
    result = runner.invoke(
        app,
        [
            "dataset",
            "upload",
            "book",
            str(book),
            "--sheet",
            "A",
            "--no-autodetect",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "--no-autodetect" in result.output


def test_upload_sheet_on_non_excel_errors(patch_client, tmp_path):
    """--sheet on a CSV upload fails with a prescriptive error."""
    f = tmp_path / "data.csv"
    f.write_text("a,b\n1,2\n")
    ds = patch_client.get_project("PROJ1").get_dataset("data")
    ds.get_settings.return_value = _excel_settings(format_type="csv")

    result = runner.invoke(
        app,
        [
            "dataset",
            "upload",
            "data",
            str(f),
            "--sheet",
            "Sheet1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "only apply to Excel files" in result.output
    assert "'csv'" in result.output


def test_create_from_file_sheet_flag(patch_client, tmp_path):
    """create-from-file forwards sheet targeting after creation."""
    book = tmp_path / "book.xlsx"
    book.write_bytes(b"fake")
    proj = patch_client.get_project("PROJ1")
    # dataset does not exist yet
    proj.get_dataset.return_value.get_schema.side_effect = Exception("404 not found")
    ds = proj.create_upload_dataset.return_value
    settings = _excel_settings()
    ds.get_settings.return_value = settings
    # sheet targeting resolves the dataset via get_project().get_dataset() —
    # make that return the created mock after creation
    with patch(
        "dku_cli.commands.dataset._redetect_schema_keeping_format",
        return_value=(settings, DETECTED_COLS, []),
    ):
        with patch(
            "dku_cli.commands.dataset._apply_excel_sheet_targeting"
        ) as apply_sheets:
            result = runner.invoke(
                app,
                [
                    "dataset",
                    "create-from-file",
                    "book",
                    str(book),
                    "--sheet",
                    "Cleaned Data",
                    "--project",
                    "PROJ1",
                ],
            )
    assert result.exit_code == 0, result.output
    apply_sheets.assert_called_once()
    assert apply_sheets.call_args.kwargs["sheet"] == "Cleaned Data"


def test_detect_keep_format_preserves_params_and_saves_schema(patch_client):
    """--keep-format re-infers the schema without touching formatParams."""
    settings = _excel_settings()
    with patch(
        "dku_cli.commands.dataset._redetect_schema_keeping_format",
        return_value=(settings, DETECTED_COLS, []),
    ) as redetect:
        result = runner.invoke(
            app,
            [
                "dataset",
                "detect",
                "pb",
                "--keep-format",
                "--infer-types",
                "--save",
                "--project",
                "PROJ1",
            ],
        )
    assert result.exit_code == 0, result.output
    redetect.assert_called_once()
    raw = settings.get_raw.return_value
    # format params untouched, schema replaced by the fresh detection
    assert raw["formatParams"]["sheets"] == "*First Sheet"
    assert raw["schema"] == {"columns": DETECTED_COLS, "userModified": True}
    settings.save.assert_called_once()
    assert "excel format, 2 columns" in result.output


def test_redetect_schema_keeping_format_reads_detected_schema(patch_client):
    """The helper posts detectPossibleFormats=False and prefers detectedSchema
    over newSchema (which silently keeps a stale mismatched schema)."""
    from dku_cli.commands.dataset import _redetect_schema_keeping_format

    patch_client._perform_json.return_value = {"jobId": "j1"}
    detection_result = {
        "format": {
            "ok": True,
            "schemaDetection": {
                "detectedSchema": {"columns": DETECTED_COLS},
                "newSchema": {"columns": [{"name": "col_0", "type": "string"}]},
                "textReasons": ["Mismatch in number of columns"],
            },
        }
    }
    fake_future = MagicMock()
    fake_future.wait_for_result.return_value = detection_result
    with patch("dataikuapi.dss.future.DSSFuture", return_value=fake_future):
        _settings, cols, reasons = _redetect_schema_keeping_format(
            patch_client, "PROJ1", "pb", infer_types=True
        )
    assert cols == DETECTED_COLS
    assert reasons == ["Mismatch in number of columns"]
    body = patch_client._perform_json.call_args.kwargs["body"]
    assert body == {"detectPossibleFormats": False, "inferStorageTypes": True}
