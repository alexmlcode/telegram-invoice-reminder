# identity_resolver.py — Layered identity resolution (channel account → channel → global → fallback)

"""Resolve identity across layers: channel account → channel → global → fallback."""

from __future__ import annotations

import pathlib
import yaml
from typing import Optional

from supervisor.state import DRIVE_ROOT


class IdentityResolver:
    """Resolve identity across layers."""

    def __init__(self, config_path: Optional[str] = None):
        """Load identity config from YAML file."""
        self._config_path = pathlib.Path(config_path) if config_path else None
        if self._config_path and self._config_path.exists():
            try:
                self._config = yaml.safe_load(self._config_path.read_text(encoding="utf-8"))
            except Exception:
                self._config = {}
        else:
            # Default config (fallback)
            self._config = {
                "accounts": {},
                "channels": {},
                "global": "Alexander Mleev — Telegram supervisor daemon",
                "fallback": "System Agent",
            }

    def resolve(self, chat_id: int, account_id: Optional[int] = None) -> str:
        """Resolve identity for a given chat (and optionally account)."""
        # 1. Channel account identity (if available)
        accounts = self._config.get("accounts", {})
        if account_id:
            account_identity = accounts.get(str(account_id))
            if account_identity:
                return account_identity

        # 2. Channel identity (if available)
        channels = self._config.get("channels", {})
        channel_identity = channels.get(str(chat_id))
        if channel_identity:
            return channel_identity

        # 3. Global identity (fallback)
        global_identity = self._config.get("global")
        if global_identity:
            return global_identity

        # 4. System default (last resort)
        return self._config.get("fallback", "System Agent")


# Single instance for the process
_resolver: Optional[IdentityResolver] = None


def get_resolver() -> IdentityResolver:
    """Get or create the global identity resolver."""
    global _resolver
    if _resolver is None:
        config_path = DRIVE_ROOT / "config" / "identity_config.yaml"
        _resolver = IdentityResolver(str(config_path))
    return _resolver


def resolve_identity(chat_id: int, account_id: Optional[int] = None) -> str:
    """Convenience function: resolve identity for a given chat."""
    return get_resolver().resolve(chat_id, account_id)
