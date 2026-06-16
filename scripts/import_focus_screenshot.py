from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from studypulse_config import focus_export_dir, focus_screenshot_inbox_dir, load_config


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATUS_PATH = PROJECT_ROOT / "data" / "focus_import_status.json"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def write_status(status: str, message: str, **detail: Any) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": now_text(),
        "status": status,
        "message": message,
        **detail,
    }
    STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def latest_image(folder: Path) -> Path | None:
    if not folder.exists():
        return None
    candidates = [path for path in folder.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES and path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", cleaned)
    if fenced:
        cleaned = fenced.group(1)
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("model output is not a JSON object")
    return data


def normalize_focus_json(data: dict[str, Any], source_image: Path) -> dict[str, Any]:
    if not data.get("date"):
        raise ValueError("recognized result has no date")
    sessions = data.get("sessions")
    if not isinstance(sessions, list):
        raise ValueError("recognized result has no sessions list")

    normalized_sessions = []
    for item in sessions:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("task") or item.get("name") or "未命名专注").strip()
        start = str(item.get("start") or item.get("start_time") or "").strip()
        end = str(item.get("end") or item.get("end_time") or "").strip()
        minutes_raw = item.get("minutes", item.get("duration_minutes", 0))
        try:
            minutes = int(round(float(minutes_raw)))
        except (TypeError, ValueError):
            minutes = 0
        if minutes <= 0:
            continue
        normalized_sessions.append(
            {
                "title": title,
                "start": start,
                "end": end,
                "minutes": minutes,
            }
        )

    if not normalized_sessions:
        raise ValueError("recognized result has no positive-duration sessions")

    source_date = datetime.fromtimestamp(source_image.stat().st_mtime).date().isoformat()
    recognized_date = str(data["date"])
    final_date = source_date or recognized_date

    return {
        "source": "tomato_todo_screenshot",
        "source_image": str(source_image),
        "date": final_date,
        "recognized_date": recognized_date,
        "date_source": "screenshot_file_mtime",
        "total_focus_minutes": sum(int(item["minutes"]) for item in normalized_sessions),
        "focus_count": len(normalized_sessions),
        "sessions": normalized_sessions,
    }


def call_vision_model(api_base_url: str, api_key: str, model: str, image_path: Path) -> dict[str, Any]:
    url = api_base_url.rstrip("/") + "/chat/completions"
    prompt = (
        "你是 StudyPulse 的番茄 ToDo 截图识别器。"
        "请只输出 JSON，不要解释。"
        "从截图中识别日期、专注任务、开始时间、结束时间和分钟数。"
        "输出格式必须是："
        '{"date":"YYYY-MM-DD","sessions":[{"title":"任务名","start":"HH:MM","end":"HH:MM","minutes":整数}]}。'
        "如果截图里有总时长但缺少某条结束时间，也要尽量根据时间轴识别。"
    )
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url(image_path)}},
                ],
            }
        ],
        "temperature": 0,
    }
    encoded_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(1, 4):
        request = urllib.request.Request(
            url,
            data=encoded_body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                body = json.loads(response.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            return extract_json(content)
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < 3:
                print(f"Focus vision API transient error on attempt {attempt}/3: {exc}; retrying...")
                time.sleep(5 * attempt)
                continue
            raise last_error
    raise RuntimeError("Focus vision API call failed without a captured error")


def write_focus_export(data: dict[str, Any], config: dict[str, Any]) -> Path:
    target_dir = focus_export_dir(config)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"focus_{data['date']}.json"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert a Tomato ToDo screenshot into StudyPulse focus JSON.")
    parser.add_argument("image", nargs="?", help="Screenshot path. Omit with --latest to use the newest image in focus.screenshot_inbox_dir.")
    parser.add_argument("--latest", action="store_true", help="Use latest screenshot from configured screenshot inbox.")
    parser.add_argument("--optional", action="store_true", help="Return success when no screenshot/API is available.")
    args = parser.parse_args()

    config = load_config()
    folder = focus_screenshot_inbox_dir(config)
    folder.mkdir(parents=True, exist_ok=True)
    image_path = Path(args.image).expanduser().resolve() if args.image else None
    if args.latest or image_path is None:
        image_path = latest_image(folder)
    if image_path is None:
        message = f"No focus screenshot found in {folder}"
        print(message)
        write_status("skipped", message, screenshot_inbox=str(folder))
        return 0 if args.optional else 1
    if not image_path.exists():
        message = f"Focus screenshot not found: {image_path}"
        print(message, file=sys.stderr)
        write_status("failed", message, screenshot=str(image_path))
        return 0 if args.optional else 1

    mimo = config.get("mimo", {})
    focus = config.get("focus", {})
    api_base_url = str(focus.get("vision_api_base_url") or mimo.get("api_base_url") or "").strip()
    model = str(focus.get("vision_model") or mimo.get("model") or "").strip()
    api_key_env = str(focus.get("vision_api_key_env") or mimo.get("api_key_env") or "MIMO_API_KEY")
    api_key = os.environ.get(api_key_env, "").strip()
    if not api_base_url or not model or not api_key:
        print("Focus screenshot import skipped: missing vision API config or API key.")
        print(f"Need api_base_url, model, and environment variable {api_key_env}.")
        write_status(
            "skipped",
            "missing vision API config or API key",
            screenshot=str(image_path),
            model=model,
            api_base_url=api_base_url,
            api_key_env=api_key_env,
        )
        return 0 if args.optional else 1

    try:
        recognized = call_vision_model(api_base_url, api_key, model, image_path)
        focus_json = normalize_focus_json(recognized, image_path)
        target = write_focus_export(focus_json, config)
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        print(f"Focus screenshot import failed: HTTPError {exc.code}: {exc.reason}", file=sys.stderr)
        if body:
            print(f"Response body: {body[:1000]}", file=sys.stderr)
        if exc.code in {400, 404, 415, 422}:
            print(
                "Likely cause: the configured model/API endpoint does not support image_url vision input. "
                "Set focus.vision_model/focus.vision_api_base_url to a vision-capable OpenAI-compatible API, "
                "or use manual focus JSON import.",
                file=sys.stderr,
            )
        write_status(
            "failed",
            f"HTTPError {exc.code}: {exc.reason}",
            screenshot=str(image_path),
            response_body=body[:1000],
            model=model,
        )
        return 0 if args.optional else 1
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError, ValueError) as exc:
        print(f"Focus screenshot import failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        write_status(
            "failed",
            f"{type(exc).__name__}: {exc}",
            screenshot=str(image_path),
            model=model,
        )
        return 0 if args.optional else 1

    print(f"Focus screenshot imported: {target}")
    print(f"Date: {focus_json['date']} | minutes: {focus_json['total_focus_minutes']} | sessions: {focus_json['focus_count']}")
    write_status(
        "success",
        "Focus screenshot imported",
        screenshot=str(image_path),
        target=str(target),
        date=focus_json["date"],
        total_focus_minutes=focus_json["total_focus_minutes"],
        focus_count=focus_json["focus_count"],
        model=model,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
