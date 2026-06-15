from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from studypulse_config import focus_export_dir, load_config


def validate_focus_export(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("Focus export must be a JSON object")
    if not data.get("date"):
        raise ValueError("Focus export requires top-level date, for example 2026-06-14")
    sessions = data.get("sessions")
    if not isinstance(sessions, list):
        raise ValueError("Focus export requires sessions list")
    for index, item in enumerate(sessions, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"sessions[{index}] must be an object")
        if "minutes" not in item and "duration_minutes" not in item:
            raise ValueError(f"sessions[{index}] requires minutes or duration_minutes")
    return data


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/import_focus_export.py <focus_json>")
    source = Path(sys.argv[1]).expanduser().resolve()
    data = validate_focus_export(source)
    target_dir = focus_export_dir(load_config())
    target_dir.mkdir(parents=True, exist_ok=True)
    date_value = str(data["date"])
    target = target_dir / f"focus_{date_value}.json"
    shutil.copy2(source, target)
    print(f"Imported focus JSON: {target}")


if __name__ == "__main__":
    main()
