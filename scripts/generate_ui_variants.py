from __future__ import annotations

import html
import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "studypulse.db"
REPORT_DIR = ROOT / "reports"


def h(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def f(row: dict[str, Any], key: str) -> float:
    value = row.get(key, 0)
    return float(value or 0)


def i(row: dict[str, Any], key: str) -> int:
    return int(round(f(row, key)))


def minutes(value: float) -> str:
    total = int(round(value))
    hours, mins = divmod(total, 60)
    return f"{hours}h {mins}m" if hours else f"{mins}m"


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def load_context() -> dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        daily = [dict(row) for row in conn.execute("SELECT * FROM daily_metrics ORDER BY date")]
        latest_date = daily[-1]["date"]
        apps = [
            dict(row)
            for row in conn.execute(
                """
                SELECT app_label, category, foreground_minutes, open_count
                FROM android_app_usage
                WHERE date = ?
                ORDER BY foreground_minutes DESC
                """,
                (latest_date,),
            )
        ]
        files = [
            dict(row)
            for row in conn.execute(
                """
                SELECT extension, activity_type, COUNT(*) AS count
                FROM windows_file_activity
                WHERE date = ?
                GROUP BY extension, activity_type
                ORDER BY count DESC, extension
                """,
                (latest_date,),
            )
        ]
        r_summary = conn.execute(
            "SELECT * FROM r_history_summary WHERE date = ? ORDER BY id DESC LIMIT 1",
            (latest_date,),
        ).fetchone()
        weekly = conn.execute("SELECT * FROM weekly_metrics ORDER BY week_end DESC LIMIT 1").fetchone()
        review = conn.execute(
            "SELECT review_text, model_name FROM ai_review WHERE scope = 'daily' ORDER BY generated_at DESC LIMIT 1"
        ).fetchone()
        return {
            "daily": daily,
            "latest": daily[-1],
            "apps": apps,
            "files": files,
            "r_summary": dict(r_summary) if r_summary else {},
            "weekly": dict(weekly) if weekly else {},
            "review": dict(review) if review else {},
        }
    finally:
        conn.close()


def sparkline(values: list[float], color: str = "#2563eb", width: int = 420, height: int = 120) -> str:
    if not values:
        return ""
    lo, hi = min(values + [0]), max(values + [1])
    span = max(hi - lo, 1)
    left, right, top, bottom = 18, 18, 12, 20
    plot_w = width - left - right
    plot_h = height - top - bottom
    xs = [left + plot_w * idx / max(len(values) - 1, 1) for idx in range(len(values))]
    ys = [top + plot_h - (value - lo) / span * plot_h for value in values]
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    area = f"{left},{top + plot_h} {points} {width - right},{top + plot_h}"
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}"/>' for x, y in zip(xs, ys))
    return (
        f'<svg viewBox="0 0 {width} {height}" class="chart">'
        f'<polygon points="{area}" fill="{color}" opacity=".09"/>'
        f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="3"/>'
        f'{dots}</svg>'
    )


def bar_list(rows: list[tuple[str, float, str]], max_value: float | None = None) -> str:
    maximum = max_value or max([value for _, value, _ in rows] + [1])
    items = []
    for label, value, color in rows:
        width = 0 if maximum <= 0 else min(100, value / maximum * 100)
        items.append(
            f"""
            <div class="bar-row">
              <div class="bar-head"><span>{h(label)}</span><strong>{minutes(value)}</strong></div>
              <div class="track"><span style="width:{width:.1f}%;background:{color}"></span></div>
            </div>
            """
        )
    return "".join(items)


def app_rows(apps: list[dict[str, Any]], limit: int = 7) -> str:
    if not apps:
        return '<tr><td colspan="4">No app data</td></tr>'
    return "".join(
        f"<tr><td>{h(app.get('app_label'))}</td><td>{h(app.get('category'))}</td>"
        f"<td>{minutes(f(app, 'foreground_minutes'))}</td><td>{i(app, 'open_count')}</td></tr>"
        for app in apps[:limit]
    )


