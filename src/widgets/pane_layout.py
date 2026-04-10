"""Pane layout container — arranges PaneWidgets to mirror the tmux pane layout."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QFontMetricsF, QResizeEvent
from PySide6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from src.core.config import AppConfig
from src.core.tmux_state import LayoutNode, TmuxWindow, parse_layout
from src.widgets.pane_widget import PaneWidget

logger = logging.getLogger(__name__)


class PaneLayoutWidget(QWidget):
    """Displays the pane layout for one tmux window using nested QSplitters."""

    def __init__(self, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._pane_widgets: dict[str, PaneWidget] = {}  # pane_id -> widget
        self._active_pane_id: str | None = None
        self._current_window: TmuxWindow | None = None
        self._current_layout: str = ""  # track layout string to avoid needless rebuilds
        self._splitters: list[QSplitter] = []  # all splitters for signal tracking

        # Callbacks set by MainWindow
        self.on_pane_resize: object | None = None  # callable(pane_id, width, height)
        self.on_history_requested: object | None = None  # callable(pane_id, line_count)
        self.on_window_resize: object | None = None  # callable(cols, rows)

        # Measure monospace cell size for pixel-to-cell conversion
        font = QFont(config.font_family, config.font_size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        fm = QFontMetricsF(font)
        self._cell_width = fm.averageCharWidth()
        self._cell_height = fm.height()

        # Debounce resize events to avoid flooding tmux with resize commands
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(300)  # ms
        self._resize_timer.timeout.connect(self._emit_window_resize)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._root_widget: QWidget | None = None

    @property
    def active_pane_id(self) -> str | None:
        return self._active_pane_id

    def set_window(self, window: TmuxWindow) -> None:
        """Update the pane layout from a TmuxWindow.

        Only rebuilds widgets if the layout string actually changed.
        If only pane content/state changed, just updates the active indicator.
        """
        self._current_window = window

        if not window.layout:
            self._clear_layout()
            self._current_layout = ""
            return

        # Only rebuild if the layout structure actually changed
        if window.layout != self._current_layout:
            self._rebuild(window)
            self._current_layout = window.layout

        # Always update active pane indicator
        for pane in window.panes.values():
            if pane.active:
                self._set_active(pane.pane_id)
                break

    def clear(self) -> None:
        self._clear_layout()
        self._active_pane_id = None
        self._current_window = None
        self._current_layout = ""

    def update_pane_content(self, pane_id: str, content: str) -> None:
        """Update the displayed content for one pane."""
        widget = self._pane_widgets.get(pane_id)
        if widget:
            widget.set_content(content)

    def update_pane_history(self, pane_id: str, content: str) -> None:
        """Deliver scrollback history content to a pane widget."""
        widget = self._pane_widgets.get(pane_id)
        if widget:
            widget.set_history_content(content)

    def _rebuild(self, window: TmuxWindow) -> None:
        """Full rebuild of the splitter tree from a layout string."""
        self._clear_layout()

        try:
            tree = parse_layout(window.layout)
        except Exception:
            logger.warning("Failed to parse layout: %s", window.layout, exc_info=True)
            return

        # Map layout node integer IDs -> tmux pane_id strings like "%17"
        pane_id_map: dict[int, str] = {}
        for pane in window.panes.values():
            try:
                num = int(pane.pane_id.lstrip("%"))
                pane_id_map[num] = pane.pane_id
            except ValueError:
                pass

        root = self._build_widget(tree, pane_id_map)
        self._root_widget = root
        self._layout.addWidget(root)

    def _clear_layout(self) -> None:
        self._pane_widgets.clear()
        self._splitters.clear()
        if self._root_widget:
            self._layout.removeWidget(self._root_widget)
            self._root_widget.deleteLater()
            self._root_widget = None

    def _build_widget(
        self, node: LayoutNode, pane_id_map: dict[int, str]
    ) -> QWidget:
        """Recursively build QSplitter tree from LayoutNode tree."""
        if node.is_leaf:
            pane_id = pane_id_map.get(node.pane_id, f"%{node.pane_id}")
            pw = PaneWidget(
                pane_id=pane_id,
                font_family=self._config.font_family,
                font_size=self._config.font_size,
            )
            pw.clicked.connect(self._on_pane_clicked)
            pw.history_requested.connect(self._on_history_requested)
            self._pane_widgets[pane_id] = pw
            return pw

        # Internal node — create splitter
        orientation = (
            Qt.Orientation.Horizontal
            if node.split == "v"  # v = side-by-side = horizontal splitter
            else Qt.Orientation.Vertical  # h = stacked = vertical splitter
        )
        splitter = QSplitter(orientation)

        for child in node.children:
            child_widget = self._build_widget(child, pane_id_map)
            splitter.addWidget(child_widget)

        # Set proportional sizes based on child dimensions
        if node.split == "v":
            sizes = [c.width for c in node.children]
        else:
            sizes = [c.height for c in node.children]
        splitter.setSizes(sizes)

        # Track splitter for resize handling
        splitter.splitterMoved.connect(self._on_splitter_moved)
        self._splitters.append(splitter)

        return splitter

    def _on_pane_clicked(self, pane_id: str) -> None:
        self._set_active(pane_id)

    def _on_history_requested(self, pane_id: str, line_count: int) -> None:
        if self.on_history_requested:
            self.on_history_requested(pane_id, line_count)

    def _set_active(self, pane_id: str) -> None:
        if self._active_pane_id == pane_id:
            return
        # Deactivate previous
        if self._active_pane_id and self._active_pane_id in self._pane_widgets:
            self._pane_widgets[self._active_pane_id].set_active(False)
        # Activate new
        self._active_pane_id = pane_id
        if pane_id in self._pane_widgets:
            self._pane_widgets[pane_id].set_active(True)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Debounce widget resize into a tmux window resize command."""
        super().resizeEvent(event)
        if self._current_window and self.on_window_resize:
            self._resize_timer.start()  # restart debounce

    def _emit_window_resize(self) -> None:
        """Convert widget pixel size to tmux cell dimensions and notify."""
        if not self.on_window_resize or self._cell_width <= 0 or self._cell_height <= 0:
            return
        cols = max(1, int(self.width() / self._cell_width))
        rows = max(1, int(self.height() / self._cell_height))
        self.on_window_resize(cols, rows)

    def _on_splitter_moved(self, pos: int, index: int) -> None:
        """When user drags a splitter, sync the new sizes back to tmux."""
        if not self._current_window or not self.on_pane_resize:
            return

        # Collect current pixel sizes of all pane widgets and translate
        # to proportional tmux cell sizes
        window = self._current_window
        if not window.panes:
            return

        # Calculate the ratio between Qt pixels and tmux cells
        total_qt_w = self.width() if self.width() > 0 else 1
        total_qt_h = self.height() if self.height() > 0 else 1
        tmux_w = window.width if window.width > 0 else 80
        tmux_h = window.height if window.height > 0 else 24

        for pane_id, widget in self._pane_widgets.items():
            qt_w = widget.width()
            qt_h = widget.height()
            # Convert Qt pixel size to tmux cell count
            new_w = max(1, round(qt_w / total_qt_w * tmux_w))
            new_h = max(1, round(qt_h / total_qt_h * tmux_h))
            self.on_pane_resize(pane_id, new_w, new_h)
