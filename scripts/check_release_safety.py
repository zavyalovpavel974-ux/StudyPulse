from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

SENSITIVE_PATTERNS = [
    ("personal email", re.compile(r"(1241228140@qq\.com|zavyalovpavel974@gmail\.com)", re.I)),
    ("local user path", re.compile(r"C:\\Users\\12412|F:\\R语言文档", re.I)),
    ("likely api key assignment", re.compile(r"(api[_-]?key|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}", re.I)),
]

SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".db", ".pyc"}


def git_candidate_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git ls-files failed")
    return [PROJECT_ROOT / line.strip() for line in result.stdout.splitlines() if line.strip()]


def should_scan(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.name == ".env.example":
        return False
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    return True


def main() -> None:
    findings: list[str] = []
    for path in git_candidate_files():
        if not should_scan(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(PROJECT_ROOT)
        for label, pattern in SENSITIVE_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                findings.append(f"{rel}:{line_no}: {label}: {match.group(0)}")

    if findings:
        print("Release safety check failed:")
        for item in findings:
            print(f"- {item}")
        raise SystemExit(1)

    print("Release safety check passed: no configured sensitive patterns found in Git candidate files.")


if __name__ == "__main__":
    main()
