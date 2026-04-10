"""High-level tmux session manager.

Executes tmux commands over SSH, parses structured output with -F format
strings, and maintains an in-memory state cache with change signals.
"""

from __future__ import annotations

import logging
import shlex
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from .tmux_state import TmuxPane, TmuxSession, TmuxState, TmuxWindow

if TYPE_CHECKING:
    from .ssh_pool import SSHPool

logger = logging.getLogger(__name__)

# -F format delimiters — use ASCII unit separator to avoid collisions
SEP = "\x1f"

SESSION_FMT = SEP.join([
    "#{session_id}", "#{session_name}", "#{session_windows}", "#{session_attached}",
])
# Include session_id in window format so we can associate without extra queries
WINDOW_FMT = SEP.join([
    "#{session_id}", "#{window_id}", "#{window_index}", "#{window_name}",
    "#{window_width}", "#{window_height}", "#{window_panes}",
    "#{window_active}", "#{window_layout}",
])
# Include window_id in pane format so we can associate without extra queries
PANE_FMT = SEP.join([
    "#{window_id}", "#{pane_id}", "#{pane_index}",
    "#{pane_width}", "#{pane_height}",
    "#{pane_top}", "#{pane_left}", "#{pane_bottom}", "#{pane_right}",
    "#{pane_active}", "#{pane_current_command}", "#{pane_pid}",
])


def _tmux_cmd(*args: str) -> str:
    """Build a tmux command with properly shell-escaped arguments."""
    return "tmux " + " ".join(shlex.quote(a) for a in args)


