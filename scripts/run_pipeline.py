from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from studypulse_config import android_export_inbox_dir, load_config


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
STATUS_PATH = PROJECT_ROOT / "data" / "pipeline_status.json"
ADB_STATUS_PATH = PROJECT_ROOT / "data" / "adb_sync_status.json"


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def write_status(status: dict) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"status": "invalid", "message": f"{path.name} could not be parsed: {exc}"}


def mark_step(status: dict, name: str, state: str, message: str = "", detail: dict | None = None) -> None:
    steps = status.setdefault("steps", {})
    item = steps.setdefault(name, {})
    item["status"] = state
    item["updated_at"] = now_text()
    if message:
        item["message"] = message
    if detail is not None:
        item["detail"] = detail
    write_status(status)


def find_latest_android_export(folder: Path) -> Path | None:
    candidates = list(folder.glob("android_usage*.json"))
    if candidates:
        return max(candidates, key=lambda path: path.stat().st_mtime)
    return None


def describe_android_export_folder(folder: Path) -> None:
    all_usage_files = sorted(folder.glob("android_usage*"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not all_usage_files:
        log(f"Progress: no android_usage* files found in {folder}")
        return

    log(f"Progress: android_usage* files found in {folder}:")
    for path in all_usage_files[:10]:
        suffix_note = "" if path.suffix.lower() == ".json" else " (ignored: extension is not .json)"
        modified = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        log(f"  - {path.name} | {path.stat().st_size} bytes | modified {modified}{suffix_note}")


def ensure_android_export_folder(config: dict) -> Path:
    folder = android_export_inbox_dir(config)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def run(args: list[str], required: bool = True) -> int:
    log("Run: " + " ".join(args))
    result = subprocess.run(args, cwd=PROJECT_ROOT, check=False)
    if required and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, args)
    if not required and result.returncode != 0:
        log(f"Progress: optional step failed with exit code {result.returncode}")
    return result.returncode


def sync_android_json_via_adb(config: dict, export_folder: Path) -> dict:
    script = PROJECT_ROOT / "scripts" / "sync_android_json_adb.ps1"
    if not script.exists():
        detail = {"status": "skipped", "message": "ADB sync script not found"}
        ADB_STATUS_PATH.write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
        return detail

    android = config.get("android", {})
    package_name = str(android.get("adb_package_name") or "com.studypulse.android")
    remote_dir = str(android.get("adb_remote_dir") or f"/sdcard/Android/data/{package_name}/files/exports")

    if ADB_STATUS_PATH.exists():
        ADB_STATUS_PATH.unlink()

    run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-PackageName",
            package_name,
            "-RemoteDir",
            remote_dir,
            "-DestinationDir",
            str(export_folder),
            "-StatusPath",
            str(ADB_STATUS_PATH),
        ],
        required=False,
    )
    detail = read_json(ADB_STATUS_PATH)
    if not detail:
        detail = {"status": "unknown", "message": "ADB sync finished without status file"}
    return detail


def adb_step_state(detail: dict) -> str:
    status = str(detail.get("status") or "unknown")
    if status == "success":
        return "completed"
    if status == "failed":
        return "warning"
    return "skipped"


