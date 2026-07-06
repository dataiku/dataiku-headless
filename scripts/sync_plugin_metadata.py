from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_SOURCE = ROOT / "src" / "dku_cli" / "__init__.py"

VERSIONED_JSON = (
    ROOT / "dataiku-mcp" / ".claude-plugin" / "plugin.json",
    ROOT / "dataiku-mcp" / ".codex-plugin" / "plugin.json",
    ROOT / "dataiku-mcp-bundle" / "manifest.json",
)

MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"


def _package_version() -> str:
    match = re.search(
        r'^__version__\s*=\s*"([^"]+)"',
        VERSION_SOURCE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if match is None:
        raise RuntimeError(f"could not read __version__ from {VERSION_SOURCE}")
    return match.group(1)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    version = _package_version()
    for path in VERSIONED_JSON:
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["version"] = version
        _write_json(path, payload)

    marketplace = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    marketplace.setdefault("metadata", {})["version"] = version
    _write_json(MARKETPLACE, marketplace)


if __name__ == "__main__":
    main()
