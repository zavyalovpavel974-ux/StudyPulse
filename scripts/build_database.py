from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from studypulse_config import expand_config_path, focus_export_dir, load_config


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "studypulse.db"
SCHEMA_PATH = PROJECT_ROOT / "schema.sql"
RULES_PATH = PROJECT_ROOT / "config" / "app_category_rules.csv"
ANDROID_JSON_PATH = PROJECT_ROOT / "sample_data" / "android_usage_2026-06-12.json"
ANDROID_EXPORT_DIR = PROJECT_ROOT / "data" / "android_exports"
WINDOWS_FILE_CSV_PATH = PROJECT_ROOT / "sample_data" / "windows_file_activity_2026-06-12.csv"
WINDOWS_SCAN_DIR = PROJECT_ROOT / "data" / "scans"
R_HISTORY_PATH = PROJECT_ROOT / "sample_data" / "r_history_sample.Rhistory"
DAILY_SAMPLE_PATH = PROJECT_ROOT / "sample_data" / "daily_metrics_sample.csv"
TOMATO_TODO_PACKAGE = "com.plan.kot32.tomatotime"
DISTRACTING_CATEGORIES = {"social", "entertainment", "game"}


R_FUNCTION_RE = re.compile(r"(?<![A-Za-z0-9_.])([A-Za-z.][A-Za-z0-9_.]*)\s*\(")
R_LIBRARY_RE = re.compile(r"\b(?:library|require)\s*\(\s*['\"]?([A-Za-z0-9_.]+)")

APP_NAME_MAP = {
    "com.tencent.mm": "微信",
    "com.ss.android.ugc.aweme": "抖音",
    "com.tencent.qqmusic": "QQ音乐",
    "com.dongqiudi.news": "懂球帝",
    "com.tencent.mobileqq": "QQ",
    "com.heytap.browser": "浏览器",
    "com.quark.browser": "夸克",
    "com.android.launcher": "系统桌面",
    "com.android.settings": "设置",
    "com.studypulse.android": "StudyPulse",
    "com.baidu.netdisk": "百度网盘",
    "tv.danmaku.bili": "哔哩哔哩",
    "com.taobao.taobao": "淘宝",
    "com.taobao.idlefish": "闲鱼",
    "com.xunmeng.pinduoduo": "拼多多",
    "com.jingdong.app.mall": "京东",
    "com.android.mms": "短信",
    "com.android.incallui": "电话",
    "com.coloros.gallery3d": "相册",
    "com.coloros.filemanager": "文件管理",
    "com.android.documentsui": "文件",
    "com.google.android.gms": "Google Play 服务",
    "com.google.android.googlequicksearchbox": "Google 搜索",
}

APP_NAME_MAP.update(
    {
        "com.tencent.mm": "微信",
        "com.ss.android.ugc.aweme": "抖音",
        "com.tencent.qqmusic": "QQ音乐",
        "com.dongqiudi.news": "懂球帝",
        "com.tencent.mobileqq": "QQ",
        "com.heytap.browser": "浏览器",
        "com.quark.browser": "夸克",
        "com.android.launcher": "系统桌面",
        "com.android.settings": "设置",
        "com.studypulse.android": "StudyPulse",
        "com.baidu.netdisk": "百度网盘",
        "tv.danmaku.bili": "哔哩哔哩",
        "com.taobao.taobao": "淘宝",
        "com.taobao.idlefish": "闲鱼",
        "com.xunmeng.pinduoduo": "拼多多",
        "com.jingdong.app.mall": "京东",
        "com.android.mms": "短信",
        "com.android.incallui": "电话",
        "com.coloros.gallery3d": "相册",
        "com.coloros.filemanager": "文件管理",
        "com.android.documentsui": "文件",
        "com.google.android.gms": "Google Play 服务",
        "com.google.android.googlequicksearchbox": "Google 搜索",
    }
)
APP_NAME_MAP["com.plan.kot32.tomatotime"] = "番茄 ToDo"

SYSTEM_PACKAGE_PREFIXES = (
    "android",
    "com.android.",
    "com.coloros.",
    "com.heytap.",
    "com.google.android.",
)


