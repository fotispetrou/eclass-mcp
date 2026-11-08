"""Settings come from environment variables, with the system keyring as a
fallback for the password so it does not have to live in a config file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_URL = "https://eclass.uth.gr"
KEYRING_SERVICE = "eclass-mcp"


class ConfigError(Exception):
    pass


def keyring_get(key: str) -> str | None:
    try:
        import keyring
    except ImportError:
        return None
    try:
        return keyring.get_password(KEYRING_SERVICE, key)
    except Exception:
        return None


@dataclass
class Settings:
    base_url: str
    username: str
    password: str
    download_dir: Path
    timeout: float = 30.0

    @classmethod
    def from_env(cls) -> "Settings":
        base_url = os.environ.get("ECLASS_URL", DEFAULT_URL).rstrip("/")
        username = os.environ.get("ECLASS_USERNAME") or keyring_get("username")
        password = os.environ.get("ECLASS_PASSWORD")
        if not password and username:
            password = keyring_get(username)
        if not username or not password:
            raise ConfigError(
                "No eClass credentials. Set ECLASS_USERNAME and ECLASS_PASSWORD, "
                "or run `eclass-mcp login` to store them in the system keyring."
            )
        download_dir = Path(
            os.environ.get("ECLASS_DOWNLOAD_DIR", "~/Downloads/eclass")
        ).expanduser()
        timeout = float(os.environ.get("ECLASS_TIMEOUT", "30"))
        return cls(base_url, username, password, download_dir, timeout)
