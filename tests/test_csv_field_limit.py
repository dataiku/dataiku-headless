"""The CLI must raise the stdlib csv field-size limit at startup.

dataikuapi streams dataset rows as CSV and parses them with the `csv` module.
Its default field_size_limit (131072) rejects large cells — geometry WKT,
JSON blobs, long text — with "field larger than field limit", which surfaces
as a confusing DSS API error on `dataset head` / `sql query`. Importing the
root app must lift that limit (module global → fixes every iter_rows read).
"""

from __future__ import annotations

import csv


def test_import_main_raises_csv_field_limit():
    import dku_cli.main  # noqa: F401  (import triggers the startup raise)

    # Default is 131072; we lift it far beyond any realistic cell size.
    assert csv.field_size_limit() > 131072
    assert csv.field_size_limit() >= 1_000_000
