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
    active_pane_interval_ms: int = 250
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
        tmp: str | None = None
        try:
            fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
            with open(fd, "w", encoding="utf-8") as f:
                f.write(content)
            Path(tmp).replace(path)
        except OSError:
            # Clean up leftover temp file
            if tmp:
                try:
                    Path(tmp).unlink(missing_ok=True)
                except OSError:
                    pass
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

    def import_ssh_config(self, path: Path | None = None) -> list[ConnectionConfig]:
        """Parse ~/.ssh/config and return new ConnectionConfig entries.

        Only imports hosts not already present in self.connections.
        Skips wildcard patterns (Host *) and hosts without a HostName.
        """
        if path is None:
            path = Path.home() / ".ssh" / "config"
        if not path.exists():
            logger.info("No SSH config at %s", path)
            return []

        imported: list[ConnectionConfig] = []
        existing_names = {c.name for c in self.connections}

        for host in parse_ssh_config(path):
            if host.name in existing_names:
                continue
            self.connections.append(host)
            imported.append(host)
            existing_names.add(host.name)

        if imported:
            logger.info("Imported %d hosts from %s", len(imported), path)
        return imported


def parse_ssh_config(path: Path) -> list[ConnectionConfig]:
    """Parse an OpenSSH config file into ConnectionConfig entries.

    Handles: Host, HostName, Port, User, IdentityFile.
    Skips wildcard hosts (containing * or ?) and hosts with no HostName.
    Expands ~ in IdentityFile paths.
    """
    hosts: list[ConnectionConfig] = []
    current: dict[str, str] = {}

    def _flush() -> None:
        alias = current.get("host", "")
        hostname = current.get("hostname", "")
        if not alias or not hostname:
            return
        # Skip wildcard-only aliases
        if "*" in alias or "?" in alias:
            return
        port = 22
        if "port" in current:
            try:
                port = int(current["port"])
            except ValueError:
                pass
        key_file = current.get("identityfile", "")
        if key_file:
            key_file = str(Path(key_file).expanduser())
        hosts.append(ConnectionConfig(
            name=alias,
            host=hostname,
            port=port,
            username=current.get("user", ""),
            key_file=key_file,
        ))

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        logger.warning("Could not read SSH config %s", path)
        return []

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        # SSH config format: "Keyword value" or "Keyword=value"
        if "=" in line:
            key, _, value = line.partition("=")
        else:
            key, _, value = line.partition(" ")
        key = key.strip().lower()
        value = value.strip()

        if key == "host":
            _flush()
            # Host can have multiple space-separated aliases; use first non-wildcard
            aliases = value.split()
            alias = next((a for a in aliases if "*" not in a and "?" not in a), "")
            current = {"host": alias} if alias else {}
        elif key == "match":
            # Match blocks are not supported; flush and skip
            _flush()
            current = {}
        elif current:
            # Only store first occurrence of each key per host block
            if key not in current:
                current[key] = value

    _flush()
    return hosts
