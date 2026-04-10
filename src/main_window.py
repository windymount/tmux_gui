"""Main application window — menu bar, toolbar, status bar, central layout."""

from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.core.config import AppConfig, ConnectionConfig
from src.core.ssh_pool import ConnState, SSHPool
from src.core.tmux_manager import TmuxManager
from src.widgets.connect_dialog import ConnectDialog
from src.widgets.connection_tree import ConnectionTree
from src.widgets.pane_layout import PaneLayoutWidget
from src.widgets.window_tabs import WindowTabBar

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """TmuxPilot main window."""

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self._ssh_pool = SSHPool()
        self._tmux = TmuxManager(self._ssh_pool, parent=self)

        # Current selection state
        self._current_host: str | None = None
        self._current_session: str | None = None  # session name
        self._current_window_index: int | None = None

        self._setup_window()
        self._build_menus()
        self._build_toolbar()
        self._build_central()
        self._build_status_bar()
        self._connect_signals()
        self._setup_polling()

    # ---------- window setup ----------

    def _setup_window(self) -> None:
        self.setWindowTitle("TmuxPilot")
        self.resize(1100, 700)
        self.setMinimumSize(800, 500)

    # ---------- menus ----------

    def _build_menus(self) -> None:
        mb = self.menuBar()

        # File menu
        file_menu = mb.addMenu("&File")
        self._act_connect = file_menu.addAction("&Connect...")
        self._act_connect.setShortcut(QKeySequence("Ctrl+N"))
        self._act_connect.triggered.connect(self._on_connect)

        self._act_disconnect = file_menu.addAction("&Disconnect")
        self._act_disconnect.setEnabled(False)
        self._act_disconnect.triggered.connect(self._on_disconnect)

        file_menu.addSeparator()
        act_quit = file_menu.addAction("&Quit")
        act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        act_quit.triggered.connect(self.close)

        # Session menu
        session_menu = mb.addMenu("&Session")
        self._act_new_session = session_menu.addAction("New &Session...")
        self._act_new_session.setEnabled(False)
        self._act_new_session.triggered.connect(self._on_new_session)

        # Window menu
        window_menu = mb.addMenu("&Window")
        self._act_new_window = window_menu.addAction("&New Window")
        self._act_new_window.setShortcut(QKeySequence("Ctrl+T"))
        self._act_new_window.setEnabled(False)
        self._act_new_window.triggered.connect(self._on_new_window)

        self._act_close_window = window_menu.addAction("&Close Window")
        self._act_close_window.setShortcut(QKeySequence("Ctrl+W"))
        self._act_close_window.setEnabled(False)
        self._act_close_window.triggered.connect(self._on_close_window)

        self._act_rename_window = window_menu.addAction("&Rename Window...")
        self._act_rename_window.setEnabled(False)
        self._act_rename_window.triggered.connect(self._on_rename_window)

        # Pane menu
        pane_menu = mb.addMenu("&Pane")
        self._act_split_h = pane_menu.addAction("Split &Horizontal")
        self._act_split_h.setShortcut(QKeySequence("Ctrl+Shift+H"))
        self._act_split_h.setEnabled(False)
        self._act_split_h.triggered.connect(lambda: self._on_split(horizontal=True))

        self._act_split_v = pane_menu.addAction("Split &Vertical")
        self._act_split_v.setShortcut(QKeySequence("Ctrl+Shift+V"))
        self._act_split_v.setEnabled(False)
        self._act_split_v.triggered.connect(lambda: self._on_split(horizontal=False))

        self._act_close_pane = pane_menu.addAction("&Close Pane")
        self._act_close_pane.setEnabled(False)
        self._act_close_pane.triggered.connect(self._on_close_pane)

        self._act_zoom = pane_menu.addAction("&Zoom Toggle")
        self._act_zoom.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        self._act_zoom.setEnabled(False)
        self._act_zoom.triggered.connect(self._on_zoom)

        pane_menu.addSeparator()
        self._act_history = pane_menu.addAction("View &History...")
        self._act_history.setEnabled(False)
        self._act_history.triggered.connect(self._on_history)

    # ---------- toolbar ----------

    def _build_toolbar(self) -> None:
        tb = self.addToolBar("Main")
        tb.setMovable(False)

        tb.addAction(self._act_connect)
        tb.addAction(self._act_disconnect)
        tb.addSeparator()
        tb.addAction(self._act_new_window)
        tb.addAction(self._act_split_h)
        tb.addAction(self._act_split_v)
        tb.addSeparator()
        tb.addAction(self._act_close_pane)
        tb.addAction(self._act_zoom)
        tb.addAction(self._act_history)

    # ---------- central widget ----------

    def _build_central(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(2, 2, 2, 2)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: connection tree
        self._conn_tree = ConnectionTree()
        splitter.addWidget(self._conn_tree)

        # Right: tabs + pane layout
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self._window_tabs = WindowTabBar()
        right_layout.addWidget(self._window_tabs)

        self._pane_layout = PaneLayoutWidget(self._config)
        right_layout.addWidget(self._pane_layout, stretch=1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)  # tree: fixed
        splitter.setStretchFactor(1, 1)  # panes: stretch
        splitter.setSizes([220, 880])

        layout.addWidget(splitter)

    # ---------- status bar ----------

    def _build_status_bar(self) -> None:
        sb = self.statusBar()
        self._status_conn = QLabel("Disconnected")
        self._status_session = QLabel("")
        self._status_panes = QLabel("")
        sb.addWidget(self._status_conn, stretch=1)
        sb.addWidget(self._status_session)
        sb.addWidget(self._status_panes)

    # ---------- signals ----------

    def _connect_signals(self) -> None:
        self._ssh_pool.on_state_change.append(self._on_ssh_state_change)
        self._tmux.state_changed.connect(self._on_tmux_state_changed)
        self._conn_tree.session_selected.connect(self._on_tree_session_selected)
        self._conn_tree.window_selected.connect(self._on_tree_window_selected)
        self._window_tabs.tab_selected.connect(self._on_tab_selected)

    # ---------- polling ----------

    def _setup_polling(self) -> None:
        self._structure_timer = QTimer(self)
        self._structure_timer.setInterval(self._config.poll.structure_interval_ms)
        self._structure_timer.timeout.connect(self._poll_structure)

        self._content_timer = QTimer(self)
        self._content_timer.setInterval(self._config.poll.active_pane_interval_ms)
        self._content_timer.timeout.connect(self._poll_content)

    def _poll_structure(self) -> None:
        if self._current_host:
            self._run_async(self._tmux.refresh_structure(self._current_host))

    def _poll_content(self) -> None:
        if self._current_host and self._pane_layout.active_pane_id:
            self._run_async(self._refresh_pane_content())

    async def _refresh_pane_content(self) -> None:
        pane_id = self._pane_layout.active_pane_id
        if not pane_id or not self._current_host:
            return
        try:
            content = await self._tmux.capture_pane(self._current_host, pane_id)
            self._pane_layout.update_pane_content(pane_id, content)
        except Exception:
            logger.debug("Failed to capture pane %s", pane_id, exc_info=True)

    # ---------- action handlers ----------

    def _on_connect(self) -> None:
        dlg = ConnectDialog(self)
        if dlg.exec() != ConnectDialog.DialogCode.Accepted:
            return
        conn_cfg = dlg.get_connection_config()
        password = dlg.get_password()

        # Save to config if new
        if not self._config.find_connection(conn_cfg.name):
            self._config.add_connection(conn_cfg)
            self._config.save()

        self._run_async(self._do_connect(conn_cfg, password))

    async def _do_connect(self, conn_cfg: ConnectionConfig, password: str) -> None:
        try:
            await self._ssh_pool.connect(conn_cfg, password)
            self._current_host = conn_cfg.name
            state = await self._tmux.refresh_structure(conn_cfg.name)
            self._conn_tree.set_state(conn_cfg.name, state)

            # Auto-select the first session and its first window
            if state.session_list:
                first_session = state.session_list[0]
                self._current_session = first_session.name
                self._window_tabs.set_windows(first_session.windows)
                if first_session.windows:
                    first_win = min(
                        first_session.windows.values(), key=lambda w: w.window_index
                    )
                    self._current_window_index = first_win.window_index
                    self._pane_layout.set_window(first_win)

            self._structure_timer.start()
            self._content_timer.start()
            self._set_actions_enabled(True)
            self._update_status_bar()
        except Exception as exc:
            QMessageBox.critical(self, "Connection Failed", str(exc))

    def _on_disconnect(self) -> None:
        if self._current_host:
            self._structure_timer.stop()
            self._content_timer.stop()
            self._run_async(self._ssh_pool.disconnect(self._current_host))
            self._current_host = None
            self._current_session = None
            self._current_window_index = None
            self._conn_tree.clear()
            self._window_tabs.clear()
            self._pane_layout.clear()
            self._set_actions_enabled(False)
            self._update_status_bar()

    def _on_new_session(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New Session", "Session name:")
        if ok and name.strip() and self._current_host:
            self._run_async(self._tmux.new_session(self._current_host, name.strip()))

    def _on_new_window(self) -> None:
        if self._current_host and self._current_session:
            self._run_async(
                self._tmux.new_window(self._current_host, self._current_session)
            )

    def _on_close_window(self) -> None:
        has_target = (
            self._current_host
            and self._current_session
            and self._current_window_index is not None
        )
        if not has_target:
            return
        reply = QMessageBox.question(
            self, "Close Window",
            f"Close window {self._current_window_index} in session '{self._current_session}'?",
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._run_async(
                self._tmux.kill_window(
                    self._current_host, self._current_session, self._current_window_index
                )
            )

    def _on_rename_window(self) -> None:
        has_target = (
            self._current_host
            and self._current_session
            and self._current_window_index is not None
        )
        if not has_target:
            return
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Rename Window", "New name:")
        if ok and name.strip():
            self._run_async(
                self._tmux.rename_window(
                    self._current_host, self._current_session,
                    self._current_window_index, name.strip(),
                )
            )

    def _on_split(self, horizontal: bool) -> None:
        pane_id = self._pane_layout.active_pane_id
        if self._current_host and pane_id:
            self._run_async(
                self._tmux.split_pane(self._current_host, pane_id, horizontal)
            )

    def _on_close_pane(self) -> None:
        pane_id = self._pane_layout.active_pane_id
        if not (self._current_host and pane_id):
            return
        reply = QMessageBox.question(self, "Close Pane", f"Close pane {pane_id}?")
        if reply == QMessageBox.StandardButton.Yes:
            self._run_async(self._tmux.kill_pane(self._current_host, pane_id))

    def _on_zoom(self) -> None:
        pane_id = self._pane_layout.active_pane_id
        if self._current_host and pane_id:
            self._run_async(self._tmux.zoom_pane(self._current_host, pane_id))

    def _on_history(self) -> None:
        pane_id = self._pane_layout.active_pane_id
        if self._current_host and pane_id:
            self._run_async(self._show_history(pane_id))

    async def _show_history(self, pane_id: str) -> None:
        try:
            content = await self._tmux.capture_pane(
                self._current_host, pane_id, history=True
            )
            from src.widgets.history_dialog import HistoryDialog
            dlg = HistoryDialog(content, pane_id, self)
            dlg.exec()
        except Exception as exc:
            QMessageBox.warning(self, "History Error", str(exc))

    # ---------- signal handlers ----------

    def _on_ssh_state_change(self, host_name: str, state: ConnState) -> None:
        label = {
            ConnState.DISCONNECTED: "Disconnected",
            ConnState.CONNECTING: f"Connecting to {host_name}...",
            ConnState.CONNECTED: f"Connected: {host_name}",
        }[state]
        self._status_conn.setText(label)

    def _on_tmux_state_changed(self, host_name: str) -> None:
        state = self._tmux.get_state(host_name)
        if not state:
            return
        self._conn_tree.set_state(host_name, state)

        # Update window tabs for current session
        if self._current_session:
            session = state.find_session_by_name(self._current_session)
            if session:
                self._window_tabs.set_windows(session.windows)
                # Update pane layout for current window
                if self._current_window_index is not None:
                    for win in session.windows.values():
                        if win.window_index == self._current_window_index:
                            self._pane_layout.set_window(win)
                            break
        self._update_status_bar()

    def _on_tree_session_selected(self, host_name: str, session_name: str) -> None:
        self._current_host = host_name
        self._current_session = session_name
        state = self._tmux.get_state(host_name)
        if state:
            session = state.find_session_by_name(session_name)
            if session:
                self._window_tabs.set_windows(session.windows)
                # Select first window
                if session.windows:
                    first = min(session.windows.values(), key=lambda w: w.window_index)
                    self._current_window_index = first.window_index
                    self._pane_layout.set_window(first)
        self._update_status_bar()

    def _on_tree_window_selected(
        self, host_name: str, session_name: str, window_index: int
    ) -> None:
        self._current_host = host_name
        self._current_session = session_name
        self._current_window_index = window_index
        self._window_tabs.select_by_index(window_index)
        state = self._tmux.get_state(host_name)
        if state:
            session = state.find_session_by_name(session_name)
            if session:
                for win in session.windows.values():
                    if win.window_index == window_index:
                        self._pane_layout.set_window(win)
                        break
        if self._current_host:
            self._run_async(
                self._tmux.select_window(host_name, session_name, window_index)
            )
        self._update_status_bar()

    def _on_tab_selected(self, window_index: int) -> None:
        self._current_window_index = window_index
        if self._current_host and self._current_session:
            self._run_async(
                self._tmux.select_window(
                    self._current_host, self._current_session, window_index
                )
            )
            state = self._tmux.get_state(self._current_host)
            if state:
                session = state.find_session_by_name(self._current_session)
                if session:
                    for win in session.windows.values():
                        if win.window_index == window_index:
                            self._pane_layout.set_window(win)
                            break
        self._update_status_bar()

    # ---------- helpers ----------

    def _run_async(self, coro) -> None:
        """Schedule a coroutine with error logging."""
        task = asyncio.ensure_future(coro)
        task.add_done_callback(self._on_async_done)

    def _on_async_done(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error("Async task failed: %s", exc, exc_info=exc)
            self._status_conn.setText(f"Error: {exc}")

    def _set_actions_enabled(self, enabled: bool) -> None:
        self._act_disconnect.setEnabled(enabled)
        self._act_new_session.setEnabled(enabled)
        self._act_new_window.setEnabled(enabled)
        self._act_close_window.setEnabled(enabled)
        self._act_rename_window.setEnabled(enabled)
        self._act_split_h.setEnabled(enabled)
        self._act_split_v.setEnabled(enabled)
        self._act_close_pane.setEnabled(enabled)
        self._act_zoom.setEnabled(enabled)
        self._act_history.setEnabled(enabled)

    def _update_status_bar(self) -> None:
        session_text = f"Session: {self._current_session}" if self._current_session else ""
        self._status_session.setText(session_text)

        pane_text = ""
        if self._current_host and self._current_session and self._current_window_index is not None:
            state = self._tmux.get_state(self._current_host)
            if state:
                session = state.find_session_by_name(self._current_session)
                if session:
                    for win in session.windows.values():
                        if win.window_index == self._current_window_index:
                            pane_text = (
                                f"Window: {win.window_index}:{win.name} | "
                                f"{win.pane_count} pane(s)"
                            )
                            break
        self._status_panes.setText(pane_text)

    def closeEvent(self, event) -> None:
        self._structure_timer.stop()
        self._content_timer.stop()
        self._config.save()
        # Schedule graceful disconnect then quit
        self._run_async(self._shutdown())
        event.ignore()  # let _shutdown() call quit after awaiting disconnect

    async def _shutdown(self) -> None:
        """Gracefully close all SSH connections then quit the app."""
        try:
            await self._ssh_pool.disconnect_all()
        except Exception:
            logger.debug("Error during shutdown disconnect", exc_info=True)
        QApplication.quit()
