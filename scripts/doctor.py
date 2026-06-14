from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

from import_android_export import validate_android_usage
from studypulse_config import (
    LOCAL_CONFIG_PATH,
    android_export_inbox_dir,
    config_path,
    configured_email_recipients,
    expand_config_path,
    load_config,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def status(level: str, title: str, detail: str = "") -> tuple[str, str, str]:
    print(f"[{level}] {title}" + (f" - {detail}" if detail else ""))
    return level, title, detail


def latest_android_json(folder: Path) -> Path | None:
    candidates = list(folder.glob("android_usage*.json"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def main() -> None:
    results: list[tuple[str, str, str]] = []
    config = load_config()
    selected_config = config_path()

    results.append(status("OK", "Python", sys.version.split()[0]))
    if selected_config.exists():
        level = "OK" if selected_config == LOCAL_CONFIG_PATH else "WARN"
        detail = str(selected_config)
        if selected_config != LOCAL_CONFIG_PATH:
            detail += "；建议先运行 setup_local_config.py 生成本机配置副本"
        results.append(status(level, "配置文件", detail))
    else:
        results.append(status("FAIL", "配置文件不存在", str(selected_config)))

    android_dir = android_export_inbox_dir(config)
    if android_dir.exists():
        results.append(status("OK", "Android JSON 目录", str(android_dir)))
        latest = latest_android_json(android_dir)
        if latest:
            try:
                data = validate_android_usage(latest)
                results.append(status("OK", "最新 Android JSON 可解析", f"{latest.name}；date={data.get('date')}；apps={len(data.get('apps', []))}"))
            except Exception as exc:
                results.append(status("FAIL", "最新 Android JSON 解析失败", f"{latest}: {exc}"))
        else:
            results.append(status("WARN", "未找到 android_usage*.json", "可以先运行样例模式，或从手机端导出 JSON"))
    else:
        results.append(status("WARN", "Android JSON 目录不存在", str(android_dir)))

    study_roots = config.get("study_roots", [])
    if not study_roots:
        results.append(status("WARN", "学习文件目录未配置", "study_roots 为空"))
    for root in study_roots:
        root_path = expand_config_path(root.get("path", ""))
        level = "OK" if root_path.exists() else "WARN"
        results.append(status(level, f"学习文件目录 {root.get('alias', 'study')}", str(root_path)))

    data_dir = PROJECT_ROOT / "data"
    reports_dir = PROJECT_ROOT / "reports"
    for folder in [data_dir, reports_dir]:
        folder.mkdir(parents=True, exist_ok=True)
        results.append(status("OK", "可写目录", str(folder)))

    adb = shutil.which("adb")
    if config.get("features", {}).get("enable_adb_sync", True):
        results.append(status("OK" if adb else "WARN", "ADB", adb or "未在 PATH 中找到；无线/USB 自动拉取会受影响"))

    if config.get("features", {}).get("enable_ai_review", True):
        api_key_env = config.get("mimo", {}).get("api_key_env", "MIMO_API_KEY")
        results.append(status("OK" if os.environ.get(api_key_env) else "WARN", "MiMo API Key", f"环境变量 {api_key_env}" + (" 已配置" if os.environ.get(api_key_env) else " 未配置")))

    if config.get("features", {}).get("enable_email", True):
        smtp_vars = ["STUDYPULSE_SMTP_HOST", "STUDYPULSE_SMTP_USER", "STUDYPULSE_SMTP_PASSWORD"]
        missing = [name for name in smtp_vars if not os.environ.get(name)]
        recipients = configured_email_recipients(config)
        if missing:
            results.append(status("WARN", "SMTP 环境变量不完整", ", ".join(missing)))
        else:
            results.append(status("OK", "SMTP 环境变量", "已配置"))
        results.append(status("OK" if recipients else "WARN", "邮件接收人", ", ".join(recipients) if recipients else "未配置"))

    node = shutil.which("node")
    results.append(status("OK" if node else "WARN", "Node.js", node or "未找到；仅影响 HTML JS 自动校验"))

    db_path = PROJECT_ROOT / "data" / "studypulse.db"
    if db_path.exists():
        try:
            with sqlite3.connect(db_path) as conn:
                count = conn.execute("SELECT COUNT(*) FROM daily_metrics").fetchone()[0]
            results.append(status("OK", "SQLite 数据库", f"{db_path}；daily_metrics={count}"))
        except Exception as exc:
            results.append(status("WARN", "SQLite 数据库存在但读取失败", str(exc)))
    else:
        results.append(status("WARN", "SQLite 数据库尚未生成", str(db_path)))

    fail_count = sum(1 for level, _, _ in results if level == "FAIL")
    warn_count = sum(1 for level, _, _ in results if level == "WARN")
    print(json.dumps({"fail": fail_count, "warn": warn_count, "config": str(selected_config)}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if fail_count else 0)


if __name__ == "__main__":
    main()