COMMAND_RULES = {
    "data_import": {"read.csv", "read_csv", "read_excel", "load", "readRDS"},
    "data_cleaning": {"filter", "mutate", "select", "arrange", "rename", "na.omit", "drop_na", "distinct"},
    "visualization": {"plot", "hist", "boxplot", "ggplot", "geom_point", "geom_smooth", "geom_line", "geom_bar"},
    "statistics": {"summary", "t.test", "chisq.test", "cor", "aov"},
    "modeling": {"lm", "glm", "predict", "kmeans"},
    "package": {"library", "require"},
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def calculate_distraction_risk(
    distracting_ratio: float,
    distracting_open_count: int,
    phone_total_minutes: float,
) -> tuple[float, float, float]:
    phone_hours = max(phone_total_minutes / 60, 1.0)
    distracting_open_rate = distracting_open_count / phone_hours
    switch_penalty = min(25.0, distracting_open_rate * 2)
    score = min(100.0, distracting_ratio * 100 + switch_penalty)
    return score, distracting_open_rate, switch_penalty


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    ensure_daily_metrics_columns(conn)
    ensure_weekly_metrics_columns(conn)
    conn.commit()


def ensure_daily_metrics_columns(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(daily_metrics)").fetchall()
    }
    additions = {
        "total_study_files_count": "INTEGER NOT NULL DEFAULT 0",
        "study_files_modified_7d_count": "INTEGER NOT NULL DEFAULT 0",
        "focus_minutes": "REAL NOT NULL DEFAULT 0",
        "focus_session_count": "INTEGER NOT NULL DEFAULT 0",
        "distracting_app_open_count": "INTEGER NOT NULL DEFAULT 0",
        "distracting_open_rate_per_hour": "REAL NOT NULL DEFAULT 0",
        "switch_penalty": "REAL NOT NULL DEFAULT 0",
    }
    for column, ddl in additions.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE daily_metrics ADD COLUMN {column} {ddl}")


def ensure_weekly_metrics_columns(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(weekly_metrics)").fetchall()
    }
    additions = {
        "data_days_count": "INTEGER NOT NULL DEFAULT 0",
        "is_partial_week": "INTEGER NOT NULL DEFAULT 1",
    }
    for column, ddl in additions.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE weekly_metrics ADD COLUMN {column} {ddl}")

    quality_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(data_quality_report)").fetchall()
    }
    if "collection_method" not in quality_columns:
        conn.execute("ALTER TABLE data_quality_report ADD COLUMN collection_method TEXT")


def reset_tables(conn: sqlite3.Connection) -> None:
    tables = [
        "ai_review",
        "monthly_metrics",
        "weekly_metrics",
        "data_quality_report",
        "daily_metrics",
        "r_history_summary",
        "focus_sessions",
        "windows_file_activity",
        "android_app_hourly_usage",
        "android_app_usage",
        "app_name_mapping",
        "app_category_rule",
        "import_log",
    ]
    for table in tables:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()


def create_import_log(conn: sqlite3.Connection, source: str, file_name: str | None) -> int:
    cur = conn.execute(
        """
        INSERT INTO import_log (source, file_name, started_at, status, message)
        VALUES (?, ?, ?, ?, ?)
        """,
        (source, file_name, now_text(), "partial", "started"),
    )
    conn.commit()
    return int(cur.lastrowid)


def finish_import_log(conn: sqlite3.Connection, import_id: int, status: str, message: str) -> None:
    conn.execute(
        """
        UPDATE import_log
        SET finished_at = ?, status = ?, message = ?
        WHERE id = ?
        """,
        (now_text(), status, message, import_id),
    )
    conn.commit()


def import_app_rules(conn: sqlite3.Connection) -> None:
    with RULES_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        conn.execute(
            """
            INSERT INTO app_category_rule (package_name, app_label, category, note)
            VALUES (?, ?, ?, ?)
            """,
            (row.get("package_name") or None, row["app_label"], row["category"], row.get("note", "")),
        )
    conn.commit()


def load_app_category_maps(conn: sqlite3.Connection) -> tuple[dict[str, str], dict[str, str]]:
    rows = conn.execute(
        """
        SELECT package_name, app_label, category
        FROM app_category_rule
        """
    ).fetchall()
    by_label = {
        str(row["app_label"]).strip().lower(): str(row["category"])
        for row in rows
        if row["app_label"]
    }
    by_package = {
        str(row["package_name"]).strip().lower(): str(row["category"])
        for row in rows
        if row["package_name"]
    }
    for row in rows:
        label = str(row["app_label"] or "").strip().lower()
        if "." in label and " " not in label:
            by_package[label] = str(row["category"])
    return by_label, by_package


def resolve_app_category(app: dict, label_map: dict[str, str], package_map: dict[str, str]) -> str:
    explicit = str(app.get("category") or "").strip()
    if explicit and explicit != "other":
        return explicit
    package_name = str(app.get("package_name") or "").strip().lower()
    if package_name in package_map:
        return package_map[package_name]
    label = str(app.get("app_label") or "").strip().lower()
    return label_map.get(label, "other")


def resolve_app_label(package_name: str, labels: list[str]) -> str:
    if package_name in APP_NAME_MAP:
        return APP_NAME_MAP[package_name]
    for label in labels:
        label = str(label or "").strip()
        if label and label != package_name:
            return label
    return package_name


def is_system_package(package_name: str) -> bool:
    lowered = package_name.lower()
    return any(lowered == prefix or lowered.startswith(prefix) for prefix in SYSTEM_PACKAGE_PREFIXES)


def is_unknown_app(package_name: str, app_label: str, category: str) -> bool:
    return category == "other" and (not app_label or app_label == package_name) and not is_system_package(package_name)


def is_suspicious_app_usage(package_name: str, minutes: float, open_count: int) -> bool:
    if is_system_package(package_name) and minutes >= 15:
        return True
    if open_count >= 300 and minutes < 5:
        return True
    return False


