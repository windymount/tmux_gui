"""Pane layout container — arranges PaneWidgets to mirror the tmux pane layout."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
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

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._root_widget: QWidget | None = None

    @property
    def active_pane_id(self) -> str | None:
        return self._active_pane_id

    def set_window(self, window: TmuxWindow) -> None:
        """Rebuild the pane layout from a TmuxWindow's layout string."""
        self._current_window = window
        self._clear_layout()

        if not window.layout:
            return

        try:
            tree = parse_layout(window.layout)
        except Exception:
            logger.warning("Failed to parse layout: %s", window.layout, exc_info=True)
            return

        # Collect pane_ids from window data for mapping layout nodes
        # Layout nodes have integer pane IDs; TmuxPane IDs are like "%17"
        pane_id_map: dict[int, str] = {}
        for pane in window.panes.values():
            # Extract numeric part from pane_id like "%17"
            try:
                num = int(pane.pane_id.lstrip("%"))
                pane_id_map[num] = pane.pane_id
            except ValueError:
                pass

        root = self._build_widget(tree, pane_id_map)
        self._root_widget = root
        self._layout.addWidget(root)

        # Set active pane
        for pane in window.panes.values():
            if pane.active:
                self._set_active(pane.pane_id)
                break

    def clear(self) -> None:
        self._clear_layout()
        self._active_pane_id = None
        self._current_window = None

    def update_pane_content(self, pane_id: str, content: str) -> None:
        """Update the displayed content for one pane."""
        widget = self._pane_widgets.get(pane_id)
        if widget:
            widget.set_content(content)

    def _clear_layout(self) -> None:
        self._pane_widgets.clear()
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

        return splitter

    def _on_pane_clicked(self, pane_id: str) -> None:
        self._set_active(pane_id)

    def _set_active(self, pane_id: str) -> None:
        # Deactivate previous
        if self._active_pane_id and self._active_pane_id in self._pane_widgets:
            self._pane_widgets[self._active_pane_id].set_active(False)
        # Activate new
        self._active_pane_id = pane_id
        if pane_id in self._pane_widgets:
            self._pane_widgets[pane_id].set_active(True)
