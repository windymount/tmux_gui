"""Single pane preview widget — displays captured pane content with ANSI colors."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QFrame, QTextEdit, QVBoxLayout

from src.core.ansi_parser import StyledSpan, parse_ansi


class PaneWidget(QFrame):
    """Displays the text content of a single tmux pane with ANSI color rendering.

    Emits ``clicked(pane_id)`` when the user clicks on the pane.
    """

    clicked = Signal(str)  # pane_id

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

        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Plain)
        self.setLineWidth(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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

        layout.addWidget(self._text_edit)

    @property
    def is_active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        self._active = active
        color = "#4488ff" if active else "#555555"
        self.setStyleSheet(f"PaneWidget {{ border: 2px solid {color}; }}")

    def set_content(self, text: str) -> None:
        """Render *text* (may contain ANSI SGR sequences) into the text widget."""
        if text == self._last_content:
            return  # skip re-render if content unchanged
        self._last_content = text
        spans = parse_ansi(text)
        self._render_spans(spans)

    def set_plain_content(self, text: str) -> None:
        """Set plain text without ANSI parsing."""
        self._text_edit.setPlainText(text)

    def _render_spans(self, spans: list[StyledSpan]) -> None:
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
        # Scroll to bottom (most recent output)
        self._text_edit.moveCursor(QTextCursor.MoveOperation.End)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.clicked.emit(self.pane_id)
        super().mousePressEvent(event)
