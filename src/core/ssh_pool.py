"""SSH connection pool using asyncssh.

Manages persistent connections with auto-reconnect and multiplexed channels.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

import asyncssh

from .config import ConnectionConfig

logger = logging.getLogger(__name__)


class ConnState(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()


@dataclass
class HostConnection:
    """Tracks state for a single SSH host."""

    config: ConnectionConfig
    password: str = ""  # kept in memory for session lifetime (for reconnect)
    conn: asyncssh.SSHClientConnection | None = None
    state: ConnState = ConnState.DISCONNECTED
    retry_count: int = 0
    _lock: asyncio.Lock | None = field(default=None, repr=False)

    @property
    def lock(self) -> asyncio.Lock:
        """Lazy-init lock to avoid capturing wrong event loop at creation."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock


class SSHPool:
    """Pool of SSH connections, one per configured host.

    All public methods are coroutines safe to call from the qasync event loop.
    """

    MAX_RETRIES = 3
    RETRY_BACKOFF_BASE = 2  # seconds

    def __init__(self) -> None:
        self._hosts: dict[str, HostConnection] = {}
        # Callbacks for UI notifications
        self.on_state_change: list[Any] = []  # callables(host_name, ConnState)

    # ---------- public API ----------

    async def connect(
        self,
        config: ConnectionConfig,
        password: str = "",
    ) -> None:
        """Establish (or re-establish) an SSH connection to *config.name*."""
        hc = self._hosts.get(config.name)
        if hc is None:
            hc = HostConnection(config=config, password=password)
            self._hosts[config.name] = hc
        else:
            # Update password if re-connecting with a new one
            if password:
                hc.password = password

        async with hc.lock:
            if hc.state == ConnState.CONNECTED and hc.conn and not hc.conn.is_closed():
                return  # already connected
            hc.state = ConnState.CONNECTING
            self._notify(config.name, ConnState.CONNECTING)
            try:
                hc.conn = await self._open(config, hc.password)
                hc.state = ConnState.CONNECTED
                hc.retry_count = 0
                self._notify(config.name, ConnState.CONNECTED)
                logger.info("Connected to %s", config.display_label)
            except Exception:
                hc.state = ConnState.DISCONNECTED
                self._notify(config.name, ConnState.DISCONNECTED)
                raise

    async def disconnect(self, host_name: str) -> None:
        """Close the connection for *host_name*."""
        hc = self._hosts.get(host_name)
        if hc is None:
            return
        async with hc.lock:
            if hc.conn and not hc.conn.is_closed():
                hc.conn.close()
                await hc.conn.wait_closed()
            hc.conn = None
            hc.password = ""  # clear session password on explicit disconnect
            hc.state = ConnState.DISCONNECTED
            self._notify(host_name, ConnState.DISCONNECTED)
            logger.info("Disconnected from %s", host_name)

    async def disconnect_all(self) -> None:
        for name in list(self._hosts):
            await self.disconnect(name)

    async def exec(self, host_name: str, cmd: str) -> str:
        """Execute *cmd* on *host_name* and return stdout.

        Automatically reconnects once if the connection was lost.
        """
        hc = self._hosts.get(host_name)
        if hc is None:
            raise RuntimeError(f"No connection configured for {host_name!r}")

        for attempt in range(2):
            conn = await self._ensure_connected(hc)
            try:
                result = await conn.run(cmd, check=True)
                return result.stdout or ""
            except (asyncssh.ConnectionLost, asyncssh.DisconnectError, OSError) as exc:
                logger.warning(
                    "SSH command failed (attempt %d) on %s: %s",
                    attempt + 1, host_name, exc,
                )
                hc.state = ConnState.DISCONNECTED
                hc.conn = None
                self._notify(host_name, ConnState.DISCONNECTED)
                if attempt == 1:
                    raise

        raise RuntimeError("unreachable")

    def get_state(self, host_name: str) -> ConnState:
        hc = self._hosts.get(host_name)
        return hc.state if hc else ConnState.DISCONNECTED

    def connected_hosts(self) -> list[str]:
        return [
            name
            for name, hc in self._hosts.items()
            if hc.state == ConnState.CONNECTED
        ]

    # ---------- internal ----------

    async def _ensure_connected(self, hc: HostConnection) -> asyncssh.SSHClientConnection:
        async with hc.lock:
            if hc.state == ConnState.CONNECTED and hc.conn and not hc.conn.is_closed():
                return hc.conn
            hc.state = ConnState.CONNECTING
            self._notify(hc.config.name, ConnState.CONNECTING)
            hc.conn = await self._open_with_retry(hc)
            hc.state = ConnState.CONNECTED
            self._notify(hc.config.name, ConnState.CONNECTED)
            return hc.conn

    async def _open_with_retry(self, hc: HostConnection) -> asyncssh.SSHClientConnection:
        last_exc: Exception | None = None
        for i in range(self.MAX_RETRIES):
            try:
                return await self._open(hc.config, hc.password)
            except Exception as exc:
                last_exc = exc
                wait = self.RETRY_BACKOFF_BASE ** i
                logger.warning(
                    "Retry %d for %s in %ds: %s", i + 1, hc.config.name, wait, exc
                )
                await asyncio.sleep(wait)
        raise RuntimeError(
            f"Failed to connect to {hc.config.name} after {self.MAX_RETRIES} retries"
        ) from last_exc

    @staticmethod
    async def _open(
        config: ConnectionConfig,
        password: str = "",
    ) -> asyncssh.SSHClientConnection:
        kwargs: dict[str, Any] = {
            "host": config.host,
            "port": config.port,
            # Use system known_hosts by default (asyncssh reads ~/.ssh/known_hosts)
        }
        if config.username:
            kwargs["username"] = config.username
        if config.key_file:
            kwargs["client_keys"] = [config.key_file]
        if password:
            kwargs["password"] = password

        return await asyncssh.connect(**kwargs)

    def _notify(self, host_name: str, state: ConnState) -> None:
        for cb in self.on_state_change:
            try:
                cb(host_name, state)
            except Exception:
                logger.exception("State change callback failed")
