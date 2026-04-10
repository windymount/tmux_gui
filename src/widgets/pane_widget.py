"""Single pane preview widget — displays captured pane content with ANSI colors.

Supports direct scrollback: scrolling up fetches tmux history via a signal,
and auto-scroll pauses while the user is browsing history.
Accepts keyboard input and forwards it to tmux via send-keys.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QTextCharFormat,
    QTextCursor,
    QWheelEvent,
)
from PySide6.QtWidgets import QFrame, QScrollBar, QTextEdit, QVBoxLayout

from src.core.ansi_parser import StyledSpan, parse_ansi

# Map Qt keys to tmux send-keys key names
_QT_TO_TMUX: dict[int, str] = {
    Qt.Key.Key_Return: "Enter",
    Qt.Key.Key_Enter: "Enter",
    Qt.Key.Key_Backspace: "BSpace",
    Qt.Key.Key_Tab: "Tab",
    Qt.Key.Key_Escape: "Escape",
    Qt.Key.Key_Up: "Up",
    Qt.Key.Key_Down: "Down",
    Qt.Key.Key_Left: "Left",
    Qt.Key.Key_Right: "Right",
    Qt.Key.Key_Home: "Home",
    Qt.Key.Key_End: "End",
    Qt.Key.Key_PageUp: "PageUp",
    Qt.Key.Key_PageDown: "PageDown",
    Qt.Key.Key_Insert: "Insert",
    Qt.Key.Key_Delete: "DC",
    Qt.Key.Key_F1: "F1",
    Qt.Key.Key_F2: "F2",
    Qt.Key.Key_F3: "F3",
    Qt.Key.Key_F4: "F4",
    Qt.Key.Key_F5: "F5",
    Qt.Key.Key_F6: "F6",
    Qt.Key.Key_F7: "F7",
    Qt.Key.Key_F8: "F8",
    Qt.Key.Key_F9: "F9",
    Qt.Key.Key_F10: "F10",
    Qt.Key.Key_F11: "F11",
    Qt.Key.Key_F12: "F12",
}


class PaneWidget(QFrame):
    """Displays the text content of a single tmux pane with ANSI color rendering.

    Signals:
        clicked(pane_id): user clicked on this pane
        history_requested(pane_id, line_count): user scrolled up, needs more history
        keys_pressed(pane_id, keys): user typed something, forward to tmux
    """

    clicked = Signal(str)  # pane_id
    history_requested = Signal(str, int)  # pane_id, how many lines of history to fetch
    keys_pressed = Signal(str, str)  # pane_id, tmux key string

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
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text_edit.setFrameStyle(QFrame.Shape.NoFrame)
        self._text_edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        # Prevent the QTextEdit from stealing focus / key events
        self._text_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)

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
        if active:
            self.setFocus()

    def set_font_size(self, size: int) -> None:
        """Update the font size live."""
        font = self._text_edit.font()
        font.setPointSize(size)
        self._text_edit.setFont(font)

    def set_content(self, text: str) -> None:
        """Render live pane content (may contain ANSI SGR sequences)."""
        self._last_content = text
        if self._browsing_history:
            return
        spans = parse_ansi(text)
        self._render_spans(spans, scroll_to_bottom=True)

    def set_history_content(self, text: str) -> None:
        """Render scrollback history content fetched from tmux."""
        self._history_content = text
        spans = parse_ansi(text)
        sb = self._scrollbar
        was_at = sb.value()
        old_max = sb.maximum()
        dist_from_bottom = old_max - was_at

        self._render_spans(spans, scroll_to_bottom=False)

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

    # ---------- keyboard input forwarding ----------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Convert key events to tmux send-keys strings and emit."""
        if not self._active:
            super().keyPressEvent(event)
            return

        # While browsing history, any key exits history mode first
        if self._browsing_history:
            self._exit_history_mode()
            # If it was Enter or Escape, just return to live — don't send the key
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
                event.accept()
                return
            # Other keys: fall through to send to tmux after exiting history

        key = event.key()
        modifiers = event.modifiers()
        tmux_key = self._translate_key(key, modifiers, event.text())

        if tmux_key:
            self.keys_pressed.emit(self.pane_id, tmux_key)
            event.accept()
        else:
            super().keyPressEvent(event)

    @staticmethod
    def _translate_key(key: int, modifiers: Qt.KeyboardModifier, text: str) -> str:
        """Translate a Qt key event to a tmux send-keys argument."""
        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        alt = bool(modifiers & Qt.KeyboardModifier.AltModifier)

        # Special keys (arrows, function keys, etc.)
        if key in _QT_TO_TMUX:
            name = _QT_TO_TMUX[key]
            if ctrl:
                return f"C-{name}"
            if alt:
                return f"M-{name}"
            return name

        # Ctrl+letter -> C-a through C-z
        if ctrl and Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            letter = chr(key).lower()
            return f"C-{letter}"

        # Alt+printable
        if alt and text:
            return f"M-{text}"

        # Regular printable character
        if text and not ctrl:
            return text

        return ""

    # ---------- scroll / history ----------

    def _exit_history_mode(self) -> None:
        """Leave history browsing: restore live content and scroll to bottom."""
        self._browsing_history = False
        self._history_lines = 0
        self._history_content = ""
        if self._last_content:
            spans = parse_ansi(self._last_content)
            self._render_spans(spans, scroll_to_bottom=True)

    def _on_scroll_changed(self, value: int) -> None:
        """Detect when user scrolls to bottom to exit history browsing mode."""
        if not self._browsing_history:
            return
        sb = self._scrollbar
        at_bottom = value >= sb.maximum() - 5
        if at_bottom:
            self._exit_history_mode()

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Intercept scroll-up to request history from tmux."""
        sb = self._scrollbar
        scrolling_up = event.angleDelta().y() > 0

        if scrolling_up and sb.value() <= sb.minimum():
            if self._history_lines >= self.HISTORY_MAX:
                event.accept()
                return
            self._browsing_history = True
            self._history_lines = min(
                self._history_lines + self.HISTORY_CHUNK, self.HISTORY_MAX
            )
            self.history_requested.emit(self.pane_id, self._history_lines)
            event.accept()
            return

        if scrolling_up and not self._browsing_history:
            self._browsing_history = True

        super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.clicked.emit(self.pane_id)
        self.setFocus()
        super().mousePressEvent(event)
