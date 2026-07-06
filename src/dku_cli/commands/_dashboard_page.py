"""Default page payload for `dku dashboard create`.

DSS renders a dashboard created with an empty settings dict as broken; a new
dashboard needs at least one fully-populated page, mirrored from what the UI
writes on first save.
"""

from __future__ import annotations


def _default_page() -> dict:
    return {
        "id": "page1",
        "title": "Page 1",
        "displayedTitle": "Page 1",
        "show": True,
        "showTitle": False,
        "titleAlign": "CENTER",
        "titleFontColor": "#333",
        "titleFontSize": 28,
        "enableCrossFilters": True,
        "backgroundColor": "#FFFEF9",
        "showFilterPanel": False,
        "filtersParams": {"panelPosition": "TOP"},
        "grid": {"tiles": []},
    }
