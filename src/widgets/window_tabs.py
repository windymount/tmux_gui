"""Window tab bar — one tab per tmux window in the active session.

Tab colors reflect tmux window-status-style colors.
Auto-adjusts text color for contrast against dark/light backgrounds.
Includes a + button to create new windows.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QTabBar, QWidget

from src.core.tmux_state import TmuxWindow


def _luminance(color: QColor) -> float:
    """Compute relative luminance (0=black, 1=white) per WCAG formula."""
    r, g, b = color.redF(), color.greenF(), color.blueF()

    def linearize(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def _contrast_text(bg_hex: str) -> str:
    """Return '#ffffff' or '#000000' for best readability on *bg_hex*."""
    if not bg_hex:
        return ""
    return "#ffffff" if _luminance(QColor(bg_hex)) < 0.4 else "#000000"


class WindowTabBar(QWidget):
    """Horizontal tab bar for switching between tmux windows.

    Each tab has a close button and colors matching the tmux status bar.
    A + button at the end creates new windows.
    """

    tab_selected = Signal(int)  # window_index
    tab_close_requested = Signal(int)  # window_index
    new_window_requested = Signal()  # + button clicked

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tab_bar = QTabBar()
        self._tab_bar.setExpanding(False)
        self._tab_bar.setTabsClosable(True)
        self._tab_bar.setDocumentMode(True)
        self._tab_bar.currentChanged.connect(self._on_current_changed)
        self._tab_bar.tabCloseRequested.connect(self._on_tab_close)
        layout.addWidget(self._tab_bar)

        # "+" button for new window
        self._add_btn = QPushButton("+")
        self._add_btn.setFixedSize(28, 28)
        self._add_btn.setToolTip("New Window (Ctrl+T)")
        self._add_btn.setStyleSheet(
            "QPushButton { font-weight: bold; font-size: 16px; border: none; }"
            "QPushButton:hover { background-color: #444444; color: white; border-radius: 4px; }"
        )
        self._add_btn.clicked.connect(self.new_window_requested.emit)
        layout.addWidget(self._add_btn)

        layout.addStretch()  # push everything left

        self._index_map: list[int] = []  # tab position -> window_index
        self._updating = False

    def set_windows(self, windows: dict[str, TmuxWindow]) -> None:
        """Rebuild tabs from window dict, applying tmux status colors."""
        self._updating = True
        self._tab_bar.blockSignals(True)

        while self._tab_bar.count():
            self._tab_bar.removeTab(0)
        self._index_map.clear()

        sorted_wins = sorted(windows.values(), key=lambda w: w.window_index)
        active_tab = 0

        tab_styles: list[tuple[str, str]] = []

        for i, win in enumerate(sorted_wins):
            flags = f" {win.flags}" if win.flags else ""
            label = f" {win.window_index}:{win.name}{flags} "
            self._tab_bar.addTab(label)
            self._index_map.append(win.window_index)
            tab_styles.append((win.style_fg, win.style_bg))

            if win.active:
                active_tab = i

        self._apply_colors(tab_styles, active_tab)

        if self._tab_bar.count() > 0:
            self._tab_bar.setCurrentIndex(active_tab)

        self._tab_bar.blockSignals(False)
        self._updating = False

    def _apply_colors(
        self, tab_styles: list[tuple[str, str]], active_tab: int
    ) -> None:
        """Apply tmux colors to tabs with auto-contrast for readability."""
        for i, (fg, bg) in enumerate(tab_styles):
            if fg:
                self._tab_bar.setTabTextColor(i, QColor(fg))
            elif bg:
                auto_fg = _contrast_text(bg)
                if auto_fg:
                    self._tab_bar.setTabTextColor(i, QColor(auto_fg))

        style_parts: list[str] = []
        active_bg = tab_styles[active_tab][1] if active_tab < len(tab_styles) else ""
        if active_bg:
            active_fg = tab_styles[active_tab][0] or _contrast_text(active_bg)
            fg_rule = f" color: {active_fg};" if active_fg else ""
            style_parts.append(
                f"QTabBar::tab:selected {{ background-color: {active_bg};{fg_rule} }}"
            )

        if style_parts:
            self._tab_bar.setStyleSheet("\n".join(style_parts))
        else:
            self._tab_bar.setStyleSheet("")

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
        self._tab_bar.setStyleSheet("")
        self._tab_bar.blockSignals(False)

    def _on_current_changed(self, tab_pos: int) -> None:
        if self._updating or tab_pos < 0 or tab_pos >= len(self._index_map):
            return
        self.tab_selected.emit(self._index_map[tab_pos])

    def _on_tab_close(self, tab_pos: int) -> None:
        if 0 <= tab_pos < len(self._index_map):
            self.tab_close_requested.emit(self._index_map[tab_pos])