def file_rows(files: list[dict[str, Any]]) -> str:
    if not files:
        return '<tr><td colspan="3">No file activity</td></tr>'
    return "".join(
        f"<tr><td>{h(row['extension'])}</td><td>{h(row['activity_type'])}</td><td>{h(row['count'])}</td></tr>"
        for row in files
    )


def r_summary_items(r_summary: dict[str, Any]) -> str:
    if not r_summary:
        return '<div class="empty">No R history summary</div>'
    packages = "None"
    try:
        parsed = json.loads(r_summary.get("top_packages_json") or "[]")
        if parsed:
            packages = " / ".join(item["name"] for item in parsed[:3])
    except json.JSONDecodeError:
        pass
    items = [
        ("Commands", r_summary.get("command_count", 0)),
        ("Import", r_summary.get("data_import_count", 0)),
        ("Cleaning", r_summary.get("data_cleaning_count", 0)),
        ("Visual", r_summary.get("visualization_count", 0)),
        ("Stats", r_summary.get("statistics_count", 0)),
        ("Modeling", r_summary.get("modeling_count", 0)),
        ("Packages", packages),
    ]
    return "".join(f'<div class="kv"><span>{h(k)}</span><strong>{h(v)}</strong></div>' for k, v in items)


def metric_payload(latest: dict[str, Any]) -> str:
    payload = {
        "date": latest["date"],
        "phone_total_minutes": f(latest, "phone_total_minutes"),
        "study_app_minutes": f(latest, "study_app_minutes"),
        "distracting_ratio": f(latest, "distracting_ratio"),
        "learning_input_score": f(latest, "learning_input_score"),
        "learning_output_score": f(latest, "learning_output_score"),
        "distraction_risk_score": f(latest, "distraction_risk_score"),
        "r_command_count": i(latest, "r_command_count"),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def category_data(latest: dict[str, Any]) -> list[tuple[str, float, str]]:
    return [
        ("Study", f(latest, "study_app_minutes"), "#2563eb"),
        ("Tool", f(latest, "tool_app_minutes"), "#16a34a"),
        ("Social", f(latest, "social_app_minutes"), "#9333ea"),
        ("Entertainment", f(latest, "entertainment_app_minutes"), "#f97316"),
        ("Game", f(latest, "game_app_minutes"), "#dc2626"),
    ]


def base_values(ctx: dict[str, Any]) -> dict[str, Any]:
    latest = ctx["latest"]
    daily = ctx["daily"]
    return {
        "date": latest["date"],
        "phone": minutes(f(latest, "phone_total_minutes")),
        "study": minutes(f(latest, "study_app_minutes")),
        "output": f(latest, "learning_output_score"),
        "risk": f(latest, "distraction_risk_score"),
        "ratio": pct(f(latest, "distracting_ratio")),
        "input_chart": sparkline([f(row, "learning_input_score") for row in daily], "#2563eb"),
        "risk_chart": sparkline([f(row, "distraction_risk_score") for row in daily], "#dc2626"),
        "output_chart": sparkline([f(row, "learning_output_score") for row in daily], "#16a34a"),
        "review": ctx["review"].get("review_text") or "MiMo API 尚未配置，当前显示 prompt-only 复盘占位。",
        "prompt": metric_payload(latest),
    }


def render_enterprise(ctx: dict[str, Any]) -> str:
    v = base_values(ctx)
    weekly = ctx["weekly"]
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>StudyPulse Enterprise</title>
<style>
body{{margin:0;background:#f3f5f9;color:#1f2937;font-family:Arial,'Microsoft YaHei',sans-serif}}.layout{{display:grid;grid-template-columns:232px 1fr;min-height:100vh}}aside{{background:#001529;color:#cbd5e1;padding:20px}}.logo{{color:#fff;font-weight:800;font-size:20px;margin-bottom:24px}}nav div{{padding:11px 12px;border-radius:6px;margin:4px 0}}nav .on{{background:#1677ff;color:#fff}}main{{padding:24px}}.top{{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}}h1{{margin:0;font-size:24px}}.sub{{color:#6b7280;font-size:13px}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}.card,.panel{{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:18px}}.label{{color:#6b7280;font-size:13px}}.num{{font-size:28px;font-weight:800;margin-top:8px}}.grid{{display:grid;grid-template-columns:1.2fr .8fr;gap:14px;margin-top:14px}}.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{border-bottom:1px solid #edf0f5;padding:10px;text-align:left}}th{{background:#fafafa}}.chart{{width:100%;height:auto}}.bar-row{{margin:12px 0}}.bar-head{{display:flex;justify-content:space-between;font-size:13px}}.track{{height:8px;background:#eef2f7;border-radius:99px;overflow:hidden}}.track span{{display:block;height:100%}}.kv{{display:flex;justify-content:space-between;border-bottom:1px solid #edf0f5;padding:10px 0}}pre{{white-space:pre-wrap;background:#111827;color:#d1d5db;padding:14px;border-radius:8px;font-size:12px}}@media(max-width:900px){{.layout{{grid-template-columns:1fr}}aside{{display:none}}.cards,.grid,.grid2{{grid-template-columns:1fr}}}}
</style></head><body><div class="layout"><aside><div class="logo">StudyPulse</div><nav><div class="on">Dashboard</div><div>Usage</div><div>Output</div><div>AI Review</div></nav></aside><main><section class="top"><div><h1>学习行为运营台</h1><div class="sub">企业后台风格：高信息密度、清晰表格、稳定指标区。</div></div><div class="sub">Date {h(v['date'])}</div></section>
<section class="cards"><div class="card"><div class="label">手机总使用</div><div class="num">{v['phone']}</div></div><div class="card"><div class="label">学习 App</div><div class="num">{v['study']}</div></div><div class="card"><div class="label">学习产出</div><div class="num">{v['output']:.1f}</div></div><div class="card"><div class="label">分心风险</div><div class="num">{v['risk']:.1f}</div></div></section>
<section class="grid"><div class="panel"><h2>学习投入趋势</h2>{v['input_chart']}</div><div class="panel"><h2>今日时间结构</h2>{bar_list(category_data(ctx['latest']))}</div></section>
<section class="grid2"><div class="panel"><h2>Top App 使用</h2><table><thead><tr><th>App</th><th>分类</th><th>时长</th><th>打开</th></tr></thead><tbody>{app_rows(ctx['apps'])}</tbody></table></div><div class="panel"><h2>周摘要</h2><div class="kv"><span>周期</span><strong>{h(weekly.get('week_start'))} - {h(weekly.get('week_end'))}</strong></div><div class="kv"><span>学习总时长</span><strong>{minutes(float(weekly.get('total_study_app_minutes', 0) or 0))}</strong></div><div class="kv"><span>分心总时长</span><strong>{minutes(float(weekly.get('total_distracting_app_minutes', 0) or 0))}</strong></div><div class="kv"><span>R 命令</span><strong>{h(weekly.get('total_r_commands', 0))}</strong></div></div></section>
<section class="grid2"><div class="panel"><h2>学习文件活动</h2><table><tbody>{file_rows(ctx['files'])}</tbody></table></div><div class="panel"><h2>RStudio 痕迹</h2>{r_summary_items(ctx['r_summary'])}</div></section>
<section class="grid2"><div class="panel"><h2>MiMo 复盘</h2><p>{h(v['review'])}</p></div><div class="panel"><h2>聚合指标 Prompt</h2><pre>{h(v['prompt'])}</pre></div></section></main></div></body></html>"""


def render_ops(ctx: dict[str, Any]) -> str:
    v = base_values(ctx)
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>StudyPulse Ops</title>
<style>
body{{margin:0;background:#f8fafc;color:#0f172a;font-family:Arial,'Microsoft YaHei',sans-serif}}main{{max-width:1180px;margin:0 auto;padding:24px}}.header{{display:flex;justify-content:space-between;gap:18px;margin-bottom:18px}}h1{{margin:0;font-size:26px}}.tabs{{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}}.tabs span{{border:1px solid #dbe3ef;background:#fff;border-radius:999px;padding:8px 12px;font-size:13px}}.tabs .on{{background:#0f172a;color:#fff}}.hero{{display:grid;grid-template-columns:1.1fr .9fr;gap:14px}}.panel{{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:18px}}.score{{font-size:56px;font-weight:900;line-height:1}}.muted{{color:#64748b;font-size:13px}}.metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:14px}}.metric{{border:1px solid #e2e8f0;border-radius:8px;padding:14px;background:#fff}}.metric strong{{display:block;font-size:26px;margin-top:7px}}.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;margin-top:14px}}.chart{{width:100%;height:auto}}.bar-row{{margin:14px 0}}.bar-head{{display:flex;justify-content:space-between}}.track{{height:10px;background:#e2e8f0;border-radius:99px;overflow:hidden}}.track span{{display:block;height:100%}}table{{width:100%;border-collapse:collapse;font-size:13px}}td,th{{padding:10px;border-bottom:1px solid #e2e8f0;text-align:left}}.timeline{{display:grid;gap:10px}}.step{{display:grid;grid-template-columns:12px 1fr;gap:10px;align-items:start}}.step i{{width:10px;height:10px;border-radius:50%;background:#2563eb;margin-top:5px}}pre{{white-space:pre-wrap;background:#0f172a;color:#dbeafe;padding:14px;border-radius:8px;font-size:12px}}@media(max-width:900px){{.hero,.grid,.metrics{{grid-template-columns:1fr}}.header{{display:block}}}}
</style></head><body><main><section class="header"><div><h1>StudyPulse Control Room</h1><div class="muted">运营控制台风格：强调当天状态、风险解释和下一步动作。</div><div class="tabs"><span class="on">Today</span><span>Week</span><span>Phone</span><span>RStudio</span><span>AI</span></div></div><div class="muted">Date {h(v['date'])}</div></section>
<section class="hero"><div class="panel"><div class="muted">今日分心风险</div><div class="score">{v['risk']:.1f}</div><p class="muted">分心类时长占比 {v['ratio']}。该指标用于提示风险，不做评价。</p>{v['risk_chart']}</div><div class="panel"><h2>今日行动线索</h2><div class="timeline"><div class="step"><i></i><div><strong>学习投入</strong><div class="muted">学习类 App 使用 {v['study']}。</div></div></div><div class="step"><i></i><div><strong>学习产出</strong><div class="muted">学习产出指数 {v['output']:.1f}。</div></div></div><div class="step"><i></i><div><strong>复盘建议</strong><div class="muted">{h(v['review'])}</div></div></div></div></div></section>
<section class="metrics"><div class="metric"><span class="muted">手机总使用</span><strong>{v['phone']}</strong></div><div class="metric"><span class="muted">学习 App</span><strong>{v['study']}</strong></div><div class="metric"><span class="muted">产出指数</span><strong>{v['output']:.1f}</strong></div></section>
<section class="grid"><div class="panel"><h2>时间结构</h2>{bar_list(category_data(ctx['latest']))}</div><div class="panel"><h2>学习产出趋势</h2>{v['output_chart']}</div></section>
<section class="grid"><div class="panel"><h2>Top App</h2><table><thead><tr><th>App</th><th>分类</th><th>时长</th><th>打开</th></tr></thead><tbody>{app_rows(ctx['apps'])}</tbody></table></div><div class="panel"><h2>R 与文件产出</h2>{r_summary_items(ctx['r_summary'])}<table><tbody>{file_rows(ctx['files'])}</tbody></table></div></section>
<section class="panel" style="margin-top:14px"><h2>MiMo Prompt</h2><pre>{h(v['prompt'])}</pre></section></main></body></html>"""


def render_analytics(ctx: dict[str, Any]) -> str:
    v = base_values(ctx)
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>StudyPulse Analytics</title>
<style>
body{{margin:0;background:#ffffff;color:#111827;font-family:Arial,'Microsoft YaHei',sans-serif}}main{{max-width:1120px;margin:0 auto;padding:32px 22px}}.eyebrow{{font-size:12px;text-transform:uppercase;color:#2563eb;font-weight:800;letter-spacing:.08em}}h1{{font-size:34px;margin:6px 0 8px}}.lead{{color:#6b7280;max-width:760px;line-height:1.6}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:26px 0}}.card,.panel{{border:1px solid #e5e7eb;border-radius:8px;padding:18px;background:#fff}}.card strong{{display:block;font-size:30px;margin:9px 0}}.muted{{color:#6b7280;font-size:13px}}.hero{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.chart{{width:100%;height:auto}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}}.bar-row{{margin:14px 0}}.bar-head{{display:flex;justify-content:space-between;font-size:13px}}.track{{height:8px;background:#f3f4f6;border-radius:999px;overflow:hidden}}.track span{{display:block;height:100%}}table{{width:100%;border-collapse:collapse;font-size:13px}}td,th{{padding:10px;border-bottom:1px solid #f0f2f5;text-align:left}}pre{{white-space:pre-wrap;background:#f9fafb;border:1px solid #e5e7eb;padding:14px;border-radius:8px;font-size:12px}}.insight{{font-size:15px;line-height:1.8;border-left:4px solid #2563eb;background:#f8fbff;padding:14px;border-radius:4px}}.kv{{display:flex;justify-content:space-between;border-bottom:1px solid #f0f2f5;padding:10px 0}}@media(max-width:900px){{.cards,.hero,.grid{{grid-template-columns:1fr}}}}
</style></head><body><main><div class="eyebrow">StudyPulse Analytics</div><h1>个人学习行为分析</h1><p class="lead">分析型产品页面风格：减少导航负担，突出指标解释、趋势和 AI 复盘，适合课堂展示和汇报。</p>
<section class="cards"><div class="card"><span class="muted">Phone</span><strong>{v['phone']}</strong><span class="muted">总使用</span></div><div class="card"><span class="muted">Study</span><strong>{v['study']}</strong><span class="muted">学习类 App</span></div><div class="card"><span class="muted">Output</span><strong>{v['output']:.1f}</strong><span class="muted">产出指数</span></div><div class="card"><span class="muted">Risk</span><strong>{v['risk']:.1f}</strong><span class="muted">分心风险</span></div></section>
<section class="hero"><div class="panel"><h2>学习投入</h2>{v['input_chart']}</div><div class="panel"><h2>分心风险</h2>{v['risk_chart']}</div></section>
<section class="grid"><div class="panel"><h2>今日时间分类</h2>{bar_list(category_data(ctx['latest']))}</div><div class="panel"><h2>AI Insight</h2><div class="insight">{h(v['review'])}</div></div></section>
<section class="grid"><div class="panel"><h2>Top App 使用</h2><table><thead><tr><th>App</th><th>分类</th><th>时长</th><th>打开</th></tr></thead><tbody>{app_rows(ctx['apps'])}</tbody></table></div><div class="panel"><h2>学习产出证据</h2>{r_summary_items(ctx['r_summary'])}<table><tbody>{file_rows(ctx['files'])}</tbody></table></div></section>
<section class="panel" style="margin-top:14px"><h2>聚合指标</h2><pre>{h(v['prompt'])}</pre></section></main></body></html>"""


def main() -> None:
    REPORT_DIR.mkdir(exist_ok=True)
    ctx = load_context()
    outputs = {
        "studypulse_ui_enterprise.html": render_enterprise(ctx),
        "studypulse_ui_ops.html": render_ops(ctx),
        "studypulse_ui_analytics.html": render_analytics(ctx),
    }
    for name, content in outputs.items():
        path = REPORT_DIR / name
        path.write_text(content, encoding="utf-8")
        print(f"written {path}")


if __name__ == "__main__":
    main()
