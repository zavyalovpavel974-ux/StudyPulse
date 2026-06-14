from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
LOCAL_CONFIG_PATH = CONFIG_DIR / "studypulse.local.json"
LEGACY_CONFIG_PATH = CONFIG_DIR / "studypulse_config.json"
EXAMPLE_CONFIG_PATH = CONFIG_DIR / "studypulse.example.json"


DEFAULT_CONFIG: dict[str, Any] = {
    "android": {
        "export_inbox_dir": "%USERPROFILE%\\Desktop\\.json",
        "adb_package_name": "com.studypulse.android",
        "adb_remote_dir": "/sdcard/Android/data/com.studypulse.android/files/exports",
    },
    "study_roots": [],
    "tracked_extensions": [
        ".R",
        ".md",
        ".Rmd",
        ".qmd",
        ".csv",
        ".xlsx",
        ".docx",
        ".pptx",
        ".html",
    ],
    "mimo": {
        "provider": "Xiaomi MiMo",
        "model": "mimo-v2.5-pro",
        "openai_compatible": True,
        "api_base_url": "https://token-plan-cn.xiaomimimo.com/v1",
        "api_key_env": "MIMO_API_KEY",
    },
    "email": {
        "recipients": [],
        "sender_env": "STUDYPULSE_NOTIFY_EMAIL_FROM",
        "recipients_env": "STUDYPULSE_NOTIFY_EMAIL_TO",
    },
    "features": {
        "enable_adb_sync": True,
        "enable_ai_review": True,
        "enable_email": True,
    },
}


def configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except OSError:
                pass


configure_console_encoding()


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def config_path() -> Path:
    explicit = os.environ.get("STUDYPULSE_CONFIG", "").strip()
    if explicit:
        return Path(os.path.expandvars(explicit)).expanduser()
    if LOCAL_CONFIG_PATH.exists():
        return LOCAL_CONFIG_PATH
    if LEGACY_CONFIG_PATH.exists():
        return LEGACY_CONFIG_PATH
    return EXAMPLE_CONFIG_PATH


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return deepcopy(DEFAULT_CONFIG)
    data = json.loads(path.read_text(encoding="utf-8"))
    return deep_merge(DEFAULT_CONFIG, data)


def expand_config_path(value: str | Path, *, base: Path | None = None) -> Path:
    text = str(value)
    expanded = Path(os.path.expandvars(text)).expanduser()
    if expanded.is_absolute():
        return expanded
    return (base or PROJECT_ROOT) / expanded


def android_export_inbox_dir(config: dict[str, Any] | None = None) -> Path:
    cfg = config or load_config()
    return expand_config_path(cfg.get("android", {}).get("export_inbox_dir", "%USERPROFILE%\\Desktop\\.json"))


def configured_email_recipients(config: dict[str, Any] | None = None) -> list[str]:
    cfg = config or load_config()
    recipients = cfg.get("email", {}).get("recipients", [])
    return [str(item).strip() for item in recipients if str(item).strip()]
