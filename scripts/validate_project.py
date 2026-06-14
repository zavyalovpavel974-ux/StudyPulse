from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from studypulse_config import configure_console_encoding


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

configure_console_encoding()


def run_step(name: str, args: list[str], *, required: bool = True) -> bool:
    print(f"[validate] {name}: {' '.join(args)}", flush=True)
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    result = subprocess.run(args, cwd=PROJECT_ROOT, check=False, env=env)
    if result.returncode == 0:
        print(f"[validate] {name}: ok", flush=True)
        return True
    level = "failed" if required else "warning"
    print(f"[validate] {name}: {level} exit_code={result.returncode}", flush=True)
    if required:
        raise SystemExit(result.returncode)
    return False


def compile_scripts() -> None:
    for path in sorted((PROJECT_ROOT / "scripts").glob("*.py")):
        run_step(f"py_compile {path.name}", [PYTHON, "-m", "py_compile", str(path)])


def validate_html_js() -> None:
    node = shutil.which("node")
    if not node:
        print("[validate] html js parse: warning node not found; skipped", flush=True)
        return
    js = (
        "const fs=require('fs');"
        "const html=fs.readFileSync('reports/studypulse_ui_interactive.html','utf8');"
        "const scripts=[...html.matchAll(/<script>([\\s\\S]*?)<\\/script>/g)].map(m=>m[1]);"
        "for (const s of scripts) new Function(s);"
        "console.log('ok scripts='+scripts.length+' size='+html.length);"
    )
    run_step("html js parse", [node, "-e", js])


def main() -> None:
    parser = argparse.ArgumentParser(description="Run StudyPulse project validation checks.")
    parser.add_argument("--with-sample-pipeline", action="store_true", help="Also run the sample pipeline without email.")
    args = parser.parse_args()

    compile_scripts()
    run_step("doctor", [PYTHON, str(PROJECT_ROOT / "scripts" / "doctor.py")])
    validate_html_js()
    run_step("release safety", [PYTHON, str(PROJECT_ROOT / "scripts" / "check_release_safety.py")])
    if args.with_sample_pipeline:
        run_step("sample pipeline", [PYTHON, str(PROJECT_ROOT / "scripts" / "run_pipeline.py"), "--sample", "--skip-email"])
    print("[validate] all required checks passed", flush=True)


if __name__ == "__main__":
    main()