class TmuxManager(QObject):
    """Manages tmux state for one SSH host.

    Signals
    -------
    state_changed(str)
        Emitted after every state refresh with the host name.
    """

    state_changed = Signal(str)  # host_name

    def __init__(self, ssh_pool: SSHPool, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ssh = ssh_pool
        self._states: dict[str, TmuxState] = {}  # keyed by host_name

    # ---------- state access ----------

    def get_state(self, host_name: str) -> TmuxState | None:
        return self._states.get(host_name)

    # ---------- polling ----------

    async def refresh_structure(self, host_name: str) -> TmuxState:
        """Fetch sessions / windows / panes in a single SSH round-trip."""
        # All three list commands batched into one exec. The -a flag on
        # list-windows and list-panes returns all items globally, and we
        # include session_id / window_id in the format strings so we can
        # associate them locally without extra queries.
        cmd = (
            f"tmux list-sessions -F '{SESSION_FMT}' 2>/dev/null;"
            f" echo '---TMUX_SEP---';"
            f" tmux list-windows -a -F '{WINDOW_FMT}' 2>/dev/null;"
            f" echo '---TMUX_SEP---';"
            f" tmux list-panes -a -F '{PANE_FMT}' 2>/dev/null"
        )
        raw = await self._ssh.exec(host_name, cmd)
        parts = raw.split("---TMUX_SEP---")
        if len(parts) < 3:
            logger.warning(
                "Unexpected tmux output for %s (got %d parts)", host_name, len(parts)
            )
            return self._states.get(host_name, TmuxState(host_id=host_name))

        sessions_raw, windows_raw, panes_raw = (p.strip() for p in parts[:3])

        state = TmuxState(host_id=host_name)

        # Parse sessions
        for line in sessions_raw.splitlines():
            fields = line.split(SEP)
            if len(fields) < 4:
                continue
            sid, sname, swins, sattached = fields[:4]
            state.sessions[sid] = TmuxSession(
                session_id=sid,
                name=sname,
                window_count=int(swins),
                attached=sattached == "1",
            )

        # Parse windows — associate with sessions via session_id in format
        for line in windows_raw.splitlines():
            fields = line.split(SEP)
            if len(fields) < 9:
                continue
            sid, wid, widx, wname, ww, wh, wpanes, wactive, wlayout = fields[:9]
            session = state.sessions.get(sid)
            if session is None:
                continue
            session.windows[wid] = TmuxWindow(
                window_id=wid,
                window_index=int(widx),
                name=wname,
                width=int(ww),
                height=int(wh),
                layout=wlayout,
                active=wactive == "1",
                pane_count=int(wpanes),
            )

        # Parse panes — associate with windows via window_id in format
        for line in panes_raw.splitlines():
            fields = line.split(SEP)
            if len(fields) < 12:
                continue
            (wid, pid, pidx, pw, ph, pt, pl, pb, pr,
             pactive, pcmd, ppid) = fields[:12]
            # Find the window this pane belongs to
            window = self._find_window(state, wid)
            if window is None:
                continue
            window.panes[pid] = TmuxPane(
                pane_id=pid,
                pane_index=int(pidx),
                width=int(pw),
                height=int(ph),
                top=int(pt),
                left=int(pl),
                bottom=int(pb),
                right=int(pr),
                active=pactive == "1",
                current_command=pcmd,
                pid=int(ppid),
            )

        self._states[host_name] = state
        self.state_changed.emit(host_name)
        return state

    @staticmethod
    def _find_window(state: TmuxState, window_id: str) -> TmuxWindow | None:
        """Look up a window by ID across all sessions."""
        for session in state.sessions.values():
            if window_id in session.windows:
                return session.windows[window_id]
        return None

    async def capture_pane(
        self, host_name: str, pane_id: str, history: bool = False
    ) -> str:
        """Capture visible content (or full history) of a pane."""
        args = ["capture-pane", "-t", pane_id, "-p", "-e"]
        if history:
            args.extend(["-S", "-"])
        return await self._ssh.exec(host_name, _tmux_cmd(*args))

    async def capture_pane_lines(
        self, host_name: str, pane_id: str, line_count: int
    ) -> str:
        """Capture the last *line_count* lines of scrollback plus visible content."""
        args = ["capture-pane", "-t", pane_id, "-p", "-e", "-S", f"-{line_count}"]
        return await self._ssh.exec(host_name, _tmux_cmd(*args))

    # ---------- actions ----------

    async def select_window(
        self, host_name: str, session_name: str, window_index: int
    ) -> None:
        target = f"{session_name}:{window_index}"
        await self._ssh.exec(host_name, _tmux_cmd("select-window", "-t", target))

    async def select_pane(self, host_name: str, pane_id: str) -> None:
        await self._ssh.exec(host_name, _tmux_cmd("select-pane", "-t", pane_id))

    async def new_window(
        self, host_name: str, session_name: str, window_name: str = ""
    ) -> None:
        args = ["new-window", "-t", session_name]
        if window_name:
            args.extend(["-n", window_name])
        await self._ssh.exec(host_name, _tmux_cmd(*args))

    async def split_pane(
        self, host_name: str, pane_id: str, horizontal: bool = True
    ) -> None:
        direction = "-h" if horizontal else "-v"
        await self._ssh.exec(
            host_name, _tmux_cmd("split-window", direction, "-t", pane_id)
        )

    async def kill_pane(self, host_name: str, pane_id: str) -> None:
        await self._ssh.exec(host_name, _tmux_cmd("kill-pane", "-t", pane_id))

    async def kill_window(
        self, host_name: str, session_name: str, window_index: int
    ) -> None:
        target = f"{session_name}:{window_index}"
        await self._ssh.exec(host_name, _tmux_cmd("kill-window", "-t", target))

    async def resize_pane(
        self, host_name: str, pane_id: str, width: int, height: int
    ) -> None:
        if width < 1 or height < 1:
            raise ValueError(f"Invalid pane dimensions: {width}x{height}")
        await self._ssh.exec(
            host_name,
            _tmux_cmd("resize-pane", "-t", pane_id, "-x", str(width), "-y", str(height)),
        )

    async def zoom_pane(self, host_name: str, pane_id: str) -> None:
        await self._ssh.exec(host_name, _tmux_cmd("resize-pane", "-t", pane_id, "-Z"))

    async def rename_window(
        self, host_name: str, session_name: str, window_index: int, new_name: str
    ) -> None:
        target = f"{session_name}:{window_index}"
        await self._ssh.exec(
            host_name, _tmux_cmd("rename-window", "-t", target, new_name)
        )

    async def new_session(self, host_name: str, session_name: str) -> None:
        await self._ssh.exec(
            host_name, _tmux_cmd("new-session", "-d", "-s", session_name)
        )

    async def send_keys(self, host_name: str, pane_id: str, keys: str) -> None:
        await self._ssh.exec(
            host_name, _tmux_cmd("send-keys", "-t", pane_id, keys)
        )
