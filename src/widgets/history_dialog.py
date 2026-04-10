"""Scrollback history viewer dialog with search."""

from __future__ import annotations

from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


class HistoryDialog(QDialog):
    """Modal dialog displaying full scrollback history of a pane."""

    def __init__(self, content: str, pane_id: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"History — {pane_id}")
        self.resize(800, 600)
        self.setMinimumSize(500, 300)

        layout = QVBoxLayout(self)

        # Search bar
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search:"))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Type to search...")
        self._search_edit.returnPressed.connect(self._find_next)
        search_row.addWidget(self._search_edit)

        self._find_btn = QPushButton("Find Next")
        self._find_btn.clicked.connect(self._find_next)
        search_row.addWidget(self._find_btn)

        self._match_label = QLabel("")
        search_row.addWidget(self._match_label)

        layout.addLayout(search_row)

        # Text viewer
        self._viewer = QPlainTextEdit()
        self._viewer.setReadOnly(True)
        self._viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._viewer.setFont(font)
        self._viewer.setStyleSheet(
            "QPlainTextEdit { background-color: #1e1e1e; color: #cccccc; }"
        )

        # Strip all ANSI escape sequences for plain text display
        from src.core.ansi_parser import strip_ansi

        self._viewer.setPlainText(strip_ansi(content))

        layout.addWidget(self._viewer)

        # Copy button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        copy_btn = QPushButton("Copy All")
        copy_btn.clicked.connect(self._copy_all)
        btn_row.addWidget(copy_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _find_next(self) -> None:
        query = self._search_edit.text()
        if not query:
            return
        found = self._viewer.find(query)
        if not found:
            # Wrap around to beginning
            cursor = self._viewer.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self._viewer.setTextCursor(cursor)
            found = self._viewer.find(query)

        self._match_label.setText("Found" if found else "Not found")

    def _copy_all(self) -> None:
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._viewer.toPlainText())