def main(argv: list[str]) -> None:
    args_in = argv[1:]
    skip_email = "--skip-email" in args_in
    sample_mode = "--sample" in args_in
    explicit_args = [arg for arg in args_in if not arg.startswith("--")]
    config = load_config()
    features = config.get("features", {})
    if sample_mode:
        os.environ["STUDYPULSE_SAMPLE"] = "1"

    status = {
        "started_at": now_text(),
        "finished_at": None,
        "status": "running",
        "skip_email": skip_email,
        "sample_mode": sample_mode,
        "android_export_folder": None,
        "selected_android_json": None,
        "adb_sync": {},
        "reports": {
            "static_html": str(PROJECT_ROOT / "reports" / "studypulse_sample_report.html"),
            "interactive_html": str(PROJECT_ROOT / "reports" / "studypulse_ui_interactive.html"),
        },
        "steps": {},
    }
    write_status(status)

    export_folder = ensure_android_export_folder(config)
    status["android_export_folder"] = str(export_folder)
    write_status(status)
    log(f"Progress: Android JSON folder {export_folder}")

    if sample_mode:
        adb_detail = {"status": "skipped", "message": "sample mode skips ADB sync"}
        status["adb_sync"] = adb_detail
        mark_step(status, "adb_sync", "skipped", "样例模式跳过 ADB 同步", adb_detail)
    elif features.get("enable_adb_sync", True):
        log("Progress: sync Android JSON from connected device if available")
        mark_step(status, "adb_sync", "running", "尝试从已连接 Android 设备同步 JSON")
        adb_detail = sync_android_json_via_adb(config, export_folder)
        status["adb_sync"] = adb_detail
        mark_step(status, "adb_sync", adb_step_state(adb_detail), str(adb_detail.get("message") or "ADB sync finished"), adb_detail)
    else:
        adb_detail = {"status": "skipped", "message": "ADB sync disabled by config"}
        status["adb_sync"] = adb_detail
        mark_step(status, "adb_sync", "skipped", "配置已关闭 ADB 同步", adb_detail)
    describe_android_export_folder(export_folder)

    explicit_android_json = explicit_args[0] if explicit_args else None
    if sample_mode and not explicit_android_json:
        android_json = PROJECT_ROOT / "sample_data" / "android_usage_2026-06-12.json"
    else:
        android_json = Path(explicit_android_json).expanduser().resolve() if explicit_android_json else find_latest_android_export(export_folder)

    if android_json:
        log(f"Progress: import Android data {android_json}")
        status["selected_android_json"] = str(android_json)
        write_status(status)
        mark_step(status, "import_android_json", "running", str(android_json))
        run([PYTHON, str(PROJECT_ROOT / "scripts" / "import_android_export.py"), str(android_json)])
        mark_step(status, "import_android_json", "completed", str(android_json))
    else:
        log(f"Progress: no android_usage*.json found in {export_folder}; keep existing Android data")
        mark_step(status, "import_android_json", "warning", "未找到新的 android_usage*.json，沿用已有数据库数据")

    steps = [
        ("scan_windows_files", "Progress: scan Windows study folders", [PYTHON, str(PROJECT_ROOT / "scripts" / "scan_windows_files.py")], True),
        ("build_database", "Progress: build SQLite database", [PYTHON, str(PROJECT_ROOT / "scripts" / "build_database.py")], True),
        ("generate_report", "Progress: generate HTML report", [PYTHON, str(PROJECT_ROOT / "scripts" / "generate_report.py")], True),
        ("generate_interactive_ui", "Progress: generate interactive product UI", [PYTHON, str(PROJECT_ROOT / "scripts" / "generate_interactive_ui.py")], True),
    ]
    if features.get("enable_ai_review", True):
        steps.insert(2, ("generate_ai_review", "Progress: generate MiMo AI review", [PYTHON, str(PROJECT_ROOT / "scripts" / "generate_ai_review.py")], True))
    else:
        mark_step(status, "generate_ai_review", "skipped", "配置已关闭 AI 复盘")

    if skip_email:
        mark_step(status, "send_email", "skipped", "手动运行使用 --skip-email，未发送邮件")
    elif features.get("enable_email", True):
        steps.append(("send_email", "Progress: send mobile email notification if configured", [PYTHON, str(PROJECT_ROOT / "scripts" / "send_report_email.py")], False))
    else:
        mark_step(status, "send_email", "skipped", "配置已关闭邮件发送")

    try:
        for name, message, args, required in steps:
            log(message)
            mark_step(status, name, "running", message)
            code = run(args, required=required)
            mark_step(status, name, "completed" if code == 0 else "warning", f"exit_code={code}")
    except Exception as exc:
        status["status"] = "failed"
        status["finished_at"] = now_text()
        status["error"] = str(exc)
        write_status(status)
        raise

    status["status"] = "completed"
    status["finished_at"] = now_text()
    write_status(status)
    log("Pipeline completed.")
    log(f"Report: {PROJECT_ROOT / 'reports' / 'studypulse_sample_report.html'}")
    log(f"Interactive UI: {PROJECT_ROOT / 'reports' / 'studypulse_ui_interactive.html'}")
    log("Progress: refresh interactive product UI with final pipeline status")
    run([PYTHON, str(PROJECT_ROOT / "scripts" / "generate_interactive_ui.py")], required=False)


if __name__ == "__main__":
    main(sys.argv)
