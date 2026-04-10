"""Settings dialog — configure font, poll intervals, and theme."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QGroupBox,
    QSpinBox,
    QVBoxLayout,
)

from src.core.config import AppConfig


class SettingsDialog(QDialog):
    """Modal dialog for application settings."""

    def __init__(self, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(400)
        self._config = config
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Font group
        font_group = QGroupBox("Font")
        font_form = QFormLayout()

        self._font_combo = QFontComboBox()
        self._font_combo.setCurrentFont(
            __import__("PySide6.QtGui", fromlist=["QFont"]).QFont(self._config.font_family)
        )
        font_form.addRow("&Font Family:", self._font_combo)

        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(6, 32)
        self._font_size_spin.setValue(self._config.font_size)
        font_form.addRow("Font &Size:", self._font_size_spin)

        font_group.setLayout(font_form)
        layout.addWidget(font_group)

        # Polling group
        poll_group = QGroupBox("Polling Intervals (ms)")
        poll_form = QFormLayout()

        self._structure_spin = QSpinBox()
        self._structure_spin.setRange(1000, 30000)
        self._structure_spin.setSingleStep(500)
        self._structure_spin.setValue(self._config.poll.structure_interval_ms)
        poll_form.addRow("&Structure Poll:", self._structure_spin)

        self._active_spin = QSpinBox()
        self._active_spin.setRange(200, 5000)
        self._active_spin.setSingleStep(100)
        self._active_spin.setValue(self._config.poll.active_pane_interval_ms)
        poll_form.addRow("&Active Pane Poll:", self._active_spin)

        poll_group.setLayout(poll_form)
        layout.addWidget(poll_group)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply_to_config(self) -> None:
        """Write dialog values back to the config object."""
        self._config.font_family = self._font_combo.currentFont().family()
        self._config.font_size = self._font_size_spin.value()
        self._config.poll.structure_interval_ms = self._structure_spin.value()
        self._config.poll.active_pane_interval_ms = self._active_spin.value()
