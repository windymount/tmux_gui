"""Single pane preview widget — displays captured pane content with ANSI colors.

Supports direct scrollback: scrolling up fetches tmux history via a signal,
and auto-scroll pauses while the user is browsing history.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QTextCharFormat, QTextCursor, QWheelEvent
from PySide6.QtWidgets import QFrame, QScrollBar, QTextEdit, QVBoxLayout

from src.core.ansi_parser import StyledSpan, parse_ansi


class PaneWidget(QFrame):
    """Displays the text content of a single tmux pane with ANSI color rendering.

    Signals:
        clicked(pane_id): user clicked on this pane
        history_requested(pane_id, line_count): user scrolled up, needs more history
    """

    clicked = Signal(str)  # pane_id
    history_requested = Signal(str, int)  # pane_id, how many lines of history to fetch

    # How many lines of history to fetch per scroll-up request
    HISTORY_CHUNK = 200
    HISTORY_MAX = 10000  # upper bound to prevent unbounded growth

    def __init__(
        self,
        pane_id: str,
        font_family: str = "Consolas",
        font_size: int = 10,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.pane_id = pane_id
        self._active = False
        self._last_content: str = ""
        self._browsing_history = False  # True when user has scrolled up
        self._history_lines: int = 0  # how many lines of history currently loaded
        self._history_content: str = ""  # full history text (when browsing)

        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Plain)
        self.setLineWidth(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text_edit.setFrameStyle(QFrame.Shape.NoFrame)
        self._text_edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        font = QFont(font_family, font_size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._text_edit.setFont(font)

        # Dark terminal background
        self._text_edit.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #cccccc; }"
        )

        # Track scroll position to detect user scrolling up / returning to bottom
        self._scrollbar: QScrollBar = self._text_edit.verticalScrollBar()
        self._scrollbar.valueChanged.connect(self._on_scroll_changed)

        layout.addWidget(self._text_edit)

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def is_browsing_history(self) -> bool:
        return self._browsing_history

    def set_active(self, active: bool) -> None:
        self._active = active
        color = "#4488ff" if active else "#555555"
        self.setStyleSheet(f"PaneWidget {{ border: 2px solid {color}; }}")

    def set_content(self, text: str) -> None:
        """Render live pane content (may contain ANSI SGR sequences).

        If the user is browsing history, live updates are suppressed —
        the display stays on the history view until they scroll back to bottom.
        """
        self._last_content = text
        if self._browsing_history:
            return  # don't overwrite history view with live content
        spans = parse_ansi(text)
        self._render_spans(spans, scroll_to_bottom=True)

    def set_history_content(self, text: str) -> None:
        """Render scrollback history content fetched from tmux."""
        self._history_content = text
        spans = parse_ansi(text)
        # Preserve approximate scroll position: remember distance from bottom
        sb = self._scrollbar
        was_at = sb.value()
        old_max = sb.maximum()
        dist_from_bottom = old_max - was_at

        self._render_spans(spans, scroll_to_bottom=False)

        # Restore position relative to bottom (new content was prepended)
        new_max = sb.maximum()
        sb.setValue(max(0, new_max - dist_from_bottom))

    def set_plain_content(self, text: str) -> None:
        """Set plain text without ANSI parsing."""
        self._text_edit.setPlainText(text)

    def _render_spans(self, spans: list[StyledSpan], scroll_to_bottom: bool = True) -> None:
        """Rebuild the QTextEdit content from styled spans."""
        self._text_edit.clear()
        cursor = self._text_edit.textCursor()
        cursor.beginEditBlock()

        for span in spans:
            fmt = QTextCharFormat()

            if span.style.fg:
                fmt.setForeground(QColor(span.style.fg))
            else:
                fmt.setForeground(QColor("#cccccc"))

            if span.style.bg:
                fmt.setBackground(QColor(span.style.bg))

            if span.style.bold:
                fmt.setFontWeight(QFont.Weight.Bold)

            if span.style.italic:
                fmt.setFontItalic(True)

            if span.style.underline:
                fmt.setFontUnderline(True)

            if span.style.strikethrough:
                fmt.setFontStrikeOut(True)

            cursor.insertText(span.text, fmt)

        cursor.endEditBlock()

        if scroll_to_bottom:
            self._text_edit.moveCursor(QTextCursor.MoveOperation.End)

    def _on_scroll_changed(self, value: int) -> None:
        """Detect when user scrolls to bottom to exit history browsing mode."""
        if not self._browsing_history:
            return
        sb = self._scrollbar
        at_bottom = value >= sb.maximum() - 5  # small tolerance
        if at_bottom:
            self._browsing_history = False
            self._history_lines = 0
            self._history_content = ""
            # Re-render live content now that we're back at bottom
            if self._last_content:
                spans = parse_ansi(self._last_content)
                self._render_spans(spans, scroll_to_bottom=True)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Intercept scroll-up to request history from tmux."""
        sb = self._scrollbar
        scrolling_up = event.angleDelta().y() > 0

        if scrolling_up and sb.value() <= sb.minimum():
            # Already at the top of current content — request more history
            if self._history_lines >= self.HISTORY_MAX:
                event.accept()
                return  # capped — don't request more
            self._browsing_history = True
            self._history_lines = min(
                self._history_lines + self.HISTORY_CHUNK, self.HISTORY_MAX
            )
            self.history_requested.emit(self.pane_id, self._history_lines)
            event.accept()
            return

        if scrolling_up and not self._browsing_history:
            # User is scrolling up within current content — enter browse mode
            self._browsing_history = True

        super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.clicked.emit(self.pane_id)
        super().mousePressEvent(event)