def aggregate_android_apps(raw_apps: list[dict], label_map: dict[str, str], package_map: dict[str, str]) -> tuple[list[dict], dict]:
    grouped: dict[str, dict] = {}
    labels_by_package: dict[str, list[str]] = {}

    for app in raw_apps:
        package_name = str(app.get("package_name") or "").strip()
        if not package_name:
            continue
        labels_by_package.setdefault(package_name, []).append(str(app.get("app_label") or "").strip())
        current = grouped.setdefault(
            package_name,
            {
                "package_name": package_name,
                "foreground_minutes": 0.0,
                "open_count": 0,
                "last_used_at": "",
                "raw_rows": 0,
                "categories": [],
            },
        )
        current["foreground_minutes"] += float(app.get("foreground_minutes", 0) or 0)
        current["open_count"] += int(app.get("open_count", 0) or 0)
        current["raw_rows"] += 1
        category = resolve_app_category(app, label_map, package_map)
        current["categories"].append(category)
        last_used_at = str(app.get("last_used_at") or "")
        if last_used_at > str(current["last_used_at"] or ""):
            current["last_used_at"] = last_used_at

    aggregated: list[dict] = []
    duplicate_package_count = 0
    unknown_app_count = 0
    system_app_count = 0
    suspicious_app_count = 0
    notes: list[dict] = []

    for package_name, item in grouped.items():
        if int(item["raw_rows"]) > 1:
            duplicate_package_count += 1
            notes.append({
                "type": "duplicate_package_aggregated",
                "package_name": package_name,
                "raw_rows": item["raw_rows"],
            })

        category_counts = Counter(item["categories"])
        category = category_counts.most_common(1)[0][0] if category_counts else "other"
        display_name = resolve_app_label(package_name, labels_by_package.get(package_name, []))
        minutes = float(item["foreground_minutes"])
        open_count = int(item["open_count"])

        if is_unknown_app(package_name, display_name, category):
            unknown_app_count += 1
            notes.append({"type": "unknown_app_needs_confirmation", "package_name": package_name})
        if is_system_package(package_name):
            system_app_count += 1
        if is_suspicious_app_usage(package_name, minutes, open_count):
            suspicious_app_count += 1
            notes.append({
                "type": "suspicious_usage_signal",
                "package_name": package_name,
                "minutes": round(minutes, 2),
                "open_count": open_count,
            })

        aggregated.append({
            "package_name": package_name,
            "app_label": display_name,
            "category": category,
            "foreground_minutes": minutes,
            "open_count": open_count,
            "last_used_at": item["last_used_at"],
            "raw_rows": item["raw_rows"],
        })

    aggregated.sort(key=lambda app: float(app["foreground_minutes"]), reverse=True)
    quality = {
        "raw_app_rows": len(raw_apps),
        "aggregated_app_rows": len(aggregated),
        "duplicate_package_count": duplicate_package_count,
        "unknown_app_count": unknown_app_count,
        "system_app_count": system_app_count,
        "suspicious_app_count": suspicious_app_count,
        "notes": notes[:60],
    }
    return aggregated, quality


def aggregate_hourly_usage(
    raw_hourly: list[dict],
    app_by_package: dict[str, dict],
    label_map: dict[str, str],
    package_map: dict[str, str],
) -> list[dict]:
    grouped: dict[tuple[str, int], float] = {}
    for item in raw_hourly:
        package_name = str(item.get("package_name") or "").strip()
        if not package_name:
            continue
        try:
            hour = int(item.get("hour"))
        except (TypeError, ValueError):
            continue
        if hour < 0 or hour > 23:
            continue
        key = (package_name, hour)
        grouped[key] = grouped.get(key, 0.0) + float(item.get("foreground_minutes", 0) or 0)

    rows: list[dict] = []
    for (package_name, hour), minutes in sorted(grouped.items()):
        app = app_by_package.get(package_name, {"package_name": package_name, "app_label": package_name, "category": "other"})
        if app["category"] == "other":
            category = resolve_app_category(app, label_map, package_map)
        else:
            category = app["category"]
        rows.append({
            "package_name": package_name,
            "app_label": app.get("app_label") or package_name,
            "category": category,
            "hour": hour,
            "foreground_minutes": minutes,
        })
    return rows


