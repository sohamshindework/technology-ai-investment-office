"""Scan publishable files without printing any matched secret values."""

import re
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
try:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    paths = [root / p for p in result.stdout.decode().split("\0") if p and (root / p).is_file()]
except subprocess.CalledProcessError:
    paths = [
        p
        for p in root.rglob("*")
        if p.is_file()
        and not any(
            part in {".venv", ".git", "__pycache__", ".pytest_cache", ".ruff_cache", "outputs", "data"}
            for part in p.relative_to(root).parts
        )
    ]
patterns = [
    r"sk-(?:proj-)?[A-Za-z0-9_-]{24,}",
    r"gh[pousr]_[A-Za-z0-9]{24,}",
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    r"AKIA[0-9A-Z]{16}",
]
problems = []
for path in paths:
    rel = path.relative_to(root)
    if path.name == ".env" or path.name.startswith(".env.") or path.suffix in {".pyc", ".sqlite3", ".duckdb"} or ".DS_Store" in rel.parts:
        problems.append(f"{rel}: forbidden generated/private file")
    if path.stat().st_size > 3_000_000:
        problems.append(f"{rel}: unexpectedly large file")
    if path.suffix not in {".jpg", ".png"}:
        text = path.read_text(errors="replace")
        if any(re.search(pattern, text) for pattern in patterns):
            problems.append(f"{rel}: potential credential pattern")
        if "/Users/" in text or "/home/" in text:
            # Public source URLs can legitimately contain /home/; scan only local absolute roots.
            if re.search(r'/(?:Users|home)/[A-Za-z][^\s"<>]*', text) and "/Users/" in text:
                problems.append(f"{rel}: local machine path")
for message in problems:
    print(message)
print(f"Scanned {len(paths)} publishable files; {len(problems)} findings. Pattern scan is not a security guarantee.")
sys.exit(bool(problems))
