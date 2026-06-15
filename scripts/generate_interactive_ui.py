from __future__ import annotations

import html
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "studypulse.db"
REPORT_DIR = ROOT / "reports"

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
    "com.zmzx.college.search": "智慧树",
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
    "com.plan.kot32.tomatotime": "番茄 ToDo",
}

def load_payload() -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    status_path = ROOT / "data" / "pipeline_status.json"
    pipeline_status = {}
    if status_path.exists():
        try:
            pipeline_status = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pipeline_status = {"status": "invalid", "message": "pipeline_status.json could not be parsed"}
    try:
        daily = [dict(row) for row in conn.execute("SELECT * FROM daily_metrics ORDER BY date")]
        latest_date = daily[-1]["date"]
        apps = [
            dict(row)
            for row in conn.execute(
                """
                SELECT app_label, package_name, category, foreground_minutes, open_count, last_used_at
                FROM android_app_usage
                WHERE date = ?
                ORDER BY foreground_minutes DESC
                """,
                (latest_date,),
            )
        ]
        top_packages = [app["package_name"] for app in apps[:8]]
        if top_packages:
            placeholders = ",".join("?" for _ in top_packages)
            app_trends = [
                dict(row)
                for row in conn.execute(
                    f"""
                    SELECT date, package_name, app_label, category,
                           SUM(foreground_minutes) AS foreground_minutes,
                           SUM(open_count) AS open_count
                    FROM android_app_usage
                    WHERE package_name IN ({placeholders})
                    GROUP BY date, package_name, app_label, category
                    ORDER BY date, foreground_minutes DESC
                    """,
                    top_packages,
                )
            ]
        else:
            app_trends = []
        app_hourly = [
            dict(row)
            for row in conn.execute(
                """
                SELECT package_name, app_label, category, hour, SUM(foreground_minutes) AS foreground_minutes
                FROM android_app_hourly_usage
                WHERE date = ?
                GROUP BY package_name, app_label, category, hour
                ORDER BY package_name, hour
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
        focus_sessions = [
            dict(row)
            for row in conn.execute(
                """
                SELECT source, title, start_time, end_time, minutes
                FROM focus_sessions
                WHERE date = ?
                ORDER BY COALESCE(start_time, ''), id
                """,
                (latest_date,),
            )
        ]
        output_trends = [
            dict(row)
            for row in conn.execute(
                """
                SELECT date, study_files_modified_count, study_files_created_count,
                       total_study_files_count, study_files_modified_7d_count,
                       r_command_count, focus_minutes, focus_session_count, learning_output_score
                FROM daily_metrics
                ORDER BY date
                """
            )
        ]
        r_summary = conn.execute(
            "SELECT * FROM r_history_summary WHERE date = ? ORDER BY id DESC LIMIT 1",
            (latest_date,),
        ).fetchone()
        review = conn.execute(
            "SELECT review_text, model_name, prompt FROM ai_review WHERE scope = 'daily' ORDER BY generated_at DESC LIMIT 1"
        ).fetchone()
        quality = conn.execute(
            "SELECT * FROM data_quality_report WHERE date = ? LIMIT 1",
            (latest_date,),
        ).fetchone()
        weekly = conn.execute(
            "SELECT * FROM weekly_metrics WHERE week_end = ? ORDER BY generated_at DESC LIMIT 1",
            (latest_date,),
        ).fetchone()
        monthly = conn.execute(
            "SELECT * FROM monthly_metrics WHERE month_end = ? ORDER BY generated_at DESC LIMIT 1",
            (latest_date,),
        ).fetchone()
        return {
            "daily": daily,
            "latest": daily[-1],
            "apps": apps,
            "app_trends": app_trends,
            "app_hourly": app_hourly,
            "files": files,
            "focus_sessions": focus_sessions,
            "output_trends": output_trends,
            "r_summary": dict(r_summary) if r_summary else {},
            "review": dict(review) if review else {},
            "data_quality": dict(quality) if quality else {},
            "weekly": dict(weekly) if weekly else {},
            "monthly": dict(monthly) if monthly else {},
            "pipeline_status": pipeline_status,
        }
    finally:
        conn.close()


def format_minutes(value) -> str:
    minutes = round(float(value or 0))
    hours, rest = divmod(minutes, 60)
    return f"{hours}h {rest}m" if hours else f"{rest}m"


def format_percent(value) -> str:
    return f"{float(value or 0) * 100:.1f}%"


def h(value) -> str:
    return html.escape(str(value if value is not None else ""))


def display_app_name(app: dict) -> str:
    package_name = app.get("package_name") or ""
    app_label = app.get("app_label") or package_name
    return app_label or APP_NAME_MAP.get(package_name) or package_name


def render(payload: dict) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False)
    app_name_map_json = json.dumps(APP_NAME_MAP, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>StudyPulse Interactive</title>
  <style>
    :root {{
      --bg:#f6f7fb; --surface:rgba(255,255,255,.78); --surface-strong:#fff; --text:#171321; --muted:#6f6785;
      --line:rgba(76, 29, 149, .16); --shadow:0 18px 50px rgba(58, 24, 104, .14); --glow:0 0 28px rgba(59,130,246,.18);
      --blue:#3b82f6; --cyan:#06b6d4; --green:#22c55e; --amber:#f59e0b; --orange:#f97316; --red:#ef4444; --purple:#8b5cf6; --pink:#ec4899; --ink:#111827;
    }}
    [data-theme="dark"] {{
      --bg:#0f1020; --surface:rgba(28,28,48,.82); --surface-strong:#1d1b35; --text:#f8fafc; --muted:#a6a1bf;
      --line:rgba(255,255,255,.13); --shadow:0 20px 60px rgba(0,0,0,.35); --glow:0 0 34px rgba(6,182,212,.22);
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; min-height:100vh; color:var(--text); font-family:Inter, Arial, "Microsoft YaHei", sans-serif;
      background:
        linear-gradient(135deg, rgba(139,92,246,.08), transparent 30%),
        linear-gradient(315deg, rgba(6,182,212,.10), transparent 34%),
        repeating-linear-gradient(90deg, rgba(59,130,246,.08) 0 1px, transparent 1px 72px),
        repeating-linear-gradient(0deg, rgba(139,92,246,.07) 0 1px, transparent 1px 72px),
        linear-gradient(135deg, var(--bg), #eef7ff 56%, #fff7ed); }}
    body::before {{ content:""; position:fixed; inset:0; pointer-events:none; opacity:.5;
      background:linear-gradient(180deg, transparent 0%, rgba(59,130,246,.12) 48%, transparent 52%);
      transform:translateY(-100%); animation:scan 7s linear infinite; }}
    body[data-theme="dark"] {{ background:
      linear-gradient(135deg, rgba(139,92,246,.16), transparent 30%),
      linear-gradient(315deg, rgba(6,182,212,.12), transparent 34%),
      repeating-linear-gradient(90deg, rgba(125,211,252,.08) 0 1px, transparent 1px 72px),
      repeating-linear-gradient(0deg, rgba(167,139,250,.08) 0 1px, transparent 1px 72px),
      linear-gradient(135deg, #0f1020, #17172e 60%, #111827); }}
    @keyframes scan {{ to {{ transform:translateY(100%); }} }}
    @keyframes rise {{ from {{ opacity:0; transform:translateY(14px); }} to {{ opacity:1; transform:translateY(0); }} }}
    @keyframes shimmer {{ to {{ transform:translateX(140%); }} }}
    @keyframes pulseRing {{ 50% {{ filter:drop-shadow(0 0 18px rgba(6,182,212,.55)); }} }}
    .app {{ max-width:1240px; margin:0 auto; padding:24px; position:relative; }}
    .command-strip {{ display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:14px; padding:10px 12px; border:1px solid var(--line); border-radius:18px; background:rgba(255,255,255,.56); backdrop-filter:blur(14px); box-shadow:0 12px 32px rgba(15,23,42,.07); }}
    [data-theme="dark"] .command-strip {{ background:rgba(15,23,42,.5); }}
    .command-strip strong {{ font-size:13px; }}
    .command-strip span {{ color:var(--muted); font-size:12px; }}
    .live-dot {{ width:9px; height:9px; border-radius:50%; background:var(--green); box-shadow:0 0 18px var(--green); display:inline-block; margin-right:8px; }}
    .hero {{ display:grid; grid-template-columns:minmax(0,1.2fr) 360px; gap:18px; align-items:stretch; }}
    .hero-main,.hero-side,.card,.panel {{ position:relative; overflow:hidden; }}
    .hero-main::before,.hero-side::before,.card::before,.panel::before {{ content:""; position:absolute; inset:0; pointer-events:none; border-radius:inherit; padding:1px;
      background:linear-gradient(135deg, rgba(59,130,246,.55), rgba(236,72,153,.35), rgba(34,197,94,.28));
      -webkit-mask:linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite:xor; mask-composite:exclude; opacity:.55; }}
    .hero-main::after {{ content:""; position:absolute; top:0; bottom:0; left:-45%; width:32%; background:linear-gradient(90deg, transparent, rgba(255,255,255,.28), transparent); transform:skewX(-18deg); animation:shimmer 8s ease-in-out infinite; }}
    .hero-main {{ border:1px solid var(--line); border-radius:24px; padding:28px; background:var(--surface); box-shadow:var(--shadow), var(--glow); backdrop-filter:blur(18px); animation:rise .55s ease both; }}
    .hero-main h1 {{ margin:0; font-size:38px; letter-spacing:0; }}
    .hero-main p {{ color:var(--muted); line-height:1.7; max-width:720px; }}
    .hero-kicker {{ display:inline-flex; align-items:center; gap:8px; color:var(--muted); font-size:13px; margin-bottom:8px; }}
    .actions {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:18px; }}
    button {{ border:0; border-radius:999px; padding:10px 14px; cursor:pointer; color:var(--text); background:var(--surface-strong); border:1px solid var(--line); font-weight:700; transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease; }}
    button:hover {{ transform:translateY(-1px); box-shadow:0 10px 28px rgba(59,130,246,.18); border-color:rgba(59,130,246,.45); }}
    button.active {{ color:#fff; background:linear-gradient(135deg, var(--purple), var(--pink)); border-color:transparent; }}
    .signal-deck {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-top:18px; }}
    .signal-card {{ border:1px solid var(--line); border-radius:14px; padding:11px; background:rgba(255,255,255,.44); }}
    .signal-card.active {{ box-shadow:0 0 0 2px rgba(6,182,212,.26), 0 0 28px rgba(6,182,212,.22); transform:translateY(-1px); }}
    [data-theme="dark"] .signal-card {{ background:rgba(255,255,255,.06); }}
    .signal-card strong {{ display:block; margin-top:5px; font-size:13px; }}
    .signal-card small {{ color:var(--muted); display:block; min-height:18px; margin-top:3px; }}
    .signal-line {{ height:4px; border-radius:99px; margin-top:10px; background:linear-gradient(90deg,var(--cyan),var(--purple),var(--pink)); background-size:180% 100%; animation:flow 3s linear infinite; }}
    @keyframes flow {{ to {{ background-position:180% 0; }} }}
    .sync-rail {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin-top:14px; }}
    .node {{ position:relative; min-height:72px; border:1px solid var(--line); border-radius:14px; padding:10px; background:rgba(255,255,255,.42); overflow:hidden; transition:.2s ease; }}
    [data-theme="dark"] .node {{ background:rgba(255,255,255,.055); }}
    .node::after {{ content:""; position:absolute; left:10px; right:10px; bottom:8px; height:3px; border-radius:99px; background:linear-gradient(90deg,var(--blue),var(--green),var(--amber),var(--pink)); opacity:.28; }}
    .node.active {{ border-color:rgba(6,182,212,.62); box-shadow:0 0 26px rgba(6,182,212,.18); }}
    .node.active::after {{ opacity:1; }}
    .node small {{ color:var(--muted); display:block; }}
    .node strong {{ display:block; margin-top:5px; }}
    .hero-side {{ border-radius:24px; padding:22px; color:#fff; background:
      linear-gradient(135deg, rgba(17,24,39,.92), rgba(30,41,59,.82)),
      linear-gradient(135deg,#7c3aed,#2563eb 55%,#06b6d4); box-shadow:var(--shadow), 0 0 38px rgba(6,182,212,.24); animation:rise .7s ease both; }}
    .risk-big {{ font-size:68px; font-weight:900; line-height:1; margin:18px 0 4px; }}
    .risk-dial {{ width:180px; height:180px; border-radius:50%; margin:16px auto; display:grid; place-items:center; background:conic-gradient(var(--cyan) 0deg, var(--pink) 210deg, rgba(255,255,255,.18) 210deg 360deg); animation:pulseRing 3s ease-in-out infinite; }}
    .risk-dial::before {{ content:""; width:132px; height:132px; border-radius:50%; background:#111827; box-shadow:inset 0 0 28px rgba(6,182,212,.25); }}
    .risk-dial span {{ position:absolute; font-size:36px; font-weight:900; }}
    .status-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:12px; font-size:12px; }}
    .status-grid div {{ background:rgba(255,255,255,.11); border:1px solid rgba(255,255,255,.16); border-radius:10px; padding:9px; }}
    .grid4 {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-top:18px; }}
    .card,.panel {{ background:var(--surface); border:1px solid var(--line); border-radius:18px; padding:18px; box-shadow:var(--shadow); backdrop-filter:blur(14px); transition:transform .18s ease, box-shadow .18s ease; animation:rise .65s ease both; }}
    .card:hover,.panel:hover {{ transform:translateY(-2px); box-shadow:var(--shadow), var(--glow); }}
    .label {{ color:var(--muted); font-size:13px; }}
    .value {{ font-size:30px; font-weight:900; margin:8px 0; }}
    .delta {{ font-size:12px; color:var(--muted); }}
    .layout {{ display:grid; grid-template-columns:1.1fr .9fr; gap:14px; margin-top:14px; }}
    h2 {{ margin:0 0 14px; font-size:18px; }}
    .chart {{ width:100%; height:260px; display:block; overflow:visible; }}
    .chart-meta {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-top:12px; }}
    .meter-chip {{ border:1px solid var(--line); border-radius:12px; padding:10px; background:rgba(255,255,255,.45); }}
    [data-theme="dark"] .meter-chip {{ background:rgba(255,255,255,.055); }}
    .meter-chip small {{ display:block; color:var(--muted); margin-bottom:4px; }}
    .wide {{ grid-column:1 / -1; }}
    .status-list,.formula-list,.period-grid {{ display:grid; gap:10px; }}
    .status-item,.formula-item,.period-item {{ border:1px solid var(--line); border-radius:12px; padding:12px; background:rgba(255,255,255,.42); }}
    [data-theme="dark"] .status-item,[data-theme="dark"] .formula-item,[data-theme="dark"] .period-item {{ background:rgba(255,255,255,.055); }}
    .status-item strong,.formula-item strong,.period-item strong {{ display:block; margin-bottom:4px; }}
    .status-ok {{ color:#16a34a; }}
    .status-warn {{ color:#d97706; }}
    .status-bad {{ color:#dc2626; }}
    .formula {{ font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:12px; color:var(--muted); margin-top:4px; }}
    .radar {{ width:100%; min-height:230px; display:grid; place-items:center; }}
    .radar svg {{ width:min(260px,100%); height:230px; overflow:visible; }}
    .bars {{ display:grid; gap:12px; }}
    .bar-head {{ display:flex; justify-content:space-between; font-size:13px; margin-bottom:7px; }}
    .track {{ height:12px; background:rgba(148,163,184,.22); border-radius:99px; overflow:hidden; }}
    .track span {{ display:block; height:100%; border-radius:99px; transition:width .35s ease; box-shadow:0 0 16px currentColor; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th,td {{ padding:11px 8px; border-bottom:1px solid var(--line); text-align:left; }}
    th {{ color:var(--muted); font-weight:800; }}
    tbody tr {{ transition:background .16s ease, transform .16s ease; }}
    tbody tr:hover {{ background:rgba(59,130,246,.08); }}
    .table-wrap {{ max-height:430px; overflow:auto; border:1px solid var(--line); border-radius:14px; }}
    .table-wrap table th {{ position:sticky; top:0; background:var(--surface-strong); z-index:2; }}
    [data-theme="dark"] .table-wrap table th {{ background:#1d1b35; }}
    .tabs,.chips {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px; }}
    .chip {{ border-radius:999px; padding:7px 11px; background:var(--surface-strong); border:1px solid var(--line); font-size:12px; cursor:pointer; }}
    .chip.active {{ background:#111827; color:#fff; border-color:#111827; }}
    [data-theme="dark"] .chip.active {{ background:#fff; color:#111827; border-color:#fff; }}
    .insight {{ line-height:1.75; font-size:14px; border-left:5px solid var(--purple); background:rgba(139,92,246,.09); padding:14px; border-radius:12px; }}
    .ai-review {{ display:grid; gap:14px; border-left:0; background:transparent; padding:0; font-size:15px; line-height:1.85; }}
    .ai-section {{ border:1px solid var(--line); border-left:5px solid var(--purple); background:rgba(139,92,246,.08); border-radius:14px; padding:14px 16px; }}
    .ai-section h3 {{ margin:0 0 10px; font-size:17px; line-height:1.35; }}
    .ai-section p {{ margin:8px 0; color:var(--text); }}
    .ai-section ol {{ margin:8px 0 0; padding-left:24px; }}
    .ai-section li {{ margin:8px 0; padding-left:2px; }}
    .ai-section strong {{ font-weight:900; color:var(--text); }}
    pre {{ margin:0; white-space:pre-wrap; max-height:250px; overflow:auto; background:#111827; color:#e5e7eb; padding:14px; border-radius:14px; font-size:12px; }}
    .kv {{ display:flex; justify-content:space-between; gap:10px; padding:10px 0; border-bottom:1px solid var(--line); }}
    .detail {{ min-height:210px; }}
    .detail-title {{ font-size:24px; font-weight:900; margin:8px 0; }}
    .detail-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:12px; }}
    .detail-grid div {{ border:1px solid var(--line); border-radius:12px; padding:10px; background:rgba(255,255,255,.36); }}
    [data-theme="dark"] .detail-grid div {{ background:rgba(255,255,255,.055); }}
    .pill {{ display:inline-flex; border:1px solid var(--line); border-radius:999px; padding:5px 9px; font-size:12px; font-weight:800; }}
    .heat {{ display:grid; grid-template-columns:repeat(24,1fr); gap:3px; margin-top:12px; }}
    .heat span {{ height:34px; border-radius:7px; background:rgba(148,163,184,.16); }}
    .heat span.hot {{ background:linear-gradient(180deg,var(--pink),var(--orange)); box-shadow:0 0 14px rgba(236,72,153,.28); }}
    .hidden {{ display:none; }}
    .foot {{ color:var(--muted); font-size:12px; margin-top:18px; }}
    #toast {{ position:fixed; right:22px; bottom:22px; background:#111827; color:#fff; border:1px solid rgba(255,255,255,.16); border-radius:14px; padding:12px 14px; box-shadow:0 18px 50px rgba(0,0,0,.25); opacity:0; transform:translateY(12px); pointer-events:none; transition:.2s ease; z-index:20; }}
    #toast.show {{ opacity:1; transform:translateY(0); }}
    @media(max-width:940px) {{ .hero,.layout,.grid4,.chart-meta {{ grid-template-columns:1fr; }} .hero-main h1 {{ font-size:30px; }} }}
    @media(max-width:720px) {{ .signal-deck,.sync-rail,.detail-grid {{ grid-template-columns:1fr 1fr; }} .command-strip {{ align-items:flex-start; flex-direction:column; }} .risk-dial {{ width:150px; height:150px; }} .risk-dial::before {{ width:110px; height:110px; }} }}
  </style>
</head>
<body>
<script>document.body.dataset.theme = localStorage.getItem("sp-theme") || "light";</script>
<div class="app">
  <div class="command-strip">
    <strong><span class="live-dot"></span>StudyPulse Control Center</strong>
    <span id="runStatus">等待本地数据渲染</span>
  </div>
  <section class="hero">
    <div class="hero-main">
      <div class="hero-kicker"><span class="live-dot"></span><span>Android + Windows + RStudio + MiMo</span></div>
      <h1>把一天的学习行为变成可追踪、可解释、可演示的个人信号台</h1>
      <p>页面直接消费本地 SQLite 聚合数据，将手机使用、Windows 文件痕迹、RStudio 活动和 MiMo 复盘串成一条可交互数据链路。</p>
      <div class="signal-deck">
        <div class="signal-card" data-source="phone"><span class="label">PHONE</span><strong>Usage Stream</strong><small id="phonePulse">--</small><div class="signal-line"></div></div>
        <div class="signal-card" data-source="windows"><span class="label">WINDOWS</span><strong>File Trace</strong><small id="windowsPulse">--</small><div class="signal-line"></div></div>
        <div class="signal-card" data-source="rstudio"><span class="label">RSTUDIO</span><strong>Command Pulse</strong><small id="rstudioPulse">--</small><div class="signal-line"></div></div>
        <div class="signal-card" data-source="mimo"><span class="label">MIMO</span><strong>AI Review</strong><small id="mimoPulse">--</small><div class="signal-line"></div></div>
      </div>
      <div class="sync-rail">
        <div class="node active" data-node="phone"><small>01 Collect</small><strong>手机使用聚合</strong></div>
        <div class="node" data-node="windows"><small>02 Detect</small><strong>Windows 学习记录</strong></div>
        <div class="node" data-node="rstudio"><small>03 Parse</small><strong>R 学习命令</strong></div>
        <div class="node" data-node="mimo"><small>04 Review</small><strong>AI 每日复盘</strong></div>
      </div>
      <div class="actions">
        <button class="active" data-tab="overview">总览</button>
        <button data-tab="apps">App 分析</button>
        <button data-tab="output">Windows 学习</button>
        <button data-tab="ai">AI 复盘</button>
        <button id="themeBtn">切换主题</button>
      </div>
    </div>
    <div class="hero-side">
      <div>今日分心风险</div>
      <div class="risk-dial" id="riskDial"><span id="riskDialValue">--</span></div>
      <div id="riskText">--</div>
      <div class="status-grid">
        <div>Local DB<br><strong>ONLINE</strong></div>
        <div>Privacy<br><strong>AGGREGATED</strong></div>
        <div>Android<br><strong>READY</strong></div>
        <div>Report<br><strong>LIVE</strong></div>
      </div>
    </div>
  </section>

  <section class="grid4" id="kpis"></section>

  <section class="layout tab-page" id="tab-overview">
    <div class="panel">
      <div class="tabs">
        <span class="chip active" data-metric="learning_input_score">学习情况</span>
        <span class="chip" data-metric="learning_output_score">Windows 学习</span>
        <span class="chip" data-metric="distraction_risk_score">分心风险</span>
        <span class="chip" data-metric="r_activity_score">R 活跃度</span>
      </div>
      <h2 id="chartTitle">学习情况趋势</h2>
      <svg id="trendChart" class="chart" viewBox="0 0 760 260"></svg>
      <div class="chart-meta" id="metricMeta"></div>
    </div>
    <div class="panel">
      <h2>今日时间结构</h2>
      <div class="radar" id="categoryRadar"></div>
      <div class="bars" id="categoryBars"></div>
    </div>
    <div class="panel wide">
      <h2>数据可信度与自动化状态</h2>
      <div class="status-list" id="qualityStatus"></div>
    </div>
    <div class="panel wide">
      <h2>指标解释与计算公式</h2>
      <div class="formula-list" id="formulaList"></div>
    </div>
    <div class="panel wide">
      <h2>周报 / 月报产品设计</h2>
      <div class="period-grid" id="periodPlan"></div>
    </div>
  </section>

  <section class="layout tab-page hidden" id="tab-apps">
    <div class="panel">
      <h2>App 分类筛选</h2>
      <div class="chips" id="categoryFilters"></div>
      <div class="table-wrap"><table><thead><tr><th>App</th><th>分类</th><th><button id="sortTime">时长</button></th><th><button id="sortOpen">打开</button></th></tr></thead><tbody id="appTable"></tbody></table></div>
    </div>
    <div class="panel">
      <h2>App 详情</h2>
      <div class="detail" id="appDetail"></div>
    </div>
    <div class="panel">
      <h2>所选 App 使用时间段</h2>
      <svg id="appHourlyChart" class="chart" viewBox="0 0 760 260"></svg>
      <div class="chart-meta" id="appHourlyMeta"></div>
    </div>
    <div class="panel">
      <h2>Top App 多日趋势</h2>
      <svg id="appTrendChart" class="chart" viewBox="0 0 760 260"></svg>
      <div class="chart-meta" id="appTrendMeta"></div>
    </div>
  </section>

  <section class="layout tab-page hidden" id="tab-output">
    <div class="panel">
      <h2>Windows 学习文件活动</h2>
      <div class="table-wrap"><table><thead><tr><th>扩展名</th><th>活动</th><th>数量</th></tr></thead><tbody id="fileTable"></tbody></table></div>
      <div class="heat" id="evidenceHeat"></div>
    </div>
    <div class="panel">
      <h2>RStudio / R 学习痕迹</h2>
      <div id="rSummary"></div>
    </div>
    <div class="panel wide" id="focusSessions"></div>
    <div class="panel wide">
      <h2>Windows 学习多日趋势</h2>
      <svg id="outputTrendChart" class="chart" viewBox="0 0 760 260"></svg>
      <div class="chart-meta" id="outputTrendMeta"></div>
    </div>
  </section>

  <section class="layout tab-page hidden" id="tab-ai">
    <div class="panel">
      <h2>MiMo 复盘建议</h2>
      <div class="ai-review" id="aiReview"></div>
    </div>
    <div class="panel">
      <h2>聚合指标 Prompt</h2>
      <pre id="promptBox"></pre>
    </div>
  </section>
  <div class="foot">Privacy by design: only aggregated metrics are rendered in this product page.</div>
</div>
<div id="toast"></div>
<script>
const payload = {payload_json};
const appNameMap = {app_name_map_json};
const colors = {{study:"#3b82f6", tool:"#22c55e", social:"#a855f7", entertainment:"#f97316", game:"#ef4444", other:"#64748b"}};
const labels = {{learning_input_score:"学习情况趋势", learning_output_score:"Windows 学习趋势", distraction_risk_score:"分心风险趋势", r_activity_score:"R 活跃度趋势"}};
const categoryNames = {{all:"全部", study:"学习", tool:"工具", social:"社交", entertainment:"娱乐", game:"游戏", other:"其他"}};
const metricMeta = {{
  learning_input_score:[["含义","学习 App 时长、工具使用、R 活动和 Windows 学习记录共同形成的学习情况"],["适合观察","今天是否把主要行为投入到学习对象上"],["风险","只代表过程强度，不直接等同掌握程度"]],
  learning_output_score:[["含义","Windows 文件和 R 命令形成的学习记录信号"],["适合观察","R 语言、统计作业等学习过程是否留下可复查的脚本、笔记或文件"],["风险","这不是最终结果或掌握程度指标，未保存文件会被低估"]],
  distraction_risk_score:[["含义","娱乐、社交、游戏相对总使用的压力"],["适合观察","学习前后是否被高刺激应用吞掉"],["风险","必要社交可能被误判"]],
  r_activity_score:[["含义","RStudio/R 相关操作的活跃程度"],["适合观察","统计作业是否进入实际代码阶段"],["风险","只看命令数量不看代码质量"]],
}};
const metricFormulas = [
  ["手机总使用", "今日所有 App 使用时长求和；番茄 ToDo 使用截图识别后的专注时长修正", "phone_total_minutes = Σ corrected_app.foreground_minutes"],
  ["学习 App", "被分类为 study 的 App 使用时长；番茄 ToDo 已作为普通学习 App 计入", "study_app_minutes = Σ corrected_app.foreground_minutes where category = study"],
  ["番茄 ToDo 修正", "系统未能正确读取番茄 ToDo 后台专注过程时，用截图识别结果覆盖该 App 时长", "tomato_todo.foreground_minutes = focus_minutes"],
  ["分心 App", "娱乐、游戏、社交类 App 使用时长合计", "distracting_app_minutes = entertainment + game + social"],
  ["分心占比", "分心 App 时长占手机总使用时长比例", "distracting_ratio = distracting_app_minutes / phone_total_minutes"],
  ["学习情况分", "学习 App 统计为主，Windows 学习记录作为 R/作业过程的辅助信号，最高 100", "learning_input_score = min(100, study_app_minutes*0.22 + tool_app_minutes*0.08 + r_command_count*0.25 + learning_output_score*0.25)"],
  ["Windows 学习记录分", "Windows 学习文件修改、新建、R 命令形成的过程记录信号，最高 100", "learning_output_score = min(100, file_signal + r_signal)"],
  ["分心风险分", "分心占比和高频切换共同推高风险，最高 100", "distraction_risk_score = min(100, distracting_ratio * 100 + switch_penalty)"],
  ["R 活跃度", "R 命令、可视化、建模操作的活跃程度", "r_activity_score = weighted(command_count, visualization_count, modeling_count)"]
];
let appSort = "time";
let appCategory = "all";

function mins(v) {{ const m=Math.round(Number(v||0)); const h=Math.floor(m/60); const r=m%60; return h ? `${{h}}h ${{r}}m` : `${{r}}m`; }}
function pct(v) {{ return `${{(Number(v||0)*100).toFixed(1)}}%`; }}
function esc(s) {{ return String(s ?? "").replace(/[&<>"']/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c])); }}
function reviewInline(s) {{
  return esc(s).replace(/\\*\\*(.+?)\\*\\*/g, "<strong>$1</strong>");
}}
function normalizeReviewText(text) {{
  return String(text || "")
    .replace(/\\r/g, "")
    .replace(/\\s+(#{{1,3}}\\s+)/g, "\\n$1")
    .replace(/\\s+(\\d+\\.\\s+)/g, "\\n$1")
    .replace(/\\s+(\\*\\*[^*]+?\\*\\*)/g, "\\n$1")
    .replace(/\\n{{3,}}/g, "\\n\\n")
    .trim();
}}
function alignOriginalSummary(lines) {{
  const result = [];
  let inOriginal = false;
  let originalIndex = 0;
  const originalTitles = new Set(["今日概况", "主要风险", "明日建议"]);
  const plainText = line => line.replace(/\\*\\*/g, "").replace(/^[-*]\\s*/, "").trim();
  for (let i = 0; i < lines.length; i++) {{
    const line = lines[i];
    const plain = plainText(line);
    if (/^(一、|一[.．、])\\s*原有总结/.test(plain)) {{
      inOriginal = true;
      originalIndex = 0;
      result.push("## " + plain);
      continue;
    }}
    if (/^(二、|二[.．、])\\s*行动化补充/.test(plain)) {{
      inOriginal = false;
      result.push("## " + plain);
      continue;
    }}
    if (inOriginal && plain === "") continue;
    if (inOriginal && originalTitles.has(plain)) {{
      const nextPlain = lines[i + 1] ? plainText(lines[i + 1]) : "";
      const body = nextPlain && !originalTitles.has(nextPlain) && !/^(二、|二[.．、])/.test(nextPlain) ? lines[++i] : "";
      originalIndex += 1;
      result.push(`${{originalIndex}}. **${{plain}}**${{body ? "：" + body : ""}}`);
      continue;
    }}
    if (plain === "*") continue;
    result.push(line);
  }}
  return result;
}}
function renderReviewText(text) {{
  const normalized = normalizeReviewText(text);
  if (!normalized) return `<div class="ai-section"><p>MiMo API 尚未配置，当前显示 prompt-only 复盘占位。</p></div>`;
  const rawLines = normalized.split("\\n").map(x => x.trim()).filter(Boolean);
  const lines = [];
  for (let i = 0; i < rawLines.length; i++) {{
    if (/^\\d+\\.$/.test(rawLines[i]) && rawLines[i + 1]) {{
      lines.push(`${{rawLines[i]}} ${{rawLines[i + 1]}}`);
      i++;
    }} else {{
      lines.push(rawLines[i]);
    }}
  }}
  const alignedLines = alignOriginalSummary(lines);
  let html = "";
  let openList = false;
  let sectionOpen = false;
  const closeList = () => {{ if (openList) {{ html += "</ol>"; openList = false; }} }};
  const closeSection = () => {{ closeList(); if (sectionOpen) {{ html += "</div>"; sectionOpen = false; }} }};
  const openSection = title => {{
    closeSection();
    html += `<div class="ai-section"><h3>${{reviewInline(title)}}</h3>`;
    sectionOpen = true;
  }};
  for (const line of alignedLines) {{
    if (/^-{{3,}}$/.test(line)) continue;
    const heading = line.match(/^#{{1,3}}\\s*(.+)$/);
    if (heading) {{
      openSection(heading[1]);
      continue;
    }}
    if (!sectionOpen) openSection("MiMo 复盘建议");
    const numbered = line.match(/^\\d+\\.\\s*(.+)$/);
    if (numbered) {{
      if (!openList) {{ html += "<ol>"; openList = true; }}
      html += `<li>${{reviewInline(numbered[1])}}</li>`;
      continue;
    }}
    closeList();
    html += `<p>${{reviewInline(line)}}</p>`;
  }}
  closeSection();
  return html;
}}
function latest() {{ return payload.latest; }}
function appDisplayName(app) {{ return app.app_label || appNameMap[app.package_name] || appNameMap[app.app_label] || app.package_name || "未知 App"; }}
function toast(message) {{
  const box = document.getElementById("toast");
  box.textContent = message;
  box.classList.add("show");
  clearTimeout(box._timer);
  box._timer = setTimeout(() => box.classList.remove("show"), 1800);
}}

function chartMax(values, floor=1) {{
  const raw = Math.max(floor, ...values.map(v => Number(v || 0)));
  const step = raw <= 10 ? 2 : raw <= 60 ? 10 : raw <= 180 ? 30 : 60;
  return Math.ceil(raw / step) * step;
}}

function drawLineChart(svgId, rows, options) {{
  const svg = document.getElementById(svgId);
  if (!svg) return;
  const unit = options.unit || "";
  const labelEvery = options.labelEvery || 1;
  if (!rows || rows.length === 0) {{
    svg.innerHTML = `<text x="380" y="130" text-anchor="middle" fill="currentColor" opacity=".55">No data</text>`;
    return;
  }}
  const values = rows.map(r => Number(r.value || 0));
  const max = options.max ?? chartMax(values, 100);
  const min = 0;
  const w=760,h=260,l=64,r=26,t=24,b=50,pw=w-l-r,ph=h-t-b;
  const yTicks = [0, .25, .5, .75, 1].map(x => max * x);
  const pts = rows.map((row,idx) => {{
    const x = l + pw * idx / Math.max(rows.length-1,1);
    const y = t + ph - (Number(row.value || 0)-min)/(max-min || 1)*ph;
    return [x,y,Number(row.value || 0),row.label];
  }});
  const line = pts.map(p => `${{p[0].toFixed(1)}},${{p[1].toFixed(1)}}`).join(" ");
  const area = `${{l}},${{t+ph}} ${{line}} ${{w-r}},${{t+ph}}`;
  const grid = yTicks.map(v => {{
    const y = t + ph - (v-min)/(max-min || 1)*ph;
    return `<line x1="${{l}}" y1="${{y}}" x2="${{w-r}}" y2="${{y}}" stroke="currentColor" opacity=".10"/><text x="${{l-10}}" y="${{y+4}}" text-anchor="end" fill="currentColor" opacity=".62" font-size="12">${{v.toFixed(v < 10 ? 1 : 0)}}${{unit}}</text>`;
  }}).join("");
  const xLabels = pts.map((p,idx) => idx % labelEvery === 0 || idx === pts.length-1 ? `<text x="${{p[0]}}" y="${{h-18}}" text-anchor="middle" fill="currentColor" opacity=".68" font-size="12">${{esc(p[3])}}</text>` : "").join("");
  svg.innerHTML = `<defs><linearGradient id="${{svgId}}Fill" x1="0" x2="1"><stop offset="0" stop-color="#06b6d4"/><stop offset=".52" stop-color="#8b5cf6"/><stop offset="1" stop-color="#ec4899"/></linearGradient></defs>${{grid}}<line x1="${{l}}" y1="${{t}}" x2="${{l}}" y2="${{t+ph}}" stroke="currentColor" opacity=".18"/><line x1="${{l}}" y1="${{t+ph}}" x2="${{w-r}}" y2="${{t+ph}}" stroke="currentColor" opacity=".18"/><text x="${{l}}" y="14" fill="currentColor" opacity=".68" font-size="12">${{esc(options.yLabel || "")}}</text><polygon points="${{area}}" fill="url(#${{svgId}}Fill)" opacity=".13"></polygon><polyline points="${{line}}" fill="none" stroke="url(#${{svgId}}Fill)" stroke-width="4"></polyline>${{pts.map(p => `<circle cx="${{p[0]}}" cy="${{p[1]}}" r="5" fill="#ec4899"><title>${{esc(p[3])}} ${{p[2].toFixed(1)}}${{unit}}</title></circle>`).join("")}}${{xLabels}}`;
}}

function drawBarChart(svgId, rows, options) {{
  const svg = document.getElementById(svgId);
  if (!svg) return;
  const unit = options.unit || "";
  if (!rows || rows.length === 0) {{
    svg.innerHTML = `<text x="380" y="130" text-anchor="middle" fill="currentColor" opacity=".55">No data</text>`;
    return;
  }}
  const values = rows.map(r => Number(r.value || 0));
  const max = chartMax(values, 1);
  const w=760,h=260,l=64,r=26,t=24,b=50,pw=w-l-r,ph=h-t-b;
  const yTicks = [0, .25, .5, .75, 1].map(x => max * x);
  const barW = Math.max(5, pw / rows.length * .62);
  const grid = yTicks.map(v => {{
    const y = t + ph - v/max*ph;
    return `<line x1="${{l}}" y1="${{y}}" x2="${{w-r}}" y2="${{y}}" stroke="currentColor" opacity=".10"/><text x="${{l-10}}" y="${{y+4}}" text-anchor="end" fill="currentColor" opacity=".62" font-size="12">${{v.toFixed(v < 10 ? 1 : 0)}}${{unit}}</text>`;
  }}).join("");
  const bars = rows.map((row,idx) => {{
    const x = l + pw * (idx + .5) / rows.length - barW/2;
    const bh = Number(row.value || 0) / max * ph;
    const y = t + ph - bh;
    const label = idx % 3 === 0 || idx === rows.length-1 ? `<text x="${{x+barW/2}}" y="${{h-18}}" text-anchor="middle" fill="currentColor" opacity=".68" font-size="11">${{esc(row.label)}}</text>` : "";
    return `<rect x="${{x}}" y="${{y}}" width="${{barW}}" height="${{bh}}" rx="4" fill="${{options.color || '#3b82f6'}}"><title>${{esc(row.label)}} ${{Number(row.value || 0).toFixed(1)}}${{unit}}</title></rect>${{label}}`;
  }}).join("");
  svg.innerHTML = `${{grid}}<line x1="${{l}}" y1="${{t}}" x2="${{l}}" y2="${{t+ph}}" stroke="currentColor" opacity=".18"/><line x1="${{l}}" y1="${{t+ph}}" x2="${{w-r}}" y2="${{t+ph}}" stroke="currentColor" opacity=".18"/><text x="${{l}}" y="14" fill="currentColor" opacity=".68" font-size="12">${{esc(options.yLabel || "")}}</text>${{bars}}`;
}}

function setActiveSource(source) {{
  document.querySelectorAll("[data-source],[data-node]").forEach(el => el.classList.remove("active"));
  document.querySelectorAll(`[data-source="${{source}}"],[data-node="${{source}}"]`).forEach(el => el.classList.add("active"));
}}

function renderSourceDeck() {{
  const l = latest();
  const r = payload.r_summary || {{}};
  document.getElementById("phonePulse").textContent = `${{mins(l.phone_total_minutes)}} captured`;
  document.getElementById("windowsPulse").textContent = `${{payload.files.length}} file signals`;
  document.getElementById("rstudioPulse").textContent = `${{Number(r.command_count || 0)}} commands`;
  document.getElementById("mimoPulse").textContent = payload.review.model_name || "prompt ready";
  document.getElementById("runStatus").textContent = `已载入 ${{payload.latest.date}} 的聚合数据，App ${{payload.apps.length}} 个，文件信号 ${{payload.files.length}} 条`;
}}

function setRiskDial(value) {{
  const degrees = Math.min(360, Math.max(0, Number(value || 0) / 100 * 360));
  const dial = document.getElementById("riskDial");
  document.getElementById("riskDialValue").textContent = Number(value || 0).toFixed(1);
  dial.style.background = `conic-gradient(#06b6d4 0deg, #8b5cf6 ${{degrees * .55}}deg, #ec4899 ${{degrees}}deg, rgba(255,255,255,.18) ${{degrees}}deg 360deg)`;
}}

function renderKpis() {{
  const l = latest();
  const items = [
    ["手机总使用", mins(l.phone_total_minutes), "今日数字行为总量"],
    ["学习 App", mins(l.study_app_minutes), `含番茄 ToDo ${{mins(l.focus_minutes || 0)}}`],
    ["Windows 学习", Number(l.learning_output_score).toFixed(1), "文件 + R 记录"],
    ["分心风险", Number(l.distraction_risk_score).toFixed(1), `分心占比 ${{pct(l.distracting_ratio)}}`],
  ];
  document.getElementById("kpis").innerHTML = items.map(x => `<div class="card"><div class="label">${{x[0]}}</div><div class="value">${{x[1]}}</div><div class="delta">${{x[2]}}</div></div>`).join("");
  setRiskDial(l.distraction_risk_score);
  document.getElementById("riskText").textContent = `分心类 App 占比 ${{pct(l.distracting_ratio)}}`;
  renderSourceDeck();
}}

function renderMetricMeta(metric) {{
  document.getElementById("metricMeta").innerHTML = metricMeta[metric].map(x => `<div class="meter-chip"><small>${{x[0]}}</small><strong>${{x[1]}}</strong></div>`).join("");
}}

function statusClass(level) {{
  return level === "ok" ? "status-ok" : level === "bad" ? "status-bad" : "status-warn";
}}

function renderQualityStatus() {{
  const q = payload.data_quality || {{}};
  const l = latest();
  const review = payload.review || {{}};
  const pipeline = payload.pipeline_status || {{}};
  const steps = pipeline.steps || {{}};
  const adb = pipeline.adb_sync || steps.adb_sync?.detail || {{}};
  const methodOk = q.collection_method === "usage_events_session_rebuild";
  const unknown = Number(q.unknown_app_count || 0);
  const rawRows = Number(q.raw_app_rows || 0);
  const aggregatedRows = Number(q.aggregated_app_rows || 0);
  const sourceTime = q.android_generated_at || "未知";
  const aiFailed = String(review.review_text || "").includes("API 调用失败") || String(review.review_text || "").includes("URLError");
  const items = [
    [methodOk ? "ok" : "warn", "手机采集口径", methodOk ? "已使用 UsageEvents 会话重建，可按单次前台会话还原 App 使用时长。" : "当前采集口径不是 UsageEvents 会话重建，App 时长解释需谨慎。", `collection_method = ${{q.collection_method || "unknown"}}`],
    [rawRows > 0 ? "ok" : "bad", "手机数据新鲜度", `Android JSON 生成时间：${{sourceTime}}。当前日报日期：${{l.date || "未知"}}。`, `raw_app_rows = ${{rawRows}}, aggregated_app_rows = ${{aggregatedRows}}`],
    [unknown === 0 ? "ok" : unknown <= 5 ? "warn" : "bad", "App 分类质量", unknown === 0 ? "没有未知 App。" : `仍有 ${{unknown}} 个未知 App，会影响学习/分心分类精度。`, `unknown_app_count = ${{unknown}}`],
    [Number(q.suspicious_app_count || 0) === 0 ? "ok" : "warn", "异常数据检测", `可疑 App 行数：${{q.suspicious_app_count || 0}}。重复包名数：${{q.duplicate_package_count || 0}}。`, "用于发现重复导入、异常时长或系统组件污染。"],
    [adb.status === "success" ? "ok" : adb.status === "failed" ? "warn" : "warn", "ADB 自动拉取", adb.message ? `最近状态：${{adb.status || "unknown"}}；${{adb.message}}。` : "尚未记录 ADB 同步状态。", `updated_at=${{adb.updated_at || "未记录"}}；local_path=${{adb.local_path || "未生成"}}`],
    [aiFailed ? "warn" : "ok", "MiMo 复盘状态", aiFailed ? "AI 接口调用失败，页面保留 prompt 或上一次错误说明，日报流程未中断。" : `AI 复盘已生成，模型：${{review.model_name || "未知"}}。`, aiFailed ? "降级输出已启用" : "review_text 可用"],
    ["ok", "报告生成状态", `HTML 已基于本地 SQLite 聚合数据生成。数据库生成时间：${{l.generated_at || "未知"}}。`, "手机 JSON -> SQLite -> HTML -> 邮件附件"],
    [pipeline.status === "completed" ? "ok" : pipeline.status === "failed" ? "bad" : "warn", "自动化流水线", pipeline.started_at ? `最近运行：${{pipeline.started_at}} 至 ${{pipeline.finished_at || "未完成"}}，状态：${{pipeline.status || "unknown"}}。` : "尚未发现 pipeline_status.json，说明还没有通过 run_pipeline.py 记录完整流水线。", `JSON=${{pipeline.selected_android_json || "未记录"}}；邮件=${{steps.send_email?.status || "未记录"}}`]
  ];
  document.getElementById("qualityStatus").innerHTML = items.map(item => `<div class="status-item"><strong class="${{statusClass(item[0])}}">${{esc(item[1])}}</strong><div>${{esc(item[2])}}</div><div class="formula">${{esc(item[3])}}</div></div>`).join("");
}}

function renderFormulaList() {{
  document.getElementById("formulaList").innerHTML = metricFormulas.map(item => `<div class="formula-item"><strong>${{esc(item[0])}}</strong><div>${{esc(item[1])}}</div><div class="formula">${{esc(item[2])}}</div></div>`).join("");
}}

function renderPeriodPlan() {{
  const w = payload.weekly || {{}};
  const m = payload.monthly || {{}};
  const dataDays = Number(w.data_days_count || m.data_days_count || payload.daily.length || 0);
  const weeklyReady = dataDays >= 7 && !Number(w.is_partial_week || 0);
  const monthlyReady = Number(m.data_days_count || 0) >= 21;
  const items = [
    ["周报状态", weeklyReady ? "可正式输出" : "早期趋势", weeklyReady ? `本周 ${{w.week_start}} 至 ${{w.week_end}} 数据完整。` : `当前周数据 ${{w.data_days_count || dataDays}} 天，不足完整周时用模拟/历史样例辅助展示。`, `周均学习情况=${{Number(w.avg_learning_input_score || 0).toFixed(1)}}，周均分心风险=${{Number(w.avg_distraction_risk_score || 0).toFixed(1)}}`],
    ["月报状态", monthlyReady ? "可正式输出" : "设计先行", monthlyReady ? `本月已有 ${{m.data_days_count}} 天数据，可做稳定月报。` : `当前月度样本 ${{m.data_days_count || dataDays}} 天，适合先展示结构与趋势解释。`, `月均 Windows 学习记录=${{Number(m.avg_learning_output_score || 0).toFixed(1)}}，风险日=${{m.risk_day || "待积累"}}`],
    ["周报应回答的问题", "产品设计", "这一周学习是否连续？分心风险是否集中在某几天？Windows/R 学习记录是否跟上？", "输出：最佳日、风险日、连续性、下周最小行动"],
    ["月报应回答的问题", "产品设计", "这个月是否形成稳定学习节奏？分心是否周期性反弹？Windows 学习记录是否可复查？", "输出：趋势拐点、稳定性、长期风险、下月策略"]
  ];
  document.getElementById("periodPlan").innerHTML = items.map(item => `<div class="period-item"><strong>${{esc(item[0])}} · ${{esc(item[1])}}</strong><div>${{esc(item[2])}}</div><div class="formula">${{esc(item[3])}}</div></div>`).join("");
}}

function renderTrend(metric) {{
  document.getElementById("chartTitle").textContent = labels[metric];
  const rows = payload.daily.map(d => ({{label:d.date.slice(5), value:Number(d[metric] || 0)}}));
  drawLineChart("trendChart", rows, {{unit:"", yLabel:"score / index", max:100}});
  renderMetricMeta(metric);
}}

function renderCategoryBars() {{
  const l = latest();
  const rows = [
    ["study","学习",l.study_app_minutes], ["tool","工具",l.tool_app_minutes], ["social","社交",l.social_app_minutes],
    ["entertainment","娱乐",Number(l.entertainment_app_minutes || 0) + Number(l.game_app_minutes || 0)]
  ];
  const max = Math.max(...rows.map(r=>Number(r[2])), 1);
  document.getElementById("categoryBars").innerHTML = rows.map(r => `<div><div class="bar-head"><span>${{r[1]}}</span><strong>${{mins(r[2])}}</strong></div><div class="track"><span style="width:${{Number(r[2])/max*100}}%;background:${{colors[r[0]]}}"></span></div></div>`).join("");
  renderCategoryRadar(rows, max);
}}

function renderCategoryRadar(rows, max) {{
  const cx=130, cy=112, radius=82;
  const points = rows.map((r,idx) => {{
    const angle = (-90 + idx * 360 / rows.length) * Math.PI / 180;
    const ratio = Number(r[2] || 0) / max;
    return [cx + Math.cos(angle) * radius * ratio, cy + Math.sin(angle) * radius * ratio, r[1], r[0]];
  }});
  const axis = rows.map((r,idx) => {{
    const angle = (-90 + idx * 360 / rows.length) * Math.PI / 180;
    const x = cx + Math.cos(angle) * radius;
    const y = cy + Math.sin(angle) * radius;
    const lx = cx + Math.cos(angle) * (radius + 23);
    const ly = cy + Math.sin(angle) * (radius + 23);
    return `<line x1="${{cx}}" y1="${{cy}}" x2="${{x}}" y2="${{y}}" stroke="currentColor" opacity=".14"/><text x="${{lx}}" y="${{ly}}" text-anchor="middle" dominant-baseline="middle" fill="currentColor" font-size="12">${{r[1]}}</text>`;
  }}).join("");
  document.getElementById("categoryRadar").innerHTML = `<svg viewBox="0 0 260 230"><circle cx="${{cx}}" cy="${{cy}}" r="${{radius}}" fill="none" stroke="currentColor" opacity=".14"/><circle cx="${{cx}}" cy="${{cy}}" r="${{radius*.62}}" fill="none" stroke="currentColor" opacity=".1"/>${{axis}}<polygon points="${{points.map(p=>`${{p[0]}},${{p[1]}}`).join(" ")}}" fill="#06b6d4" opacity=".17" stroke="#06b6d4" stroke-width="3"/>${{points.map(p=>`<circle cx="${{p[0]}}" cy="${{p[1]}}" r="5" fill="${{colors[p[3]]}}"></circle>`).join("")}}</svg>`;
}}

function renderFilters() {{
  const cats = ["all", ...new Set(payload.apps.map(a => a.category || "other"))];
  document.getElementById("categoryFilters").innerHTML = cats.map(c => `<span class="chip ${{c===appCategory?"active":""}}" data-cat="${{c}}">${{categoryNames[c] || c}}</span>`).join("");
  document.querySelectorAll("[data-cat]").forEach(el => el.onclick = () => {{ appCategory = el.dataset.cat; renderFilters(); renderApps(); toast(`已筛选：${{el.textContent}}`); }});
}}

function renderApps() {{
  let rows = payload.apps.slice();
  if (appCategory !== "all") rows = rows.filter(a => (a.category || "other") === appCategory);
  rows.sort((a,b) => appSort === "open" ? Number(b.open_count)-Number(a.open_count) : Number(b.foreground_minutes)-Number(a.foreground_minutes));
  document.getElementById("appTable").innerHTML = rows.map((a,idx) => `<tr data-app-index="${{idx}}"><td>${{esc(appDisplayName(a))}}</td><td><span class="pill" style="color:${{colors[a.category]||colors.other}}">${{categoryNames[a.category] || a.category || "其他"}}</span></td><td>${{mins(a.foreground_minutes)}}</td><td>${{a.open_count}}</td></tr>`).join("");
  document.querySelectorAll("[data-app-index]").forEach(row => row.onclick = () => renderAppDetail(rows[Number(row.dataset.appIndex)]));
  renderAppDetail(rows[0]);
}}

function renderAppHourly(app) {{
  const rows = Array.from({{length:24}}, (_,hour) => {{
    const found = (payload.app_hourly || []).find(x => x.package_name === app.package_name && Number(x.hour) === hour);
    return {{label:String(hour).padStart(2,"0"), value:Number(found?.foreground_minutes || 0)}};
  }});
  drawBarChart("appHourlyChart", rows, {{unit:"m", yLabel:"minutes by hour", color:colors[app.category] || "#3b82f6"}});
  const total = rows.reduce((sum,row)=>sum+row.value,0);
  const peak = rows.reduce((best,row)=>row.value > best.value ? row : best, rows[0]);
  document.getElementById("appHourlyMeta").innerHTML = `<div class="meter-chip"><small>App</small><strong>${{esc(appDisplayName(app))}}</strong></div><div class="meter-chip"><small>hourly total</small><strong>${{mins(total)}}</strong></div><div class="meter-chip"><small>peak hour</small><strong>${{peak.label}}:00 / ${{mins(peak.value)}}</strong></div>`;
}}

function renderAppTrend(app) {{
  const rows = (payload.daily || []).map(day => {{
    const found = (payload.app_trends || []).find(x => x.date === day.date && x.package_name === app.package_name);
    return {{label:day.date.slice(5), value:Number(found?.foreground_minutes || 0)}};
  }});
  drawLineChart("appTrendChart", rows, {{unit:"m", yLabel:"daily app minutes", max:chartMax(rows.map(r=>r.value), 10)}});
  document.getElementById("appTrendMeta").innerHTML = `<div class="meter-chip"><small>series</small><strong>${{esc(appDisplayName(app))}}</strong></div><div class="meter-chip"><small>days</small><strong>${{rows.length}}</strong></div><div class="meter-chip"><small>latest</small><strong>${{mins(rows.at(-1)?.value || 0)}}</strong></div>`;
}}

function renderAppDetail(app) {{
  if (!app) {{ document.getElementById("appDetail").innerHTML = `<div class="insight">当前分类下没有 App 记录。</div>`; return; }}
  const denominator = Math.max(Number(latest().phone_total_minutes || 1), 1);
  const share = Math.min(100, Number(app.foreground_minutes || 0) / denominator * 100);
  const shareLabel = "占手机总时长";
  const insight = app.package_name === "com.plan.kot32.tomatotime" ? "番茄 ToDo 的系统前台时长无法反映真实专注过程，已用截图识别的专注时长修正为普通学习 App 使用时长。" : "这个详情用于说明自动抓取后如何解释单个软件行为。分类仍可人工修正，分析只基于聚合痕迹。";
  document.getElementById("appDetail").innerHTML = `<span class="pill" style="color:${{colors[app.category]||colors.other}}">${{categoryNames[app.category] || app.category || "其他"}}</span><div class="detail-title">${{esc(appDisplayName(app))}}</div><div class="label">${{esc(app.package_name || "")}}</div><div class="detail-grid"><div><small>使用时长</small><strong>${{mins(app.foreground_minutes)}}</strong></div><div><small>打开次数</small><strong>${{app.open_count || 0}}</strong></div><div><small>${{shareLabel}}</small><strong>${{share.toFixed(1)}}%</strong></div><div><small>最近使用</small><strong>${{esc(app.last_used_at || "未知")}}</strong></div></div><div class="insight" style="margin-top:12px">${{esc(insight)}}</div>`;
  renderAppHourly(app);
  renderAppTrend(app);
}}

function renderOutputTrend() {{
  const rows = (payload.output_trends || payload.daily || []).map(d => ({{label:d.date.slice(5), value:Number(d.learning_output_score || 0)}}));
  drawLineChart("outputTrendChart", rows, {{unit:"", yLabel:"windows study score", max:100}});
  const latestRow = rows.at(-1) || {{value:0}};
  const trendRows = payload.output_trends || [];
  const latestTrend = trendRows.at(-1) || {{}};
  document.getElementById("outputTrendMeta").innerHTML = `<div class="meter-chip"><small>latest score</small><strong>${{Number(latestRow.value || 0).toFixed(1)}}</strong></div><div class="meter-chip"><small>focus</small><strong>${{mins(latestTrend.focus_minutes ?? latest().focus_minutes ?? 0)}}</strong></div><div class="meter-chip"><small>file records</small><strong>${{latestTrend.total_study_files_count ?? latest().total_study_files_count ?? 0}}</strong></div><div class="meter-chip"><small>R commands</small><strong>${{latestTrend.r_command_count ?? latest().r_command_count ?? 0}}</strong></div>`;
}}

function renderOutput() {{
  document.getElementById("fileTable").innerHTML = payload.files.map(f => `<tr><td>${{esc(f.extension)}}</td><td>${{esc(f.activity_type)}}</td><td>${{f.count}}</td></tr>`).join("");
  const focusHtml = (payload.focus_sessions || []).length
    ? `<h2>番茄 ToDo 学习会话</h2><div class="table-wrap"><table><thead><tr><th>任务</th><th>时间</th><th>时长</th><th>来源</th></tr></thead><tbody>${{payload.focus_sessions.map(s => `<tr><td>${{esc(s.title)}}</td><td>${{esc((s.start_time || "") + (s.end_time ? " - " + s.end_time : ""))}}</td><td>${{mins(s.minutes)}}</td><td>${{esc(s.source || "manual")}}</td></tr>`).join("")}}</tbody></table></div>`
    : `<h2>番茄 ToDo 学习会话</h2><p class="muted">尚未导入 focus_*.json；当前学习情况主要来自 App 与文件/R 信号。</p>`;
  document.getElementById("focusSessions").innerHTML = focusHtml;
  const total = payload.files.reduce((sum,f)=>sum+Number(f.count||0),0);
  document.getElementById("evidenceHeat").innerHTML = Array.from({{length:24}}, (_,i) => `<span class="${{i < Math.min(24,total) ? "hot" : ""}}" title="文件信号 ${{i+1}}"></span>`).join("");
  const r = payload.r_summary || {{}};
  let packages = [];
  try {{ packages = JSON.parse(r.top_packages_json || "[]").map(x=>x.name); }} catch(e) {{}}
  const rows = [["命令总数",r.command_count],["数据读取",r.data_import_count],["数据清洗",r.data_cleaning_count],["可视化",r.visualization_count],["统计分析",r.statistics_count],["建模",r.modeling_count],["常用包",packages.join(" / ") || "无"]];
  document.getElementById("rSummary").innerHTML = rows.map(x => `<div class="kv"><span>${{x[0]}}</span><strong>${{esc(x[1])}}</strong></div>`).join("");
  renderOutputTrend();
}}

function renderAi() {{
  document.getElementById("aiReview").innerHTML = renderReviewText(payload.review.review_text || "");
  document.getElementById("promptBox").textContent = payload.review.prompt || JSON.stringify(payload.latest, null, 2);
}}

document.querySelectorAll("[data-tab]").forEach(btn => btn.onclick = () => {{
  document.querySelectorAll("[data-tab]").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  document.querySelectorAll(".tab-page").forEach(p => p.classList.add("hidden"));
  document.getElementById("tab-" + btn.dataset.tab).classList.remove("hidden");
  const source = btn.dataset.tab === "apps" ? "phone" : btn.dataset.tab === "output" ? "windows" : btn.dataset.tab === "ai" ? "mimo" : "rstudio";
  setActiveSource(source);
  toast(`已切换到：${{btn.textContent}}`);
}});
document.querySelectorAll("[data-metric]").forEach(chip => chip.onclick = () => {{
  document.querySelectorAll("[data-metric]").forEach(c => c.classList.remove("active"));
  chip.classList.add("active");
  renderTrend(chip.dataset.metric);
  toast(`趋势已切换：${{chip.textContent}}`);
}});
document.getElementById("themeBtn").onclick = () => {{
  const next = document.body.dataset.theme === "dark" ? "light" : "dark";
  document.body.dataset.theme = next; localStorage.setItem("sp-theme", next);
  toast(next === "dark" ? "已切换深色模式" : "已切换浅色模式");
}};
document.getElementById("sortTime").onclick = () => {{ appSort = "time"; renderApps(); toast("App 已按使用时长排序"); }};
document.getElementById("sortOpen").onclick = () => {{ appSort = "open"; renderApps(); toast("App 已按打开次数排序"); }};
renderKpis(); renderTrend("learning_input_score"); renderCategoryBars(); renderQualityStatus(); renderFormulaList(); renderPeriodPlan(); renderFilters(); renderApps(); renderOutput(); renderAi(); setActiveSource("phone");
</script>
</body>
</html>"""


def main() -> None:
    REPORT_DIR.mkdir(exist_ok=True)
    payload = load_payload()
    output = REPORT_DIR / "studypulse_ui_interactive.html"
    output.write_text(render(payload), encoding="utf-8")
    print(f"written {output}")


if __name__ == "__main__":
    main()