def get_android_json_path() -> Path:
    if os.environ.get("STUDYPULSE_SAMPLE") == "1":
        return ANDROID_JSON_PATH
    if ANDROID_EXPORT_DIR.exists():
        candidates = sorted(
            ANDROID_EXPORT_DIR.glob("android_usage*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return candidates[0]
    return ANDROID_JSON_PATH


def get_android_json_paths() -> list[Path]:
    if os.environ.get("STUDYPULSE_SAMPLE") == "1":
        return [ANDROID_JSON_PATH]
    if ANDROID_EXPORT_DIR.exists():
        candidates = sorted(
            ANDROID_EXPORT_DIR.glob("android_usage*.json"),
            key=lambda path: path.name,
        )
        if candidates:
            return candidates
    return [ANDROID_JSON_PATH]


def get_windows_file_csv_path() -> Path:
    if os.environ.get("STUDYPULSE_SAMPLE") == "1":
        return WINDOWS_FILE_CSV_PATH
    if WINDOWS_SCAN_DIR.exists():
        candidates = sorted(
            WINDOWS_SCAN_DIR.glob("windows_file_activity_*.csv"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return candidates[0]
    return WINDOWS_FILE_CSV_PATH


def import_android_json(conn: sqlite3.Connection, android_json_path: Path | None = None) -> str:
    android_json_path = android_json_path or get_android_json_path()
    import_id = create_import_log(conn, "android_json", android_json_path.name)
    try:
        label_map, package_map = load_app_category_maps(conn)
        data = json.loads(android_json_path.read_text(encoding="utf-8"))
        apps, quality = aggregate_android_apps(data["apps"], label_map, package_map)
        app_by_package = {app["package_name"]: app for app in apps}
        hourly_rows = aggregate_hourly_usage(data.get("hourly_usage", []), app_by_package, label_map, package_map)
        for app in apps:
            conn.execute(
                """
                INSERT INTO android_app_usage (
                    date, package_name, app_label, category, foreground_minutes,
                    open_count, last_used_at, import_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["date"],
                    app["package_name"],
                    app.get("app_label"),
                    app["category"],
                    float(app.get("foreground_minutes", 0)),
                    int(app.get("open_count", 0)),
                    app.get("last_used_at"),
                    import_id,
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO app_name_mapping (package_name, display_name, source, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    app["package_name"],
                    app.get("app_label") or app["package_name"],
                    "builtin" if app["package_name"] in APP_NAME_MAP else "android_label",
                    now_text(),
                ),
            )
        for item in hourly_rows:
            conn.execute(
                """
                INSERT INTO android_app_hourly_usage (
                    date, package_name, app_label, category, hour,
                    foreground_minutes, import_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["date"],
                    item["package_name"],
                    item.get("app_label"),
                    item["category"],
                    int(item["hour"]),
                    float(item.get("foreground_minutes", 0)),
                    import_id,
                ),
            )
        conn.execute(
            """
            INSERT OR REPLACE INTO data_quality_report (
                date, android_source_file, android_generated_at, collection_method, raw_app_rows,
                aggregated_app_rows, duplicate_package_count, unknown_app_count,
                system_app_count, suspicious_app_count, notes_json, generated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["date"],
                str(android_json_path),
                data.get("generated_at"),
                data.get("collection_method", "usage_stats_total_time"),
                quality["raw_app_rows"],
                quality["aggregated_app_rows"],
                quality["duplicate_package_count"],
                quality["unknown_app_count"],
                quality["system_app_count"],
                quality["suspicious_app_count"],
                json.dumps(quality["notes"], ensure_ascii=False),
                now_text(),
            ),
        )
        conn.commit()
        finish_import_log(
            conn,
            import_id,
            "success",
            f"imported {len(apps)} aggregated apps and {len(hourly_rows)} hourly rows from {len(data['apps'])} raw rows",
        )
        return str(data["date"])
    except Exception as exc:
        finish_import_log(conn, import_id, "failed", str(exc))
        raise


def import_windows_file_activity(conn: sqlite3.Connection) -> None:
    windows_file_csv_path = get_windows_file_csv_path()
    import_id = create_import_log(conn, "windows_scan", windows_file_csv_path.name)
    try:
        with windows_file_csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            conn.execute(
                """
                INSERT INTO windows_file_activity (
                    date, root_alias, relative_path, path_hash, extension,
                    file_size_bytes, last_modified_at, activity_type, import_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["date"],
                    row["root_alias"],
                    row["relative_path"],
                    row.get("path_hash") or sha256_text(row["relative_path"]),
                    row["extension"],
                    int(row["file_size_bytes"]),
                    row["last_modified_at"],
                    row.get("activity_type", "unknown"),
                    import_id,
                ),
            )
        conn.commit()
        finish_import_log(conn, import_id, "success", f"imported {len(rows)} file activities")
    except Exception as exc:
        finish_import_log(conn, import_id, "failed", str(exc))
        raise


def normalize_focus_session(date: str, source: str, item: dict) -> dict:
    title = str(item.get("title") or item.get("task") or item.get("name") or "未命名专注").strip()
    minutes = item.get("minutes", item.get("duration_minutes", 0))
    try:
        minutes_value = float(minutes)
    except (TypeError, ValueError):
        minutes_value = 0.0
    return {
        "date": str(item.get("date") or date),
        "source": str(item.get("source") or source or "manual"),
        "title": title,
        "start_time": str(item.get("start") or item.get("start_time") or ""),
        "end_time": str(item.get("end") or item.get("end_time") or ""),
        "minutes": max(0.0, minutes_value),
        "raw_json": json.dumps(item, ensure_ascii=False, sort_keys=True),
    }


def get_focus_export_paths() -> list[Path]:
    config = load_config()
    folder = focus_export_dir(config)
    if not folder.exists():
        return []
    patterns = ("focus_*.json", "tomato_*.json", "pomodoro_*.json")
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(folder.glob(pattern))
    return sorted(set(paths), key=lambda path: (path.stat().st_mtime, path.name))


def import_focus_sessions(conn: sqlite3.Connection) -> list[str]:
    imported_dates: set[str] = set()
    for path in get_focus_export_paths():
        import_id = create_import_log(conn, "focus_sessions", path.name)
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            date_value = str(data.get("date") or "")
            source = str(data.get("source") or "manual")
            sessions = data.get("sessions", [])
            if not date_value:
                raise ValueError("focus export requires top-level date")
            if not isinstance(sessions, list):
                raise ValueError("focus export requires sessions list")
            rows = [normalize_focus_session(date_value, source, item) for item in sessions if isinstance(item, dict)]
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO focus_sessions (
                        date, source, title, start_time, end_time, minutes, raw_json, import_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["date"],
                        row["source"],
                        row["title"],
                        row["start_time"],
                        row["end_time"],
                        row["minutes"],
                        row["raw_json"],
                        import_id,
                    ),
                )
                imported_dates.add(row["date"])
            conn.commit()
            finish_import_log(conn, import_id, "success", f"imported {len(rows)} focus sessions")
        except Exception as exc:
            finish_import_log(conn, import_id, "failed", str(exc))
            raise
    return sorted(imported_dates)


def split_focus_session_by_hour(date_value: str, start_time: str, end_time: str, minutes: float) -> list[tuple[int, float]]:
    if minutes <= 0:
        return []
    try:
        start = datetime.strptime(f"{date_value} {start_time}", "%Y-%m-%d %H:%M")
        end = datetime.strptime(f"{date_value} {end_time}", "%Y-%m-%d %H:%M") if end_time else start + timedelta(minutes=minutes)
        if end <= start:
            end = start + timedelta(minutes=minutes)
    except ValueError:
        hour = int(start_time.split(":", 1)[0]) if ":" in start_time and start_time.split(":", 1)[0].isdigit() else 0
        return [(max(0, min(23, hour)), minutes)]

    rows: list[tuple[int, float]] = []
    cursor = start
    while cursor < end:
        hour_end = cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        segment_end = min(hour_end, end)
        rows.append((cursor.hour, (segment_end - cursor).total_seconds() / 60))
        cursor = segment_end
    return rows


def apply_focus_sessions_to_tomato_app(conn: sqlite3.Connection) -> None:
    """Use Tomato ToDo focus sessions as the corrected normal app usage signal."""
    dates = [
        row["date"]
        for row in conn.execute("SELECT DISTINCT date FROM focus_sessions ORDER BY date").fetchall()
    ]
    for date_value in dates:
        sessions = [
            dict(row)
            for row in conn.execute(
                """
                SELECT title, start_time, end_time, minutes
                FROM focus_sessions
                WHERE date = ?
                ORDER BY COALESCE(start_time, ''), id
                """,
                (date_value,),
            ).fetchall()
        ]
        focus_minutes = sum(float(row["minutes"] or 0) for row in sessions)
        if focus_minutes <= 0:
            continue
        focus_count = len(sessions)
        last_time = max(
            [str(row.get("end_time") or row.get("start_time") or "") for row in sessions if row.get("end_time") or row.get("start_time")],
            default="",
        )
        last_used_at = f"{date_value} {last_time}:00" if last_time else date_value

        existing = conn.execute(
            """
            SELECT id
            FROM android_app_usage
            WHERE date = ? AND package_name = ?
            ORDER BY id
            LIMIT 1
            """,
            (date_value, TOMATO_TODO_PACKAGE),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE android_app_usage
                SET app_label = ?, category = ?, foreground_minutes = ?, open_count = ?, last_used_at = ?
                WHERE id = ?
                """,
                ("番茄 ToDo", "study", focus_minutes, focus_count, last_used_at, existing["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO android_app_usage (
                    date, package_name, app_label, category, foreground_minutes, open_count, last_used_at, import_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (date_value, TOMATO_TODO_PACKAGE, "番茄 ToDo", "study", focus_minutes, focus_count, last_used_at),
            )

        conn.execute(
            "DELETE FROM android_app_hourly_usage WHERE date = ? AND package_name = ?",
            (date_value, TOMATO_TODO_PACKAGE),
        )
        hourly: dict[int, float] = {}
        for session in sessions:
            for hour, value in split_focus_session_by_hour(
                date_value,
                str(session.get("start_time") or ""),
                str(session.get("end_time") or ""),
                float(session.get("minutes") or 0),
            ):
                hourly[hour] = hourly.get(hour, 0.0) + value
        for hour, minutes in sorted(hourly.items()):
            conn.execute(
                """
                INSERT INTO android_app_hourly_usage (
                    date, package_name, app_label, category, hour, foreground_minutes, import_id
                )
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (date_value, TOMATO_TODO_PACKAGE, "番茄 ToDo", "study", hour, minutes),
            )
    conn.commit()


def get_windows_activity_dates(conn: sqlite3.Connection) -> list[str]:
    return [
        row["date"]
        for row in conn.execute(
            """
            SELECT DISTINCT date
            FROM windows_file_activity
            ORDER BY date
            """
        ).fetchall()
    ]


def classify_r_command(line: str) -> tuple[str, list[str]]:
    functions = R_FUNCTION_RE.findall(line)
    for category, names in COMMAND_RULES.items():
        if any(fn in names or fn.startswith("geom_") and category == "visualization" for fn in functions):
            return category, functions
    return "other", functions


def extract_r_lines_from_file(path: Path) -> list[str]:
    try:
        raw_lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []

    suffix = path.suffix.lower()
    if suffix == ".r":
        return [
            line.strip()
            for line in raw_lines
            if line.strip() and not line.strip().startswith("#")
        ]

    lines: list[str] = []
    in_r_chunk = False
    for raw_line in raw_lines:
        stripped = raw_line.strip()
        lower = stripped.lower()
        if lower.startswith("```"):
            if in_r_chunk:
                in_r_chunk = False
            else:
                fence_info = lower[3:].strip()
                in_r_chunk = fence_info.startswith("{r") or fence_info == "r" or fence_info.startswith("r ")
            continue
        if in_r_chunk and stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


def collect_real_r_code_lines() -> tuple[list[str], list[Path]]:
    if os.environ.get("STUDYPULSE_SAMPLE") == "1":
        return [], []
    config = load_config()
    extensions = {".r", ".md", ".rmd", ".qmd"}
    lines: list[str] = []
    files: list[Path] = []
    for root in config.get("study_roots", []):
        root_path = expand_config_path(root["path"])
        if not root_path.exists():
            continue
        for path in root_path.rglob("*"):
            if path.is_file() and path.suffix.lower() in extensions:
                file_lines = extract_r_lines_from_file(path)
                if file_lines:
                    files.append(path)
                    lines.extend(file_lines)
    return lines, files


def insert_r_summary(conn: sqlite3.Connection, date: str, source_key: str, import_id: int, lines: list[str]) -> None:
    package_names: list[str] = []
    function_names: list[str] = []
    category_counts = Counter()

    for line in lines:
        package_names.extend(R_LIBRARY_RE.findall(line))
        category, functions = classify_r_command(line)
        function_names.extend(functions)
        category_counts[category] += 1

    top_packages = [
        {"name": name, "count": count}
        for name, count in Counter(package_names).most_common(8)
    ]
    top_functions = [
        {"name": name, "count": count}
        for name, count in Counter(function_names).most_common(12)
    ]

    conn.execute(
        """
        INSERT INTO r_history_summary (
            date, history_file_hash, command_count, package_count,
            data_import_count, data_cleaning_count, visualization_count,
            statistics_count, modeling_count, other_count,
            top_packages_json, top_functions_json, import_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            date,
            sha256_text(source_key),
            len(lines),
            len(set(package_names)),
            category_counts["data_import"],
            category_counts["data_cleaning"],
            category_counts["visualization"],
            category_counts["statistics"],
            category_counts["modeling"],
            category_counts["other"],
            json.dumps(top_packages, ensure_ascii=False),
            json.dumps(top_functions, ensure_ascii=False),
            import_id,
        ),
    )


def parse_r_sources(conn: sqlite3.Connection, date: str) -> None:
    real_lines, real_files = collect_real_r_code_lines()
    if real_lines:
        import_id = create_import_log(conn, "r_code_scan", "study_roots")
        try:
            source_key = "|".join(str(path) for path in real_files)
            insert_r_summary(conn, date, source_key, import_id, real_lines)
            conn.commit()
            finish_import_log(conn, import_id, "success", f"parsed {len(real_lines)} R commands from {len(real_files)} files")
        except Exception as exc:
            finish_import_log(conn, import_id, "failed", str(exc))
            raise
        return

    import_id = create_import_log(conn, "r_history", R_HISTORY_PATH.name)
    try:
        lines = [
            line.strip()
            for line in R_HISTORY_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        insert_r_summary(conn, date, str(R_HISTORY_PATH), import_id, lines)
        conn.commit()
        finish_import_log(conn, import_id, "success", f"parsed {len(lines)} R commands from fallback Rhistory")
    except Exception as exc:
        finish_import_log(conn, import_id, "failed", str(exc))
        raise


def generate_daily_metrics(conn: sqlite3.Connection, date: str) -> None:
    app_rows = conn.execute(
        """
        SELECT category, SUM(foreground_minutes) AS minutes, SUM(open_count) AS opens
        FROM android_app_usage
        WHERE date = ?
        GROUP BY category
        """,
        (date,),
    ).fetchall()
    by_category = {row["category"]: float(row["minutes"] or 0) for row in app_rows}
    opens_by_category = {row["category"]: int(row["opens"] or 0) for row in app_rows}
    app_open_count = sum(int(row["opens"] or 0) for row in app_rows)
    phone_total = sum(by_category.values())
    study = by_category.get("study", 0.0)
    tool = by_category.get("tool", 0.0)
    social = by_category.get("social", 0.0)
    entertainment = by_category.get("entertainment", 0.0)
    game = by_category.get("game", 0.0)
    distracting = social + entertainment + game
    distracting_ratio = distracting / phone_total if phone_total else 0.0
    distracting_app_open_count = sum(opens_by_category.get(category, 0) for category in DISTRACTING_CATEGORIES)

    recent_start = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=6)).strftime("%Y-%m-%d")
    total_file_count = int(conn.execute("SELECT COUNT(*) FROM windows_file_activity").fetchone()[0] or 0)
    recent_file_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM windows_file_activity
            WHERE date BETWEEN ? AND ?
            """,
            (recent_start, date),
        ).fetchone()[0]
        or 0
    )

    file_counts = conn.execute(
        """
        SELECT
            SUM(CASE WHEN activity_type = 'modified' THEN 1 ELSE 0 END) AS modified_count,
            SUM(CASE WHEN activity_type = 'created' THEN 1 ELSE 0 END) AS created_count
        FROM windows_file_activity
        WHERE date = ?
        """,
        (date,),
    ).fetchone()
    modified_count = int(file_counts["modified_count"] or 0)
    created_count = int(file_counts["created_count"] or 0)

    r_summary = conn.execute(
        """
        SELECT *
        FROM r_history_summary
        WHERE date = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (date,),
    ).fetchone()
    r_command_count = int(r_summary["command_count"] if r_summary else 0)
    r_visualization_count = int(r_summary["visualization_count"] if r_summary else 0)
    r_modeling_count = int(r_summary["modeling_count"] if r_summary else 0)
    focus_row = conn.execute(
        """
        SELECT SUM(minutes) AS focus_minutes, COUNT(*) AS focus_session_count
        FROM focus_sessions
        WHERE date = ?
        """,
        (date,),
    ).fetchone()
    focus_minutes = float(focus_row["focus_minutes"] or 0)
    focus_session_count = int(focus_row["focus_session_count"] or 0)

    learning_output_score = min(
        100.0,
        modified_count * 12
        + created_count * 18
        + recent_file_count * 3
        + min(total_file_count, 30) * 0.5
        + r_command_count * 0.6,
    )
    learning_input_score = min(
        100.0,
        study * 0.22
        + tool * 0.08
        + r_command_count * 0.25
        + learning_output_score * 0.25,
    )
    distraction_risk_score, distracting_open_rate, switch_penalty = calculate_distraction_risk(
        distracting_ratio,
        distracting_app_open_count,
        phone_total,
    )
    r_activity_score = min(100.0, r_command_count * 1.2 + r_visualization_count * 2 + r_modeling_count * 3)

    conn.execute(
        """
        INSERT OR REPLACE INTO daily_metrics (
            date, phone_total_minutes, study_app_minutes, focus_minutes, focus_session_count, tool_app_minutes,
            social_app_minutes, entertainment_app_minutes, game_app_minutes,
            distracting_app_minutes, distracting_ratio, app_open_count,
            distracting_app_open_count, distracting_open_rate_per_hour, switch_penalty,
            total_study_files_count, study_files_modified_7d_count,
            study_files_modified_count, study_files_created_count,
            r_command_count, r_visualization_count, r_modeling_count,
            learning_input_score, learning_output_score, distraction_risk_score,
            r_activity_score, generated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            date,
            phone_total,
            study,
            focus_minutes,
            focus_session_count,
            tool,
            social,
            entertainment,
            game,
            distracting,
            distracting_ratio,
            app_open_count,
            distracting_app_open_count,
            distracting_open_rate,
            switch_penalty,
            total_file_count,
            recent_file_count,
            modified_count,
            created_count,
            r_command_count,
            r_visualization_count,
            r_modeling_count,
            learning_input_score,
            learning_output_score,
            distraction_risk_score,
            r_activity_score,
            now_text(),
        ),
    )
    conn.commit()


def import_sample_daily_history(conn: sqlite3.Connection) -> None:
    """Seed nearby dates so weekly report has a trend. Current date is overwritten later."""
    with DAILY_SAMPLE_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        phone_total = float(row["phone_total_minutes"])
        distracting_ratio = float(row["distracting_ratio"])
        app_open_count = int(float(row["app_open_count"]))
        distracting_app_open_count = round(app_open_count * distracting_ratio)
        distraction_risk_score, distracting_open_rate, switch_penalty = calculate_distraction_risk(
            distracting_ratio,
            distracting_app_open_count,
            phone_total,
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO daily_metrics (
                date, phone_total_minutes, study_app_minutes, tool_app_minutes,
                social_app_minutes, entertainment_app_minutes, game_app_minutes,
                distracting_app_minutes, distracting_ratio, app_open_count,
                distracting_app_open_count, distracting_open_rate_per_hour, switch_penalty,
                total_study_files_count, study_files_modified_7d_count,
                study_files_modified_count, study_files_created_count,
                r_command_count, r_visualization_count, r_modeling_count,
                learning_input_score, learning_output_score, distraction_risk_score,
                r_activity_score, generated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["date"],
                phone_total,
                float(row["study_app_minutes"]),
                float(row["tool_app_minutes"]),
                float(row["social_app_minutes"]),
                float(row["entertainment_app_minutes"]),
                float(row["game_app_minutes"]),
                float(row["distracting_app_minutes"]),
                distracting_ratio,
                app_open_count,
                distracting_app_open_count,
                distracting_open_rate,
                switch_penalty,
                int(float(row["study_files_modified_count"])) + int(float(row["study_files_created_count"])),
                int(float(row["study_files_modified_count"])),
                int(float(row["study_files_modified_count"])),
                int(float(row["study_files_created_count"])),
                int(float(row["r_command_count"])),
                int(float(row["r_visualization_count"])),
                int(float(row["r_modeling_count"])),
                float(row["learning_input_score"]),
                float(row["learning_output_score"]),
                distraction_risk_score,
                float(row["r_activity_score"]),
                row["generated_at"],
            ),
        )
    conn.commit()


def generate_weekly_metrics(conn: sqlite3.Connection, end_date: str) -> None:
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    start = end - timedelta(days=6)
    rows = conn.execute(
        """
        SELECT *
        FROM daily_metrics
        WHERE date BETWEEN ? AND ?
        ORDER BY date
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    if not rows:
        return

    def avg(key: str) -> float:
        return sum(float(row[key] or 0) for row in rows) / len(rows)

    def total(key: str) -> float:
        return sum(float(row[key] or 0) for row in rows)

    best_day = max(rows, key=lambda row: float(row["learning_output_score"] or 0))["date"]
    risk_day = max(rows, key=lambda row: float(row["distraction_risk_score"] or 0))["date"]

    conn.execute(
        """
        INSERT OR REPLACE INTO weekly_metrics (
            week_start, week_end, avg_learning_input_score,
            avg_learning_output_score, avg_distraction_risk_score,
            total_study_app_minutes, total_distracting_app_minutes,
            total_study_files_modified, total_r_commands,
            data_days_count, is_partial_week, best_day, risk_day, generated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            start.isoformat(),
            end.isoformat(),
            avg("learning_input_score"),
            avg("learning_output_score"),
            avg("distraction_risk_score"),
            total("study_app_minutes"),
            total("distracting_app_minutes"),
            int(total("study_files_modified_count")),
            int(total("r_command_count")),
            len(rows),
            1 if len(rows) < 7 else 0,
            best_day,
            risk_day,
            now_text(),
        ),
    )
    conn.commit()


def generate_monthly_metrics(conn: sqlite3.Connection, end_date: str) -> None:
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    start = end.replace(day=1)
    rows = conn.execute(
        """
        SELECT *
        FROM daily_metrics
        WHERE date BETWEEN ? AND ?
        ORDER BY date
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    if not rows:
        return

    def avg(key: str) -> float:
        return sum(float(row[key] or 0) for row in rows) / len(rows)

    def total(key: str) -> float:
        return sum(float(row[key] or 0) for row in rows)

    best_day = max(rows, key=lambda row: float(row["learning_output_score"] or 0))["date"]
    risk_day = max(rows, key=lambda row: float(row["distraction_risk_score"] or 0))["date"]

    conn.execute(
        """
        INSERT OR REPLACE INTO monthly_metrics (
            month_start, month_end, avg_learning_input_score,
            avg_learning_output_score, avg_distraction_risk_score,
            total_study_app_minutes, total_distracting_app_minutes,
            total_study_files_modified, total_r_commands,
            data_days_count, is_partial_month, best_day, risk_day, generated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            start.isoformat(),
            end.isoformat(),
            avg("learning_input_score"),
            avg("learning_output_score"),
            avg("distraction_risk_score"),
            total("study_app_minutes"),
            total("distracting_app_minutes"),
            int(total("study_files_modified_count")),
            int(total("r_command_count")),
            len(rows),
            1,
            best_day,
            risk_day,
            now_text(),
        ),
    )
    conn.commit()


def seed_ai_review(conn: sqlite3.Connection, date: str) -> None:
    row = conn.execute("SELECT * FROM daily_metrics WHERE date = ?", (date,)).fetchone()
    if not row:
        return
    prompt_payload = {
        "date": row["date"],
        "phone_total_minutes": row["phone_total_minutes"],
        "study_app_minutes": row["study_app_minutes"],
        "focus_minutes": row["focus_minutes"],
        "focus_session_count": row["focus_session_count"],
        "distracting_app_minutes": row["distracting_app_minutes"],
        "distracting_ratio": row["distracting_ratio"],
        "study_files_modified_count": row["study_files_modified_count"],
        "r_command_count": row["r_command_count"],
        "learning_input_score": row["learning_input_score"],
        "learning_output_score": row["learning_output_score"],
        "distraction_risk_score": row["distraction_risk_score"],
    }
    review_text = (
        "这是基于规则生成的占位复盘。今天的行为数据可用于判断学习投入和分心风险的趋势，"
        "后续接入小米 MiMo 后将由模型基于同一份聚合指标生成自然语言建议。"
    )
    conn.execute(
        """
        INSERT INTO ai_review (scope, target_date, prompt, review_text, model_name, generated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "daily",
            date,
            json.dumps(prompt_payload, ensure_ascii=False, indent=2),
            review_text,
            "rule-placeholder",
            now_text(),
        ),
    )
    conn.commit()


def main() -> None:
    conn = connect()
    init_schema(conn)
    reset_tables(conn)
    import_app_rules(conn)
    imported_dates = [import_android_json(conn, path) for path in get_android_json_paths()]
    import_windows_file_activity(conn)
    focus_dates = import_focus_sessions(conn)
    apply_focus_sessions_to_tomato_app(conn)
    signal_dates = sorted(set(imported_dates + focus_dates + get_windows_activity_dates(conn)))
    if not signal_dates:
        raise RuntimeError("No Android, focus, or Windows activity dates were imported")
    target_date = signal_dates[-1]
    parse_r_sources(conn, target_date)
    import_sample_daily_history(conn)
    generate_daily_metrics(conn, target_date)
    generate_weekly_metrics(conn, target_date)
    generate_monthly_metrics(conn, target_date)
    seed_ai_review(conn, target_date)

    counts = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in [
            "app_category_rule",
            "android_app_usage",
            "windows_file_activity",
            "focus_sessions",
            "r_history_summary",
            "daily_metrics",
            "weekly_metrics",
            "monthly_metrics",
            "ai_review",
        ]
    }
    conn.close()
    print(f"Database written to: {DB_PATH}")
    for table, count in counts.items():
        print(f"{table}: {count}")


if __name__ == "__main__":
    main()
