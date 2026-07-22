from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


class URLRuleError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedURL:
    display_url: str
    canonical_url: str
    domain: str


_CONTROL_OR_SPACE = re.compile(r"[\x00-\x20\x7f]")


def normalize_material_url(value: str) -> NormalizedURL:
    """Validate metadata-only material URL without any network access."""
    raw = value.strip()
    if not raw or len(raw) > 2048 or _CONTROL_OR_SPACE.search(raw) or "\\" in raw:
        raise URLRuleError("invalid_url_characters")
    try:
        parsed = urlsplit(raw)
        port = parsed.port  # forces invalid-port validation
    except ValueError as exc:
        raise URLRuleError("invalid_url") from exc
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"}:
        raise URLRuleError("scheme_not_allowed")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise URLRuleError("host_or_credentials_invalid")
    try:
        host = parsed.hostname.encode("idna").decode("ascii").casefold()
    except UnicodeError as exc:
        raise URLRuleError("invalid_hostname") from exc
    if not host or host.startswith(".") or host.endswith(".") or ".." in host:
        raise URLRuleError("invalid_hostname")
    if ":" in host and not host.startswith("["):
        host_for_url = f"[{host}]"
    else:
        host_for_url = host
    include_port = port is not None and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443))
    netloc = f"{host_for_url}:{port}" if include_port else host_for_url
    path = parsed.path or "/"
    canonical = urlunsplit((scheme, netloc, path, parsed.query, ""))
    display = urlunsplit((scheme, netloc, path, parsed.query, parsed.fragment))
    return NormalizedURL(display, canonical, host)
