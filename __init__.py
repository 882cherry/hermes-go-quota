"""OpenCode Go Quota — Hermes plugin.

Appends the OpenCode Go quota summary (5h rolling / weekly / monthly) to the
end of every final assistant reply, but ONLY when the active model provider is
opencode-go (detected from Hermes config: model.provider == "opencode-go" or
model.base_url containing opencode.ai/zen/go).

Implementation: registers the ``transform_llm_output`` plugin hook, which
fires once per turn after the tool-calling loop completes, right before the
final response is returned to the user. Returning a string replaces the
response text; we return ``response_text + "\n" + quota_line``.

No core Hermes files are modified — this is a drop-in plugin.

Config for the quota fetch itself (auth cookie) lives OUTSIDE Hermes config:
    ~/.hermes/opencode_go_quota.json          {"auth_cookie": "Fe26....", "workspace_id": "wrk_..."}
    ~/.config/opencode-go-quota/config.json   (same shape)
    env OPENCODE_GO_AUTH_COOKIE               (highest priority)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

PLUGIN_VERSION = "1.0.0"

# Optional: force quota line even when provider detection disagrees.
# Set "always" to always append, "auto" (default) to follow Hermes model config.
_MODE = os.environ.get("OPENCODE_GO_QUOTA_MODE", "auto")


def _load_hermes_model_config() -> dict[str, Any]:
    """Read Hermes model.provider / model.base_url from config.yaml (best-effort)."""
    home = os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
    try:
        import yaml

        cfg_path = Path(home) / "config.yaml"
        if not cfg_path.exists():
            return {}
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        return dict((cfg.get("model") or {}))
    except Exception:
        return {}


def _is_opencode_go_active() -> bool:
    if _MODE == "always":
        return True
    model_cfg = _load_hermes_model_config()
    provider = str(model_cfg.get("provider") or "").lower()
    base_url = str(model_cfg.get("base_url") or "").lower()
    return provider == "opencode-go" or "opencode.ai/zen/go" in base_url


def _quota_line() -> str:
    try:
        from .quota import fetch_quota_line

        return fetch_quota_line()
    except Exception:
        return ""


def _on_transform_llm_output(
    response_text: str = "",
    session_id: str = "",
    model: str = "",
    platform: str = "",
    **kwargs: Any,
) -> Optional[str]:
    """Append the quota line to the final reply (open-code-go provider only)."""
    if not response_text:
        return None
    if not _is_opencode_go_active():
        return None
    line = _quota_line()
    if not line:
        return None
    return f"{response_text}\n{line}"


def register(ctx) -> None:
    ctx.register_hook("transform_llm_output", _on_transform_llm_output)
