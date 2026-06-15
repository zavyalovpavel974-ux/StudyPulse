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
        "focus_minutes",
        "focus_session_count",
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
            SELECT date, phone_total_minutes, study_app_minutes, focus_minutes, focus_session_count, distracting_app_minutes,
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
        "metric_semantics": {
            "study_app_minutes": "已包含番茄 ToDo 截图识别修正后的普通学习 App 时长",
            "focus_minutes": "番茄 ToDo 修正来源说明，不应与 study_app_minutes 重复相加",
            "learning_output_score": "Windows 文件和 R 命令形成的学习记录指标，不代表最终结果或掌握程度",
            "learning_input_score": "学习 App 统计为主，Windows 学习记录作为辅助贡献的整日学习情况指标",
        },
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
        "术语要求：learning_output_score 只能称为“Windows 学习记录”或“Windows/R 学习记录”；"
        "含义是文件与 R 命令留下的学习过程痕迹。"
        "不要把该指标描述为学习完成物、最终交付物、掌握程度或最终结果。\n\n"
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


def normalize_review_terms(review_text: str | None) -> str | None:
    if not review_text:
        return review_text
    replacements = {
        "学习产出": "Windows 学习记录",
        "学习输出": "Windows 学习记录",
        "文件产出": "文件记录",
        "产出痕迹": "学习记录痕迹",
        "输出痕迹": "学习记录痕迹",
        "产出指标": "Windows 学习记录指标",
        "输出指标": "Windows 学习记录指标",
        "产出分数": "Windows 学习记录分数",
        "输出分数": "Windows 学习记录分数",
        "高产出": "高记录",
        "低产出": "低记录",
        "输出目标": "记录目标",
        "产出目标": "记录目标",
        "输出实践": "记录实践",
        "产出": "记录",
        "输出": "记录",
        "成果": "最终结果",
    }
    normalized = review_text
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalized


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
        save_review(conn, str(metrics["date"]), prompt, normalize_review_terms(review_text), model)
        print(f"Review row saved for {metrics['date']}.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
