from __future__ import annotations

import csv
import html
import json
import sqlite3
from pathlib import Path
from typing import Any


def find_project_root() -> Path:
    candidates = [Path.cwd(), Path.cwd().parent]
    script_parent = Path(__file__).resolve().parent
    candidates.extend([script_parent, script_parent.parent])
    for candidate in candidates:
        if (candidate / "sample_data" / "daily_metrics_sample.csv").exists():
            return candidate
    raise FileNotFoundError("Cannot find sample_data/daily_metrics_sample.csv")


def read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_sqlite_context(path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        daily = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM daily_metrics
                ORDER BY date
                """
            ).fetchall()
        ]
        latest_date = daily[-1]["date"] if daily else None
        apps = [
            dict(row)
            for row in conn.execute(
                """
                SELECT app_label, package_name, category, foreground_minutes, open_count, last_used_at
                FROM android_app_usage
                WHERE date = COALESCE(?, date)
                ORDER BY foreground_minutes DESC
                """,
                (latest_date,),
            ).fetchall()
        ]
        files = [
            dict(row)
            for row in conn.execute(
                """
                SELECT extension, activity_type, COUNT(*) AS count
                FROM windows_file_activity
                WHERE date BETWEEN date(?, '-6 day') AND ?
                GROUP BY extension, activity_type
                ORDER BY count DESC, extension
                """,
                (latest_date, latest_date),
            ).fetchall()
        ]
        r_summary_row = conn.execute(
            """
            SELECT *
            FROM r_history_summary
            WHERE date = COALESCE(?, date)
            ORDER BY id DESC
            LIMIT 1
            """,
            (latest_date,),
        ).fetchone()
        weekly_row = conn.execute(
            """
            SELECT *
            FROM weekly_metrics
            ORDER BY week_end DESC
            LIMIT 1
            """
        ).fetchone()
        review_row = conn.execute(
            """
            SELECT prompt, review_text, model_name
            FROM ai_review
            WHERE scope = 'daily'
            ORDER BY generated_at DESC
            LIMIT 1
            """
        ).fetchone()
        return {
            "daily": daily,
            "apps": apps,
            "files": files,
            "r_summary": dict(r_summary_row) if r_summary_row else None,
            "weekly": dict(weekly_row) if weekly_row else None,
            "review": dict(review_row) if review_row else None,
            "data_source": "SQLite database",
        }
    finally:
        conn.close()


def read_csv_context(path: Path) -> dict[str, Any]:
    return {
        "daily": read_csv_rows(path),
        "apps": [],
        "files": [],
        "r_summary": None,
        "weekly": None,
        "review": None,
        "data_source": "sample CSV",
    }


def h(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def as_float(row: dict[str, Any], key: str) -> float:
    value = row.get(key, "")
    return float(value) if value not in ("", None) else 0.0


def as_int(row: dict[str, Any], key: str) -> int:
    return int(round(as_float(row, key)))


def minutes_label(value: float) -> str:
    minutes = int(round(value))
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m" if hours else f"{mins}m"


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def score(value: float) -> str:
    return f"{value:.1f}"


def clamp(value: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, value))


def delta_text(rows: list[dict[str, Any]], key: str) -> str:
    if len(rows) < 2:
        return "No comparison"
    current = as_float(rows[-1], key)
    previous = as_float(rows[-2], key)
    delta = current - previous
    if abs(delta) < 0.05:
        return "No change"
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:.1f} vs yesterday"


def mini_bar(value: float, max_value: float, color: str) -> str:
    width = 0 if max_value <= 0 else clamp(value / max_value * 100)
    return f'<div class="mini-bar"><span style="width:{width:.1f}%;background:{color}"></span></div>'


def donut_svg(segments: list[tuple[str, float, str]], size: int = 184) -> str:
    total = sum(value for _, value, _ in segments)
    if total <= 0:
        return f'<svg viewBox="0 0 {size} {size}" class="donut"><circle cx="92" cy="92" r="66" fill="none" stroke="#e4e4e7" stroke-width="24"/></svg>'
    radius = 66
    circumference = 2 * 3.141592653589793 * radius
    offset = 0.0
    circles = []
    for label, value, color in segments:
        dash = value / total * circumference
        circles.append(
            f'<circle cx="92" cy="92" r="{radius}" fill="none" stroke="{color}" stroke-width="24" '
            f'stroke-dasharray="{dash:.2f} {circumference - dash:.2f}" stroke-dashoffset="{-offset:.2f}" '
            f'transform="rotate(-90 92 92)"><title>{h(label)} {minutes_label(value)}</title></circle>'
        )
        offset += dash
    return f'<svg viewBox="0 0 {size} {size}" class="donut">{"".join(circles)}</svg>'


def line_svg(labels: list[str], values: list[float], stroke: str, width: int = 760, height: int = 230) -> str:
    if not values:
        return ""
    max_value = max(values + [1])
    min_value = min(values + [0])
    value_range = max(max_value - min_value, 1)
    left, right, top, bottom = 46, 18, 18, 38
    plot_width = width - left - right
    plot_height = height - top - bottom
    xs = [left + (plot_width * i / max(len(values) - 1, 1)) for i in range(len(values))]
    ys = [top + plot_height - ((v - min_value) / value_range * plot_height) for v in values]
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    area_points = f"{left},{top + plot_height} {points} {width - right},{top + plot_height}"
    parts = [
        f'<svg viewBox="0 0 {width} {height}" class="line-chart" role="img">',
        f'<polygon points="{area_points}" fill="{stroke}" opacity="0.08"/>',
        f'<line x1="{left}" y1="{top + plot_height}" x2="{width - right}" y2="{top + plot_height}" stroke="#d4d4d8"/>',
        f'<polyline fill="none" stroke="{stroke}" stroke-width="3" points="{points}"/>',
    ]
    for i, (label, value, x, y) in enumerate(zip(labels, values, xs, ys)):
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{stroke}"><title>{h(label)} {value:.1f}</title></circle>')
        if i in (0, len(values) - 1):
            parts.append(f'<text x="{x:.1f}" y="{height - 14}" text-anchor="middle" font-size="12" fill="#71717a">{h(label[5:])}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def category_breakdown(latest: dict[str, Any]) -> list[tuple[str, str, float, str]]:
    return [
        ("study", "学习", as_float(latest, "study_app_minutes"), "#2563eb"),
        ("tool", "工具", as_float(latest, "tool_app_minutes"), "#16a34a"),
        ("social", "社交", as_float(latest, "social_app_minutes"), "#a855f7"),
        ("entertainment", "娱乐", as_float(latest, "entertainment_app_minutes"), "#f97316"),
        ("game", "游戏", as_float(latest, "game_app_minutes"), "#ef4444"),
    ]


def table_html(headers: list[str], rows: list[list[Any]]) -> str:
    thead = "".join(f"<th>{h(header)}</th>" for header in headers)
    tbody = []
    for row in rows:
        tbody.append("<tr>" + "".join(f"<td>{h(cell)}</td>" for cell in row) + "</tr>")
    return f"<table><thead><tr>{thead}</tr></thead><tbody>{''.join(tbody)}</tbody></table>"


def app_table(apps: list[dict[str, Any]]) -> str:
    if not apps:
        return '<div class="empty">暂无 App 明细。真实 Android JSON 导入后会显示 Top App。</div>'
    max_minutes = max(as_float(app, "foreground_minutes") for app in apps) or 1
    colors = {
        "study": "#2563eb",
        "tool": "#16a34a",
        "social": "#a855f7",
        "entertainment": "#f97316",
        "game": "#ef4444",
        "other": "#71717a",
    }
    rows = []
    for app in apps[:8]:
        category = str(app.get("category", "other"))
        rows.append(
            [
                app.get("app_label") or app.get("package_name"),
                category,
                minutes_label(as_float(app, "foreground_minutes")),
                as_int(app, "open_count"),
                mini_bar(as_float(app, "foreground_minutes"), max_minutes, colors.get(category, "#71717a")),
            ]
        )
    return table_html(["App", "分类", "时长", "打开", "占比"], rows)


def file_activity_html(files: list[dict[str, Any]]) -> str:
    if not files:
        return '<div class="empty">暂无学习文件活动。</div>'
    rows = [
        [row["extension"], row["activity_type"], row["count"]]
        for row in files
    ]
    return table_html(["文件类型", "活动", "数量"], rows)


def r_activity_html(r_summary: dict[str, Any] | None) -> str:
    if not r_summary:
        return '<div class="empty">暂无 R history 摘要。</div>'
    package_text = "无"
    try:
        packages = json.loads(r_summary.get("top_packages_json") or "[]")
        if packages:
            package_text = " / ".join(item["name"] for item in packages[:4])
    except json.JSONDecodeError:
        pass
    rows = [
        ["命令总数", r_summary.get("command_count", 0)],
        ["数据读取", r_summary.get("data_import_count", 0)],
        ["数据清洗", r_summary.get("data_cleaning_count", 0)],
        ["可视化", r_summary.get("visualization_count", 0)],
        ["统计分析", r_summary.get("statistics_count", 0)],
        ["建模", r_summary.get("modeling_count", 0)],
        ["常用包", package_text],
    ]
    return table_html(["R 活动", "值"], rows)


def ai_prompt_from_latest(latest: dict[str, Any]) -> str:
    payload = {
        "date": latest["date"],
        "phone_total_minutes": as_float(latest, "phone_total_minutes"),
        "study_app_minutes": as_float(latest, "study_app_minutes"),
        "tool_app_minutes": as_float(latest, "tool_app_minutes"),
        "distracting_app_minutes": as_float(latest, "distracting_app_minutes"),
        "distracting_ratio": as_float(latest, "distracting_ratio"),
        "total_study_files_count": as_int(latest, "total_study_files_count"),
        "study_files_modified_7d_count": as_int(latest, "study_files_modified_7d_count"),
        "study_files_modified_count": as_int(latest, "study_files_modified_count"),
        "study_files_created_count": as_int(latest, "study_files_created_count"),
        "r_command_count": as_int(latest, "r_command_count"),
        "r_visualization_count": as_int(latest, "r_visualization_count"),
        "r_modeling_count": as_int(latest, "r_modeling_count"),
        "learning_input_score": as_float(latest, "learning_input_score"),
        "learning_output_score": as_float(latest, "learning_output_score"),
        "distraction_risk_score": as_float(latest, "distraction_risk_score"),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_report(context: dict[str, Any], output_path: Path) -> None:
    daily = context["daily"]
    latest = daily[-1]
    labels = [str(row["date"]) for row in daily]
    input_scores = [as_float(row, "learning_input_score") for row in daily]
    output_scores = [as_float(row, "learning_output_score") for row in daily]
    risk_scores = [as_float(row, "distraction_risk_score") for row in daily]
    breakdown = category_breakdown(latest)
    donut_segments = [(label, value, color) for _, label, value, color in breakdown]
    phone_total = as_float(latest, "phone_total_minutes")
    study_minutes = as_float(latest, "study_app_minutes")
    distracting_ratio = as_float(latest, "distracting_ratio")
    risk = as_float(latest, "distraction_risk_score")
    output_score = as_float(latest, "learning_output_score")
    total_files = as_int(latest, "total_study_files_count")
    recent_files = as_int(latest, "study_files_modified_7d_count")
    today_files = as_int(latest, "study_files_modified_count") + as_int(latest, "study_files_created_count")
    ai_review = context.get("review") or {}
    ai_review_text = ai_review.get("review_text") or "尚未配置真实 MiMo API，当前保留聚合指标 prompt，可接入后自动生成复盘。"
    weekly = context.get("weekly") or {}
    generated_at = latest.get("generated_at", "")

    breakdown_rows = []
    max_part = max([value for _, _, value, _ in breakdown] + [1])
    for key, label, value, color in breakdown:
        breakdown_rows.append(
            f"""
            <div class="breakdown-row">
              <div><span class="dot" style="background:{color}"></span>{h(label)}</div>
              <strong>{minutes_label(value)}</strong>
              {mini_bar(value, max_part, color)}
            </div>
            """
        )

    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>StudyPulse Dashboard</title>
  <style>
    :root {{
      --bg:#f5f7fb; --surface:#ffffff; --line:#e5e7eb; --text:#111827; --muted:#6b7280;
      --blue:#2563eb; --green:#16a34a; --amber:#f59e0b; --red:#dc2626; --purple:#9333ea;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font-family:Inter, Arial, "Microsoft YaHei", sans-serif; }}
    .shell {{ display:grid; grid-template-columns:236px minmax(0,1fr); min-height:100vh; }}
    aside {{ background:#111827; color:#e5e7eb; padding:24px 18px; }}
    .brand {{ font-size:20px; font-weight:800; margin-bottom:6px; }}
    .brand-sub {{ color:#9ca3af; font-size:12px; line-height:1.5; margin-bottom:28px; }}
    nav a {{ display:block; color:#d1d5db; text-decoration:none; padding:10px 12px; border-radius:8px; margin:4px 0; font-size:14px; }}
    nav a.active {{ background:#1f2937; color:#fff; }}
    .privacy {{ margin-top:28px; border-top:1px solid #374151; padding-top:18px; color:#9ca3af; font-size:12px; line-height:1.6; }}
    main {{ padding:28px; max-width:1320px; width:100%; }}
    .topbar {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:20px; }}
    h1 {{ margin:0 0 8px; font-size:28px; letter-spacing:0; }}
    h2 {{ margin:0 0 14px; font-size:17px; }}
    .muted {{ color:var(--muted); font-size:13px; line-height:1.5; }}
    .status {{ display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; }}
    .pill {{ background:#fff; border:1px solid var(--line); border-radius:999px; padding:7px 11px; font-size:12px; color:#374151; }}
    .grid-4 {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; }}
    .grid-main {{ display:grid; grid-template-columns:minmax(0,1.35fr) minmax(320px,.65fr); gap:14px; margin-top:14px; }}
    .grid-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:14px; }}
    .panel {{ background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:18px; min-width:0; overflow:hidden; }}
    .kpi-label {{ color:var(--muted); font-size:13px; }}
    .kpi-value {{ font-size:30px; font-weight:800; margin:9px 0 6px; }}
    .kpi-foot {{ color:var(--muted); font-size:12px; }}
    .score-ring {{ display:grid; grid-template-columns:190px 1fr; gap:18px; align-items:center; }}
    .donut {{ width:184px; height:184px; }}
    .breakdown-row {{ display:grid; grid-template-columns:84px 72px 1fr; gap:10px; align-items:center; margin:10px 0; font-size:13px; }}
    .dot {{ display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:7px; }}
    .mini-bar {{ height:8px; background:#eef2f7; border-radius:999px; overflow:hidden; min-width:80px; }}
    .mini-bar span {{ display:block; height:100%; border-radius:999px; }}
    .line-chart {{ width:100%; height:auto; min-width:560px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th, td {{ border-bottom:1px solid var(--line); padding:10px 8px; text-align:left; vertical-align:middle; }}
    th {{ color:#4b5563; font-weight:700; background:#f9fafb; }}
    td:last-child {{ min-width:110px; }}
    pre {{ margin:0; white-space:pre-wrap; color:#d1d5db; background:#111827; border-radius:8px; padding:14px; font-size:12px; max-height:260px; overflow:auto; }}
    .insight {{ border-left:4px solid var(--blue); background:#eff6ff; padding:12px 14px; border-radius:4px; line-height:1.7; font-size:14px; }}
    .empty {{ color:var(--muted); font-size:13px; padding:16px 0; }}
    .summary-list {{ display:grid; gap:10px; font-size:13px; }}
    .summary-list div {{ display:flex; justify-content:space-between; gap:12px; border-bottom:1px solid var(--line); padding-bottom:9px; }}
    @media (max-width: 980px) {{
      .shell {{ grid-template-columns:1fr; }}
      aside {{ display:none; }}
      main {{ padding:18px; }}
      .grid-4, .grid-main, .grid-2 {{ grid-template-columns:1fr; }}
      .topbar {{ display:block; }}
      .status {{ justify-content:flex-start; margin-top:12px; }}
      .score-ring {{ grid-template-columns:1fr; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <div class="brand">StudyPulse</div>
      <div class="brand-sub">Android + Windows 学习行为复盘仪表盘</div>
      <nav>
        <a class="active" href="#overview">Overview</a>
        <a href="#phone">Phone Usage</a>
        <a href="#trend">Trends</a>
        <a href="#work">Work Output</a>
        <a href="#ai">AI Review</a>
      </nav>
      <div class="privacy">本报告只使用聚合指标和脱敏摘要，不读取聊天内容、文件正文或完整浏览器历史。</div>
    </aside>
    <main>
      <section class="topbar" id="overview">
        <div>
          <h1>学习行为复盘仪表盘</h1>
          <div class="muted">数据来源：{h(context["data_source"])}。生成时间：{h(generated_at)}。结果用于自我复盘，不等同于学习质量评价。</div>
        </div>
        <div class="status">
          <span class="pill">日期 {h(latest["date"])}</span>
          <span class="pill">MiMo {h((context.get("review") or {}).get("model_name") or "未调用")}</span>
          <span class="pill">本地 SQLite</span>
        </div>
      </section>

      <section class="grid-4">
        <div class="panel"><div class="kpi-label">手机总使用</div><div class="kpi-value">{minutes_label(phone_total)}</div><div class="kpi-foot">{h(delta_text(daily, "phone_total_minutes"))}</div></div>
        <div class="panel"><div class="kpi-label">学习类 App</div><div class="kpi-value">{minutes_label(study_minutes)}</div><div class="kpi-foot">{h(delta_text(daily, "study_app_minutes"))}</div></div>
        <div class="panel"><div class="kpi-label">学习产出指数</div><div class="kpi-value">{score(output_score)}</div><div class="kpi-foot">{h(delta_text(daily, "learning_output_score"))}</div></div>
        <div class="panel"><div class="kpi-label">学习文件</div><div class="kpi-value">{total_files}</div><div class="kpi-foot">近 7 天 {recent_files}，今日 {today_files}</div></div>
      </section>

      <section class="grid-main" id="phone">
        <div class="panel">
          <h2>今日时间结构</h2>
          <div class="score-ring">
            {donut_svg(donut_segments)}
            <div>{''.join(breakdown_rows)}</div>
          </div>
        </div>
        <div class="panel">
          <h2>本周摘要</h2>
          <div class="summary-list">
            <div><span>周期</span><strong>{h(weekly.get("week_start", "-"))} 至 {h(weekly.get("week_end", "-"))}</strong></div>
            <div><span>学习 App 总时长</span><strong>{minutes_label(float(weekly.get("total_study_app_minutes", 0) or 0))}</strong></div>
            <div><span>分心 App 总时长</span><strong>{minutes_label(float(weekly.get("total_distracting_app_minutes", 0) or 0))}</strong></div>
            <div><span>R 命令总数</span><strong>{int(float(weekly.get("total_r_commands", 0) or 0))}</strong></div>
            <div><span>分心风险指数</span><strong>{score(risk)} / {pct(distracting_ratio)}</strong></div>
            <div><span>产出较高日</span><strong>{h(weekly.get("best_day", "-"))}</strong></div>
            <div><span>风险较高日</span><strong>{h(weekly.get("risk_day", "-"))}</strong></div>
          </div>
        </div>
      </section>

      <section class="grid-2" id="trend">
        <div class="panel">
          <h2>学习投入趋势</h2>
          {line_svg(labels, input_scores, "#2563eb")}
        </div>
        <div class="panel">
          <h2>分心风险趋势</h2>
          {line_svg(labels, risk_scores, "#dc2626")}
        </div>
      </section>

      <section class="grid-2">
        <div class="panel">
          <h2>学习产出趋势</h2>
          {line_svg(labels, output_scores, "#16a34a")}
        </div>
        <div class="panel">
          <h2>Top App 使用</h2>
          {app_table(context["apps"])}
        </div>
      </section>

      <section class="grid-2" id="work">
        <div class="panel">
          <h2>Windows 学习文件活动</h2>
          {file_activity_html(context["files"])}
        </div>
        <div class="panel">
          <h2>RStudio / R 学习痕迹</h2>
          {r_activity_html(context["r_summary"])}
        </div>
      </section>

      <section class="grid-2" id="ai">
        <div class="panel">
          <h2>AI 复盘建议</h2>
          <div class="insight">{h(ai_review_text)}</div>
        </div>
        <div class="panel">
          <h2>发送给 MiMo 的聚合指标</h2>
          <pre>{h(ai_prompt_from_latest(latest))}</pre>
        </div>
      </section>
    </main>
  </div>
</body>
</html>
"""
    output_path.write_text(html_doc, encoding="utf-8")


def main() -> None:
    root = find_project_root()
    db_path = root / "data" / "studypulse.db"
    csv_path = root / "sample_data" / "daily_metrics_sample.csv"
    report_dir = root / "reports"
    report_dir.mkdir(exist_ok=True)

    context = read_sqlite_context(db_path) if db_path.exists() else read_csv_context(csv_path)
    if not context["daily"]:
        raise ValueError("No daily metrics available")
    output_path = report_dir / "studypulse_sample_report.html"
    build_report(context, output_path)
    print(f"Report written to: {output_path}")


if __name__ == "__main__":
    main()
