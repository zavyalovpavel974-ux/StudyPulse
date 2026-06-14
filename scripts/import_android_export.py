from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = PROJECT_ROOT / "data" / "android_exports"


def validate_android_usage(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}. "
            "The Android export may be incomplete or saved with the wrong format."
        ) from exc

    required = {"schema_version", "device_type", "date", "generated_at", "apps"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(sorted(missing))}")
    if data["device_type"] != "android":
        raise ValueError(f"Expected device_type=android, got {data['device_type']!r}")
    if not isinstance(data["apps"], list):
        raise ValueError("Field apps must be a list")
    for index, app in enumerate(data["apps"], start=1):
        for key in ["package_name", "foreground_minutes", "open_count"]:
            if key not in app:
                raise ValueError(f"App #{index} missing field: {key}")
    return data


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        raise SystemExit("Usage: python scripts/import_android_export.py <android_usage.json>")

    source = Path(argv[1]).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)

    data = validate_android_usage(source)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    target = EXPORT_DIR / f"android_usage_{data['date']}.json"
    shutil.copy2(source, target)
    print(f"Imported Android usage JSON: {target}")
    print(f"Date: {data['date']}")
    print(f"Apps: {len(data['apps'])}")


if __name__ == "__main__":
    main(sys.argv)
