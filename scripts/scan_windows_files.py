from __future__ import annotations

import csv
import hashlib
from datetime import datetime, date, timedelta
from pathlib import Path

from studypulse_config import expand_config_path, load_config


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "scans"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def scan_root(alias: str, root_path: Path, extensions: set[str], target_date: date) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not root_path.exists():
        return rows

    for path in root_path.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in extensions:
            continue
        stat = path.stat()
        modified_at = datetime.fromtimestamp(stat.st_mtime)
        relative_path = path.relative_to(root_path).as_posix()
        rows.append(
            {
                "date": modified_at.date().isoformat(),
                "root_alias": alias,
                "relative_path": relative_path,
                "path_hash": sha256_text(f"{alias}/{relative_path}"),
                "extension": path.suffix.lower(),
                "file_size_bytes": str(stat.st_size),
                "last_modified_at": modified_at.strftime("%Y-%m-%d %H:%M:%S"),
                "activity_type": "modified",
            }
        )
    return rows


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "date",
        "root_alias",
        "relative_path",
        "path_hash",
        "extension",
        "file_size_bytes",
        "last_modified_at",
        "activity_type",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    config = load_config()
    target_date = date.today()
    extensions = {extension.lower() for extension in config["tracked_extensions"]}
    all_rows: list[dict[str, str]] = []

    for root in config["study_roots"]:
        alias = root["alias"]
        path = expand_config_path(root["path"])
        rows = scan_root(alias, path, extensions, target_date)
        all_rows.extend(rows)
        today_count = sum(1 for row in rows if row["date"] == target_date.isoformat())
        recent_start = target_date - timedelta(days=6)
        recent_count = sum(1 for row in rows if recent_start.isoformat() <= row["date"] <= target_date.isoformat())
        print(f"{alias}: {len(rows)} tracked files total, {recent_count} modified in last 7 days, {today_count} modified today")

    output_path = OUTPUT_DIR / f"windows_file_activity_{target_date.isoformat()}.csv"
    write_csv(all_rows, output_path)
    print(f"Scan result written to: {output_path}")


if __name__ == "__main__":
    main()
