"""Settings dialog — configure terminal font, UI font, and poll intervals."""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
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
        self.setMinimumWidth(420)
        self._config = config
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Terminal font group (pane monospace font)
        term_group = QGroupBox("Terminal Font (Panes)")
        term_form = QFormLayout()

        self._term_font_combo = QFontComboBox()
        self._term_font_combo.setFontFilters(QFontComboBox.FontFilter.MonospacedFonts)
        self._term_font_combo.setCurrentFont(QFont(self._config.font_family))
        term_form.addRow("&Font Family:", self._term_font_combo)

        self._term_size_spin = QSpinBox()
        self._term_size_spin.setRange(6, 32)
        self._term_size_spin.setValue(self._config.font_size)
        term_form.addRow("Font &Size:", self._term_size_spin)

        term_group.setLayout(term_form)
        layout.addWidget(term_group)

        # UI font group (menus, tabs, tree, dialogs)
        ui_group = QGroupBox("UI Font (Menus, Tabs, Tree)")
        ui_form = QFormLayout()

        self._ui_default_check = QCheckBox("Use system default")
        self._ui_default_check.setChecked(not self._config.ui_font_family)
        self._ui_default_check.toggled.connect(self._on_ui_default_toggled)
        ui_form.addRow(self._ui_default_check)

        self._ui_font_combo = QFontComboBox()
        if self._config.ui_font_family:
            self._ui_font_combo.setCurrentFont(QFont(self._config.ui_font_family))
        self._ui_font_combo.setEnabled(bool(self._config.ui_font_family))
        ui_form.addRow("Font Fa&mily:", self._ui_font_combo)

        self._ui_size_spin = QSpinBox()
        self._ui_size_spin.setRange(7, 24)
        self._ui_size_spin.setValue(self._config.ui_font_size or 9)
        self._ui_size_spin.setEnabled(bool(self._config.ui_font_family))
        ui_form.addRow("Font Si&ze:", self._ui_size_spin)

        ui_group.setLayout(ui_form)
        layout.addWidget(ui_group)

        # Polling group
        poll_group = QGroupBox("Polling Intervals (ms)")
        poll_form = QFormLayout()

        self._structure_spin = QSpinBox()
        self._structure_spin.setRange(1000, 30000)
        self._structure_spin.setSingleStep(500)
        self._structure_spin.setValue(self._config.poll.structure_interval_ms)
        poll_form.addRow("&Structure Poll:", self._structure_spin)

        self._active_spin = QSpinBox()
        self._active_spin.setRange(100, 5000)
        self._active_spin.setSingleStep(50)
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

    def _on_ui_default_toggled(self, checked: bool) -> None:
        self._ui_font_combo.setEnabled(not checked)
        self._ui_size_spin.setEnabled(not checked)

    def apply_to_config(self) -> None:
        """Write dialog values back to the config object."""
        self._config.font_family = self._term_font_combo.currentFont().family()
        self._config.font_size = self._term_size_spin.value()
        if self._ui_default_check.isChecked():
            self._config.ui_font_family = ""
            self._config.ui_font_size = 0
        else:
            self._config.ui_font_family = self._ui_font_combo.currentFont().family()
            self._config.ui_font_size = self._ui_size_spin.value()
        self._config.poll.structure_interval_ms = self._structure_spin.value()
        self._config.poll.active_pane_interval_ms = self._active_spin.value()
