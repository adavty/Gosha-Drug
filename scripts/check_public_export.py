from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

FORBIDDEN_NAMES = {
    ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__",
    "build", "dist", "gosha-demo.db", "governance", "submission",
}

EMAIL_PATTERN = re.compile(r"(?i)(?<![\w.+:/-])[\w.+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}")
PHONE_PATTERN = re.compile(r"(?<!\w)\+[0-9][0-9 ()-]{8,}[0-9](?!\w)")
PLACEHOLDER_EMAIL_DOMAINS = {"example.com", "example.net", "example.org", "example.invalid"}
SECRET_PATTERNS = {
    "Telegram bot token": re.compile(r"(?<!\w)[0-9]{6,12}:[A-Za-z0-9_-]{20,}(?!\w)"),
    "OpenAI-style secret": re.compile(r"(?<!\w)sk-[A-Za-z0-9_-]{20,}(?!\w)"),
    "private key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
}


def _email_candidates(text: str) -> list[str]:
    candidates = [match.group(0).lower() for match in EMAIL_PATTERN.finditer(text)]
    return [value for value in candidates if value.rsplit("@", 1)[1] not in PLACEHOLDER_EMAIL_DOMAINS]


def _phone_candidates(text: str) -> list[str]:
    return ["".join(char for char in match.group(0) if char.isdigit()) for match in PHONE_PATTERN.finditer(text)]


def scan(root: Path) -> list[str]:
    root = root.resolve()
    findings: list[str] = []

    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if path.name in FORBIDDEN_NAMES or path.name.endswith(".egg-info"):
            findings.append(f"forbidden path: {relative}")
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        raw = path.read_bytes()
        if b"\0" in raw:
            continue
        text = raw.decode("utf-8", errors="ignore")

        emails = _email_candidates(text)
        phones = _phone_candidates(text)
        if emails:
            findings.append(f"email address: {relative}")
        if phones:
            findings.append(f"international phone-like value: {relative}")

        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{label}: {relative}")

    return sorted(set(findings))


def self_test() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        planted_contact = "privacy-regression" + "@" + "scanner-check.dev"
        (root / "README.md").write_text(f"Contact: {planted_contact}\n", encoding="utf-8")
        fixture = root / "tests" / "test_urls.txt"
        fixture.parent.mkdir()
        fixture.write_text(
            "postgresql://demo:demo@127.0.0.1:5432/demo\n"
            "uses: actions/checkout@v4\n"
            "https://user@example.invalid/path\n",
            encoding="utf-8",
        )
        findings = scan(root)
        assert findings == ["email address: README.md"], findings
    print("Public export privacy scan self-test: PASS")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fail when a public export contains private paths, contacts or secrets")
    parser.add_argument("root", type=Path, nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.root is None:
        parser.error("root is required unless --self-test is used")

    findings = scan(args.root)
    if findings:
        raise SystemExit("Public export privacy scan failed:\n- " + "\n- ".join(findings))
    print("Public export privacy scan: PASS")


if __name__ == "__main__":
    main()
