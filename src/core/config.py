"""Application configuration: saved connections and user preferences."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_DIR = Path.home() / ".tmuxpilot"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"


@dataclass
class ConnectionConfig:
    """Saved SSH connection parameters."""

    name: str
    host: str
    port: int = 22
    username: str = ""
    key_file: str = ""  # path to private key; empty = use agent / password
    # Password is intentionally NOT persisted — prompted at connect time.

    @property
    def display_label(self) -> str:
        user_part = f"{self.username}@" if self.username else ""
        port_part = f":{self.port}" if self.port != 22 else ""
        return f"{self.name} ({user_part}{self.host}{port_part})"


@dataclass
class PollConfig:
    """Polling interval settings (milliseconds)."""

    structure_interval_ms: int = 3000
    active_pane_interval_ms: int = 500
    inactive_pane_interval_ms: int = 2000


@dataclass
class AppConfig:
    """Top-level application configuration."""

    connections: list[ConnectionConfig] = field(default_factory=list)
    poll: PollConfig = field(default_factory=PollConfig)
    font_family: str = "Consolas"
    font_size: int = 10
    theme: str = "system"  # "system", "dark", "light"

    # --- persistence ---

    def save(self, path: Path = DEFAULT_CONFIG_FILE) -> None:
        import stat
        import tempfile

        path.parent.mkdir(parents=True, exist_ok=True)
        # Restrict directory permissions (owner-only on POSIX)
        try:
            path.parent.chmod(stat.S_IRWXU)
        except OSError:
            pass  # Windows doesn't support POSIX chmod

        data = asdict(self)
        content = json.dumps(data, indent=2)

        # Atomic write: write to temp file first, then rename.
        # Prevents leaving an empty/corrupt config if interrupted mid-write.
        try:
            fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
            with open(fd, "w", encoding="utf-8") as f:
                f.write(content)
            Path(tmp).replace(path)
        except OSError:
            # Fallback: direct write (e.g., if rename across drives fails)
            path.write_text(content, encoding="utf-8")

        try:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        logger.info("Config saved to %s", path)

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_FILE) -> AppConfig:
        if not path.exists():
            logger.info("No config file at %s — using defaults", path)
            return cls()
        try:
            text = path.read_text(encoding="utf-8").strip()
            if not text:
                logger.warning("Config file %s is empty — using defaults", path)
                return cls()
            data = json.loads(text)
            conns = [ConnectionConfig(**c) for c in data.get("connections", [])]
            poll = PollConfig(**data.get("poll", {}))
            return cls(
                connections=conns,
                poll=poll,
                font_family=data.get("font_family", "Consolas"),
                font_size=data.get("font_size", 10),
                theme=data.get("theme", "system"),
            )
        except Exception:
            logger.exception("Failed to load config from %s — using defaults", path)
            return cls()

    # --- helpers ---

    def add_connection(self, conn: ConnectionConfig) -> None:
        self.connections.append(conn)

    def remove_connection(self, name: str) -> None:
        self.connections = [c for c in self.connections if c.name != name]

    def find_connection(self, name: str) -> ConnectionConfig | None:
        for c in self.connections:
            if c.name == name:
                return c
        return None
