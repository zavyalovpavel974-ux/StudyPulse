from __future__ import annotations

import os
import smtplib
import sqlite3
import sys
from datetime import date
from email.message import EmailMessage
from html import escape
from pathlib import Path

from studypulse_config import configured_email_recipients, load_config


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "studypulse.db"
REPORT_PATH = PROJECT_ROOT / "reports" / "studypulse_ui_interactive.html"


def read_windows_user_env(name: str) -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value).strip()
    except OSError:
        return ""


def env(name: str, default: str = "", prefer_user: bool = False) -> str:
    process_value = os.environ.get(name, "").strip()
    user_value = read_windows_user_env(name)
    if prefer_user and user_value:
        return user_value
    return process_value or user_value or default


def parse_recipients(value: str) -> list[str]:
    normalized = value.replace(";", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def merge_recipients(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            key = item.lower()
            if key not in seen:
                merged.append(item)
                seen.add(key)
    return merged


def read_latest_ai_review() -> tuple[str, str]:
    if not DB_PATH.exists():
        return date.today().isoformat(), "StudyPulse report has been generated."

    with sqlite3.connect(DB_PATH) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(ai_review)").fetchall()}
        date_column = "target_date" if "target_date" in columns else "date"
        order_column = "generated_at" if "generated_at" in columns else date_column
        row = conn.execute(
            f"""
            SELECT {date_column}, review_text
            FROM ai_review
            ORDER BY {order_column} DESC
            LIMIT 1
            """
        ).fetchone()

    if not row:
        return date.today().isoformat(), "StudyPulse report has been generated."
    review_date, review_text = row
    return str(review_date), str(review_text or "StudyPulse report has been generated.")


def format_minutes(value) -> str:
    minutes = round(float(value or 0))
    hours, rest = divmod(minutes, 60)
    return f"{hours}h {rest}m" if hours else f"{rest}m"


def format_percent(value) -> str:
    return f"{float(value or 0) * 100:.1f}%"


def read_mobile_summary() -> dict:
    if not DB_PATH.exists():
        return {}

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        latest = conn.execute(
            """
            SELECT *
            FROM daily_metrics
            ORDER BY date DESC
            LIMIT 1
            """
        ).fetchone()
        if not latest:
            return {}
        latest_date = latest["date"]
        apps = [
            dict(row)
            for row in conn.execute(
                """
                SELECT app_label, package_name, category, foreground_minutes, open_count
                FROM android_app_usage
                WHERE date = ?
                ORDER BY foreground_minutes DESC
                LIMIT 5
                """,
                (latest_date,),
            )
        ]
        quality = conn.execute("SELECT * FROM data_quality_report WHERE date = ? LIMIT 1", (latest_date,)).fetchone()
        weekly = conn.execute("SELECT * FROM weekly_metrics WHERE week_end = ? ORDER BY generated_at DESC LIMIT 1", (latest_date,)).fetchone()
        monthly = conn.execute("SELECT * FROM monthly_metrics WHERE month_end = ? ORDER BY generated_at DESC LIMIT 1", (latest_date,)).fetchone()

    return {
        "latest": dict(latest),
        "apps": apps,
        "quality": dict(quality) if quality else {},
        "weekly": dict(weekly) if weekly else {},
        "monthly": dict(monthly) if monthly else {},
    }


def build_mobile_summary_text(summary: dict, review_text: str) -> str:
    if not summary:
        return review_text

    latest = summary["latest"]
    apps = summary["apps"]
    quality = summary["quality"]
    weekly = summary["weekly"]
    monthly = summary["monthly"]
    app_lines = [
        f"- {app.get('app_label') or app.get('package_name')}: {format_minutes(app.get('foreground_minutes'))}, 打开 {app.get('open_count') or 0} 次"
        for app in apps[:3]
    ] or ["- 暂无 App 使用数据"]

    weekly_days = int(weekly.get("data_days_count") or 0) if weekly else 0
    monthly_days = int(monthly.get("data_days_count") or 0) if monthly else 0

    return (
        f"StudyPulse 手机摘要 - {latest['date']}\n\n"
        "核心指标\n"
        f"- 手机总使用：{format_minutes(latest.get('phone_total_minutes'))}\n"
        f"- 学习 App：{format_minutes(latest.get('study_app_minutes'))}\n"
        f"- 分心 App：{format_minutes(latest.get('distracting_app_minutes'))}\n"
        f"- 分心占比：{format_percent(latest.get('distracting_ratio'))}\n"
        f"- 学习文件总量：{latest.get('total_study_files_count')}\n"
        f"- 最近 7 天文件修改记录：{latest.get('study_files_modified_7d_count')}\n"
        f"- R 命令数：{latest.get('r_command_count')}\n\n"
        "Top App\n"
        + "\n".join(app_lines)
        + "\n\n"
        "数据可信度\n"
        f"- Android 原始 App 行数：{quality.get('raw_app_rows', '未知')}\n"
        f"- 聚合后 App 数：{quality.get('aggregated_app_rows', '未知')}\n"
        f"- 已聚合重复包名：{quality.get('duplicate_package_count', 0)}\n"
        f"- 待确认未知 App：{quality.get('unknown_app_count', 0)}\n"
        f"- 可疑异常信号：{quality.get('suspicious_app_count', 0)}\n\n"
        "趋势雏形\n"
        f"- 周趋势样本天数：{weekly_days}；{'样本不足 7 天，当前为早期趋势' if weekly_days < 7 else '已具备 7 天窗口'}\n"
        f"- 月趋势样本天数：{monthly_days}；当前先做滚动积累\n\n"
        "AI 复盘\n"
        f"{review_text}\n"
    )


def build_mobile_summary_html(summary: dict, review_text: str) -> str:
    text = build_mobile_summary_text(summary, review_text)
    return (
        "<!doctype html><html><body>"
        "<div style=\"font-family:Arial,'Microsoft YaHei',sans-serif;line-height:1.65;color:#111827;\">"
        "<pre style=\"white-space:pre-wrap;font-family:inherit;\">"
        f"{escape(text)}"
        "</pre>"
        "</div></body></html>"
    )


def build_message(sender: str, recipients: list[str], subject: str, body: str, html_body: str, report_path: Path) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)
    message.add_alternative(html_body, subtype="html")
    html = report_path.read_bytes()
    message.add_attachment(html, maintype="text", subtype="html", filename=report_path.name)
    return message


def main() -> None:
    config = load_config()
    email_config = config.get("email", {})
    smtp_host = env("STUDYPULSE_SMTP_HOST", prefer_user=True)
    smtp_port = int(env("STUDYPULSE_SMTP_PORT", "465", prefer_user=True))
    smtp_user = env("STUDYPULSE_SMTP_USER", prefer_user=True)
    smtp_password = env("STUDYPULSE_SMTP_PASSWORD", prefer_user=True)
    recipients_env = str(email_config.get("recipients_env") or "STUDYPULSE_NOTIFY_EMAIL_TO")
    sender_env = str(email_config.get("sender_env") or "STUDYPULSE_NOTIFY_EMAIL_FROM")
    recipients_raw = env(recipients_env, prefer_user=True)
    recipients = merge_recipients(parse_recipients(recipients_raw), configured_email_recipients(config))
    sender = env(sender_env, smtp_user, prefer_user=True)
    use_ssl = env("STUDYPULSE_SMTP_SSL", "1", prefer_user=True).lower() not in {"0", "false", "no"}

    if smtp_host.lower() == "smtp.gmail.com":
        smtp_password = smtp_password.replace(" ", "")

    missing = [
        name
        for name, value in [
            ("STUDYPULSE_SMTP_HOST", smtp_host),
            ("STUDYPULSE_SMTP_USER", smtp_user),
            ("STUDYPULSE_SMTP_PASSWORD", smtp_password),
            (f"{sender_env} or STUDYPULSE_SMTP_USER", sender),
        ]
        if not value
    ]
    if not recipients:
        missing.append("valid recipients")

    if "--dry-run" in sys.argv:
        print("Email notification dry run.")
        print(f"SMTP host: {smtp_host or '(missing)'}")
        print(f"SMTP user: {smtp_user or '(missing)'}")
        print(f"From: {sender or '(missing)'}")
        print(f"Recipients: {', '.join(recipients) if recipients else '(missing)'}")
        print(f"Attachment: {REPORT_PATH}")
        if missing:
            print("Missing env vars: " + ", ".join(missing))
        return

    if missing:
        print("Email notification skipped. Missing env vars: " + ", ".join(missing))
        return

    if not REPORT_PATH.exists():
        raise FileNotFoundError(REPORT_PATH)

    review_date, review_text = read_latest_ai_review()
    summary = read_mobile_summary()
    subject = f"StudyPulse Daily Report - {review_date}"
    body = build_mobile_summary_text(summary, review_text) + f"\nAttached: {REPORT_PATH.name}\n"
    html_body = build_mobile_summary_html(summary, review_text)
    message = build_message(sender, recipients, subject, body, html_body, REPORT_PATH)

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as smtp:
                smtp.login(smtp_user, smtp_password)
                smtp.send_message(message, from_addr=sender, to_addrs=recipients)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(smtp_user, smtp_password)
                smtp.send_message(message, from_addr=sender, to_addrs=recipients)
    except smtplib.SMTPAuthenticationError as exc:
        print("Email notification failed: SMTP authentication error.", file=sys.stderr)
        print("For Gmail, use a 16-digit Google App Password, not your normal Gmail password.", file=sys.stderr)
        print("If you already created an App Password, remove spaces when setting STUDYPULSE_SMTP_PASSWORD.", file=sys.stderr)
        print(f"SMTP server response: {exc.smtp_code} {exc.smtp_error!r}", file=sys.stderr)
        raise SystemExit(2)

    print(f"Email notification sent to: {', '.join(recipients)}")


if __name__ == "__main__":
    main()
