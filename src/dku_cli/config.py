"""Config file management using platformdirs + TOML."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


# `ensure_exists=False`: do not create the dir at import time. _write_toml
# creates it lazily on first write. Importing must never crash on a
# read-only ~/.config (e.g. inside a Code Studio pod where the dir is
# root-owned and the runtime user can't mkdir into it).
CONFIG_DIR = Path(user_config_dir("dku", ensure_exists=False))
CONFIG_FILE = CONFIG_DIR / "config.toml"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.toml"


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text())


def _write_toml(path: Path, data: dict[str, Any]) -> None:
    """Write a dict as TOML. Minimal writer — no third-party dep needed."""
    lines: list[str] = []
    # Write top-level keys first
    for key, value in data.items():
        if not isinstance(value, dict):
            lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
    # Then sections
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"\n[{_toml_key(key)}]")
            for k, v in value.items():
                lines.append(f"{_toml_key(k)} = {_toml_value(v)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def _toml_value(v: Any) -> str:
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _toml_key(key: str) -> str:
    return json.dumps(str(key))


def get_config() -> dict[str, Any]:
    return _read_toml(CONFIG_FILE)


def get_profile_config(profile: str) -> dict[str, Any]:
    config = get_config()
    return config.get(profile, {})


def set_profile_config(profile: str, url: str, node_type: str | None = None) -> None:
    config = get_config()
    profile_cfg = config.get(profile, {})
    if not isinstance(profile_cfg, dict):
        profile_cfg = {}
    profile_cfg["url"] = url
    if node_type is not None:
        profile_cfg["node_type"] = node_type
    config[profile] = profile_cfg
    # Track active profile
    config["active_profile"] = profile
    _write_toml(CONFIG_FILE, config)


def set_profile_node_type(profile: str, node_type: str) -> None:
    """Persist the DSS node type (design/automation/govern/deployer/apinode) for a profile."""
    config = get_config()
    profile_cfg = config.get(profile, {})
    if not isinstance(profile_cfg, dict):
        profile_cfg = {}
    profile_cfg["node_type"] = node_type
    config[profile] = profile_cfg
    _write_toml(CONFIG_FILE, config)


def get_profile_node_type(profile: str) -> str | None:
    """Return the stored node type for a profile, or None if not known."""
    return get_profile_config(profile).get("node_type")


def get_active_profile() -> str:
    config = get_config()
    return config.get("active_profile", "default")


def set_active_profile(profile: str) -> None:
    config = get_config()
    config["active_profile"] = profile
    _write_toml(CONFIG_FILE, config)


def get_all_profiles() -> dict[str, dict[str, Any]]:
    config = get_config()
    return {k: v for k, v in config.items() if isinstance(v, dict)}


def delete_profile_config(profile: str) -> bool:
    """Remove a profile from config and update the active profile if needed."""
    config = get_config()
    removed = config.pop(profile, None)

    if config.get("active_profile") == profile:
        remaining_profiles = sorted(k for k, v in config.items() if isinstance(v, dict))
        if "default" in remaining_profiles:
            config["active_profile"] = "default"
        elif remaining_profiles:
            config["active_profile"] = remaining_profiles[0]
        else:
            config.pop("active_profile", None)

    _write_toml(CONFIG_FILE, config)
    return removed is not None


def clear_profile_configs() -> int:
    """Remove all profile sections while preserving non-profile settings."""
    config = get_config()
    profile_names = [k for k, v in config.items() if isinstance(v, dict)]

    for profile in profile_names:
        del config[profile]

    config.pop("active_profile", None)
    _write_toml(CONFIG_FILE, config)
    return len(profile_names)


def get_default_project() -> str | None:
    profile = get_active_profile()
    return get_profile_config(profile).get("default_project")


def get_profile_credential_store(profile: str) -> str | None:
    return get_profile_config(profile).get("credential_store")


def set_profile_credential_store(profile: str, store: str) -> None:
    config = get_config()
    profile_cfg = config.get(profile, {})
    if not isinstance(profile_cfg, dict):
        profile_cfg = {}
    profile_cfg["credential_store"] = store
    config[profile] = profile_cfg
    _write_toml(CONFIG_FILE, config)


def set_default_project(project_key: str) -> None:
    config = get_config()
    profile = get_active_profile()
    if profile not in config:
        config[profile] = {}
    config[profile]["default_project"] = project_key
    _write_toml(CONFIG_FILE, config)


def get_dangerous_mode() -> bool:
    config = get_config()
    return bool(config.get("dangerous_mode", False))


def set_dangerous_mode(enabled: bool) -> None:
    config = get_config()
    config["dangerous_mode"] = bool(enabled)
    _write_toml(CONFIG_FILE, config)
