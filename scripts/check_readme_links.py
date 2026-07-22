from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def markdown_files() -> list[Path]:
    return sorted(
        path for path in ROOT.rglob("*.md")
        if not {".git", ".venv", "build", "dist"}.intersection(path.relative_to(ROOT).parts)
    )


def main() -> None:
    missing: list[str] = []
    checked = 0
    for source in markdown_files():
        for target in re.findall(r"\[[^]]*]\(([^)]+)\)", source.read_text(encoding="utf-8")):
            target = target.split("#", 1)[0]
            if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
                continue
            checked += 1
            path = source.parent / unquote(target)
            if not path.exists():
                missing.append(f"{source.relative_to(ROOT)} -> {target}")
    if missing:
        raise SystemExit("Missing Markdown targets:\n- " + "\n- ".join(sorted(set(missing))))
    print(f"Markdown local links: PASS ({checked} targets)")


if __name__ == "__main__":
    main()
