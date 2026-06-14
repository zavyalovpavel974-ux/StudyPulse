from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from studypulse_config import load_config


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "studypulse.db"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def latest_metrics(conn: sqlite3.Connection) -> dict:
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT *
        FROM daily_metrics
        ORDER BY date DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise RuntimeError("No daily_metrics row found. Run scripts/build_database.py first.")
    keys = [
        "date",
        "phone_total_minutes",
        "study_app_minutes",
        "tool_app_minutes",
        "social_app_minutes",
        "entertainment_app_minutes",
        "game_app_minutes",
        "distracting_app_minutes",
        "distracting_ratio",
        "app_open_count",
        "total_study_files_count",
        "study_files_modified_7d_count",
        "study_files_modified_count",
        "study_files_created_count",
        "r_command_count",
        "r_visualization_count",
        "r_modeling_count",
        "learning_input_score",
        "learning_output_score",
        "distraction_risk_score",
        "r_activity_score",
    ]
    return {key: row[key] for key in keys}


def latest_context(conn: sqlite3.Connection) -> dict:
    metrics = latest_metrics(conn)
    date_value = str(metrics["date"])

    recent_daily = [
        dict(row)
        for row in conn.execute(
            """
            SELECT date, phone_total_minutes, study_app_minutes, distracting_app_minutes,
                   distracting_ratio, study_files_modified_count, r_command_count,
                   learning_output_score, distraction_risk_score
            FROM daily_metrics
            WHERE date <= ?
            ORDER BY date DESC
            LIMIT 7
            """,
            (date_value,),
        ).fetchall()
    ]
    weekly = conn.execute(
        """
        SELECT *
        FROM weekly_metrics
        WHERE week_end = ?
        ORDER BY generated_at DESC
        LIMIT 1
        """,
        (date_value,),
    ).fetchone()
    monthly = conn.execute(
        """
        SELECT *
        FROM monthly_metrics
        WHERE month_end = ?
        ORDER BY generated_at DESC
        LIMIT 1
        """,
        (date_value,),
    ).fetchone()
    quality = conn.execute(
        """
        SELECT *
        FROM data_quality_report
        WHERE date = ?
        LIMIT 1
        """,
        (date_value,),
    ).fetchone()

    return {
        "latest_metrics": metrics,
        "recent_daily_metrics": list(reversed(recent_daily)),
        "weekly_metrics": dict(weekly) if weekly else {},
        "monthly_metrics": dict(monthly) if monthly else {},
        "data_quality": dict(quality) if quality else {},
    }


def build_prompt(context: dict) -> str:
    payload = json.dumps(context, ensure_ascii=False, indent=2)
    return (
        "你是 StudyPulse 的学习行为复盘助手。请基于下面的聚合指标生成中文日报复盘。\n\n"
        "要求：只做趋势分析，不做道德评判；使用“可能、估计、建议”等谨慎表达；"
        "不要声称能看到屏幕内容、通知内容、聊天内容或输入内容。\n\n"
        "输出必须分成两个大部分：\n\n"
        "一、原有总结\n"
        "保留日报总结风格，包含：今日概况、主要风险、明日建议。\n\n"
        "二、行动化补充\n"
        "额外给出以下五项，并与上面的原有总结明显分开：\n"
        "1. 今日最大问题：一句话指出最优先处理的问题。\n"
        "2. 今日正向信号：指出一个值得保留的行为或痕迹。\n"
        "3. 明天一个最小行动：必须具体、低成本、可执行。\n"
        "4. 风险提醒：指出一个可能导致复盘失真的数据质量或行为风险。\n"
        "5. 趋势对比：如果 recent_daily_metrics 不足 7 天，明确写“当前为早期趋势，样本不足 7 天”；否则比较最近 7 天变化。\n\n"
        f"聚合指标：\n{payload}"
    )


def call_openai_compatible(api_base_url: str, api_key: str, model: str, prompt: str) -> str:
    url = api_base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个谨慎、具体、尊重隐私的学习行为复盘助手。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AI API HTTP {exc.code}: {detail}") from exc
    return data["choices"][0]["message"]["content"]


def save_review(conn: sqlite3.Connection, target_date: str, prompt: str, review_text: str | None, model: str) -> None:
    conn.execute(
        """
        INSERT INTO ai_review (scope, target_date, prompt, review_text, model_name, generated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("daily", target_date, prompt, review_text, model, now_text()),
    )
    conn.commit()


def main() -> None:
    config = load_config()
    mimo = config["mimo"]
    model = mimo["model"]
    api_base_url = mimo.get("api_base_url", "")
    api_key_env = mimo.get("api_key_env", "MIMO_API_KEY")
    api_key = os.environ.get(api_key_env, "")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        context = latest_context(conn)
        metrics = context["latest_metrics"]
        prompt = build_prompt(context)
        review_text = None
        if api_base_url and api_key:
            try:
                print(f"Calling AI API endpoint: {api_base_url.rstrip('/')}/chat/completions")
                review_text = call_openai_compatible(api_base_url, api_key, model, prompt)
                print("AI review generated through API.")
            except Exception as exc:
                review_text = (
                    "MiMo API 调用失败，已保留聚合指标 prompt。\n"
                    f"错误类型：{type(exc).__name__}；错误信息：{exc}"
                )
                print(review_text)
        else:
            print("AI API not configured. Saved prompt only.")
        save_review(conn, str(metrics["date"]), prompt, review_text, model)
        print(f"Review row saved for {metrics['date']}.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
