from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from studypulse_config import EXAMPLE_CONFIG_PATH, LOCAL_CONFIG_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or update a local StudyPulse config file.")
    parser.add_argument("--force", action="store_true", help="Overwrite config/studypulse.local.json if it already exists.")
    parser.add_argument("--study-root", default="", help="Path to the folder that contains study files.")
    parser.add_argument("--android-dir", default="", help="Folder where Android usage JSON files are collected.")
    parser.add_argument("--email", action="append", default=[], help="Notification recipient. Can be used multiple times.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if LOCAL_CONFIG_PATH.exists() and not args.force:
        print(f"Local config already exists: {LOCAL_CONFIG_PATH}")
        print("Use --force only if you intentionally want to overwrite it.")
        return

    if not EXAMPLE_CONFIG_PATH.exists():
        raise FileNotFoundError(EXAMPLE_CONFIG_PATH)

    LOCAL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(EXAMPLE_CONFIG_PATH, LOCAL_CONFIG_PATH)
    data = json.loads(LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))

    if args.study_root:
        data["study_roots"] = [{"alias": "study-files", "path": str(Path(args.study_root))}]
    if args.android_dir:
        data.setdefault("android", {})["export_inbox_dir"] = str(Path(args.android_dir))
    if args.email:
        data.setdefault("email", {})["recipients"] = args.email

    LOCAL_CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Local config written: {LOCAL_CONFIG_PATH}")
    print("Next: edit this file, then run `python scripts\\doctor.py`.")


if __name__ == "__main__":
    main()
