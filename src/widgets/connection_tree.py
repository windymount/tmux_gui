"""Left sidebar: server / session / window tree widget with context menus."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QMenu, QTreeWidget, QTreeWidgetItem

from src.core.tmux_state import TmuxState

# Custom data roles for storing metadata on tree items
ROLE_HOST = Qt.ItemDataRole.UserRole
ROLE_SESSION = Qt.ItemDataRole.UserRole + 1
ROLE_WINDOW = Qt.ItemDataRole.UserRole + 2


class ConnectionTree(QTreeWidget):
    """Expandable tree showing: host > session > window."""

    session_selected = Signal(str, str)  # host_name, session_name
    window_selected = Signal(str, str, int)  # host_name, session_name, window_index
    # Context menu action signals
    new_window_requested = Signal(str, str)  # host_name, session_name
    close_window_requested = Signal(str, str, int)  # host_name, session_name, window_index
    rename_window_requested = Signal(str, str, int)  # host_name, session_name, window_index
    new_session_requested = Signal(str)  # host_name

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderLabel("Connections")
        self.setMinimumWidth(180)
        self.itemClicked.connect(self._on_item_clicked)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

    def set_state(self, host_name: str, state: TmuxState) -> None:
        """Rebuild tree for one host from tmux state."""
        host_item = self._find_host_item(host_name)
        if host_item is None:
            host_item = QTreeWidgetItem(self, [host_name])
            host_item.setData(0, ROLE_HOST, host_name)
            host_item.setExpanded(True)
        else:
            host_item.takeChildren()

        session_count = len(state.sessions)
        host_item.setText(0, f"{host_name} ({session_count})")

        for session in state.session_list:
            s_label = f"{session.name} ({session.window_count} win)"
            s_item = QTreeWidgetItem(host_item, [s_label])
            s_item.setData(0, ROLE_HOST, host_name)
            s_item.setData(0, ROLE_SESSION, session.name)
            s_item.setExpanded(True)

            for window in sorted(session.windows.values(), key=lambda w: w.window_index):
                active_marker = " *" if window.active else ""
                w_label = f"{window.window_index}:{window.name}{active_marker}"
                w_item = QTreeWidgetItem(s_item, [w_label])
                w_item.setData(0, ROLE_HOST, host_name)
                w_item.setData(0, ROLE_SESSION, session.name)
                w_item.setData(0, ROLE_WINDOW, window.window_index)

    def clear(self) -> None:
        super().clear()

    def _find_host_item(self, host_name: str) -> QTreeWidgetItem | None:
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item and item.data(0, ROLE_HOST) == host_name:
                return item
        return None

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        host = item.data(0, ROLE_HOST)
        session_name = item.data(0, ROLE_SESSION)
        window_index = item.data(0, ROLE_WINDOW)

        if host is None or session_name is None:
            return

        if window_index is not None:
            self.window_selected.emit(host, session_name, window_index)
        else:
            self.session_selected.emit(host, session_name)

    def _on_context_menu(self, pos) -> None:
        item = self.itemAt(pos)
        if item is None:
            return

        host = item.data(0, ROLE_HOST)
        session_name = item.data(0, ROLE_SESSION)
        window_index = item.data(0, ROLE_WINDOW)

        menu = QMenu(self)

        if window_index is not None:
            # Right-clicked on a window
            act_rename = menu.addAction("Rename Window...")
            act_close = menu.addAction("Close Window")

            action = menu.exec(self.viewport().mapToGlobal(pos))
            if action == act_rename:
                self.rename_window_requested.emit(host, session_name, window_index)
            elif action == act_close:
                self.close_window_requested.emit(host, session_name, window_index)

        elif session_name is not None:
            # Right-clicked on a session
            act_new_win = menu.addAction("New Window")

            action = menu.exec(self.viewport().mapToGlobal(pos))
            if action == act_new_win:
                self.new_window_requested.emit(host, session_name)

        elif host is not None:
            # Right-clicked on a host
            act_new_session = menu.addAction("New Session...")

            action = menu.exec(self.viewport().mapToGlobal(pos))
            if action == act_new_session:
                self.new_session_requested.emit(host)
