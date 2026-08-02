#!/usr/bin/env python3
"""OpenCode Go quota fetcher (shared by the Hermes plugin and the CLI).

Queries the OpenCode Go dashboard page for the three usage windows
(5h rolling / weekly / monthly) and returns a compact one-line summary.

Configuration (priority high → low):
    1. env OPENCODE_GO_AUTH_COOKIE / OPENCODE_GO_WORKSPACE_ID
    2. ~/.hermes/opencode_go_quota.json  {"auth_cookie": "Fe26....", "workspace_id": "wrk_..."}
    3. ~/.config/opencode-go-quota/config.json (same shape)

Output (single line, no secrets):
    opencode-go 5h 62% (3h后) · 周 45% (2d后) · 月 18% (12d后) [pro]

On any failure returns "" so callers can silently ignore.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

CONFIG_CANDIDATES = [
    Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / "opencode_go_quota.json",
    Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "opencode-go-quota" / "config.json",
]
CACHE_PATH = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / "cache" / "opencode_go_quota.json"
CACHE_TTL_SEC = 60

WORKSPACE_SERVER_ID = "def39973159c7f0483d8793a822b8dbb10d067e12c65455fcb4608459ba0234f"
DASHBOARD_BASE = "https://opencode.ai/workspace"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Gecko/20100101 Firefox/148.0"
TIMEOUT = 8.0
MAX_BYTES = 4 << 20

RE_WORKSPACE_ENTRY = re.compile(r'id\s*:\s*"(wrk_[^"]+)"[^{}]*?name\s*:\s*"([^"]*)"', re.DOTALL)


def _usage_patterns(key: str) -> tuple[re.Pattern, re.Pattern]:
    return (
        re.compile(r"%s:\s*\$R\[\d+\]\s*=\s*\{[^}]*usagePercent\s*:\s*(-?\d+(?:\.\d+)?)[^}]*resetInSec\s*:\s*(-?\d+(?:\.\d+)?)[^}]*\}" % key),
        re.compile(r"%s:\s*\$R\[\d+\]\s*=\s*\{[^}]*resetInSec\s*:\s*(-?\d+(?:\.\d+)?)[^}]*usagePercent\s*:\s*(-?\d+(?:\.\d+)?)[^}]*\}" % key),
    )
RE_PLAN = re.compile(r'plan:\s*\$R\[\d+\]\s*=\s*"([^"]+)"')


def _http_get(url: str, cookie: str, referer: str | None = None, extra_headers: dict | None = None) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Cookie": f"auth={cookie}",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read(MAX_BYTES).decode("utf-8", errors="replace")


def load_config() -> dict:
    cfg: dict = {}
    for p in CONFIG_CANDIDATES:
        if p.exists():
            try:
                cfg.update(json.loads(p.read_text(encoding="utf-8")))
                break
            except Exception:
                continue
    if os.environ.get("OPENCODE_GO_AUTH_COOKIE"):
        cfg["auth_cookie"] = os.environ["OPENCODE_GO_AUTH_COOKIE"].strip()
    if os.environ.get("OPENCODE_GO_WORKSPACE_ID"):
        cfg["workspace_id"] = os.environ["OPENCODE_GO_WORKSPACE_ID"].strip()
    return cfg


def extract_workspace_id(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("wrk_") and len(raw) > 4:
        return raw
    m = re.search(r"wrk_[A-Za-z0-9]+", raw)
    return m.group(0) if m else ""


def resolve_workspace_id(cookie: str, hint: str = "") -> str:
    resolved = extract_workspace_id(hint)
    if resolved:
        return resolved
    url = f"https://opencode.ai/_server?id={WORKSPACE_SERVER_ID}"
    # _server 需要 X-Server-Id 头,否则返回 500
    server_headers = {
        "X-Server-Id": WORKSPACE_SERVER_ID,
        "X-Server-Instance": f"server-fn:{int(time.time() * 1e9)}",
        "Origin": "https://opencode.ai",
        "Accept": "text/javascript, application/json;q=0.9, */*;q=0.8",
    }
    try:
        text = _http_get(url, cookie, referer="https://opencode.ai", extra_headers=server_headers)
    except Exception:
        return ""
    for ws_id, name in RE_WORKSPACE_ENTRY.findall(text):
        hint_l = hint.strip().lower()
        if not hint_l or ws_id.lower() == hint_l or name.strip().lower() == hint_l:
            return ws_id
    m = re.search(r'id\s*:\s*"(wrk_[^"]+)"', text)
    return m.group(1) if m else ""


def parse_usage(text: str) -> tuple[dict, str]:
    out: dict = {}
    for key in ("rollingUsage", "weeklyUsage", "monthlyUsage"):
        pct_first, reset_first = _usage_patterns(key)
        m = pct_first.search(text)
        if m:
            out[key] = (float(m.group(1)), int(float(m.group(2))))
            continue
        m = reset_first.search(text)
        if m:
            out[key] = (float(m.group(2)), int(float(m.group(1))))
    plan_m = RE_PLAN.search(text)
    return out, (plan_m.group(1) if plan_m else "")


def _fmt_reset(sec: int) -> str:
    if sec < 0:
        return ""
    if sec < 3600:
        return f"{max(1, sec // 60)}m后"
    if sec < 86400:
        return f"{sec // 3600}h后"
    return f"{sec // 86400}d后"


def _clamp(pct: float) -> float:
    return max(0.0, min(100.0, pct))


def format_line(usage: dict, plan: str) -> str:
    labels = [("rollingUsage", "5h"), ("weeklyUsage", "周"), ("monthlyUsage", "月")]
    parts: list[str] = []
    for key, label in labels:
        if key not in usage:
            continue
        pct, reset = usage[key]
        pct = _clamp(pct)
        reset_s = _fmt_reset(reset)
        parts.append(f"{label} {pct:.0f}% ({reset_s})" if reset_s else f"{label} {pct:.0f}%")
    if not parts:
        return ""
    line = " · ".join(parts)
    return f"opencode-go {line}" + (f" [{plan}]" if plan else "")


def fetch_quota_line(*, refresh: bool = False) -> str:
    """Top-level: return the quota summary line ("" on any failure)."""
    if not refresh and CACHE_PATH.exists():
        try:
            if time.time() - CACHE_PATH.stat().st_mtime < CACHE_TTL_SEC:
                return CACHE_PATH.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    cfg = load_config()
    cookie = (cfg.get("auth_cookie") or "").strip()
    if not cookie:
        return ""
    # 容错:允许粘贴 "auth=Fe26...." 或完整 Cookie 头
    if cookie.lower().startswith("auth="):
        cookie = cookie[5:].strip()
    if not cookie.startswith("Fe26.") and ";" in cookie:
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("auth="):
                cookie = part[5:]
                break
    workspace = resolve_workspace_id(cookie, (cfg.get("workspace_id") or "").strip())
    if not workspace:
        return ""

    url = f"{DASHBOARD_BASE}/{urllib.parse.quote(workspace, safe='')}/go"
    try:
        html = _http_get(url, cookie, referer=f"https://opencode.ai/workspace/{workspace}/go")
    except Exception:
        return ""
    if "/sign-in" in html and "rollingUsage" not in html:
        return ""

    usage, plan = parse_usage(html)
    line = format_line(usage, plan)
    if not line:
        return ""
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(line, encoding="utf-8")
    except Exception:
        pass
    return line


if __name__ == "__main__":
    import sys as _sys

    _line = fetch_quota_line(refresh="--refresh" in _sys.argv)
    if _line:
        print(_line)
        _sys.exit(0)
    _sys.exit(1)
