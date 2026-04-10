"""Window tab bar — one tab per tmux window in the active session."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTabBar, QWidget

from src.core.tmux_state import TmuxWindow


class WindowTabBar(QWidget):
    """Horizontal tab bar for switching between tmux windows."""

    tab_selected = Signal(int)  # window_index

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QHBoxLayout

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._tab_bar = QTabBar()
        self._tab_bar.setExpanding(False)
        self._tab_bar.currentChanged.connect(self._on_current_changed)
        layout.addWidget(self._tab_bar)

        self._index_map: list[int] = []  # tab position -> window_index
        self._updating = False

    def set_windows(self, windows: dict[str, TmuxWindow]) -> None:
        """Rebuild tabs from window dict."""
        self._updating = True
        self._tab_bar.blockSignals(True)

        # Clear existing
        while self._tab_bar.count():
            self._tab_bar.removeTab(0)
        self._index_map.clear()

        sorted_wins = sorted(windows.values(), key=lambda w: w.window_index)
        active_tab = 0
        for i, win in enumerate(sorted_wins):
            label = f"{win.window_index}:{win.name}"
            self._tab_bar.addTab(label)
            self._index_map.append(win.window_index)
            if win.active:
                active_tab = i

        if self._tab_bar.count() > 0:
            self._tab_bar.setCurrentIndex(active_tab)

        self._tab_bar.blockSignals(False)
        self._updating = False

    def select_by_index(self, window_index: int) -> None:
        """Programmatically select the tab for *window_index*."""
        self._tab_bar.blockSignals(True)
        for i, idx in enumerate(self._index_map):
            if idx == window_index:
                self._tab_bar.setCurrentIndex(i)
                break
        self._tab_bar.blockSignals(False)

    def clear(self) -> None:
        self._tab_bar.blockSignals(True)
        while self._tab_bar.count():
            self._tab_bar.removeTab(0)
        self._index_map.clear()
        self._tab_bar.blockSignals(False)

    def _on_current_changed(self, tab_pos: int) -> None:
        if self._updating or tab_pos < 0 or tab_pos >= len(self._index_map):
            return
        self.tab_selected.emit(self._index_map[tab_pos])
