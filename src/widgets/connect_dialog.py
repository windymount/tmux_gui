"""SSH connection dialog — collect host, port, username, key, password."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from src.core.config import ConnectionConfig


class ConnectDialog(QDialog):
    """Modal dialog for entering SSH connection details."""

    def __init__(self, parent=None, config: ConnectionConfig | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connect to Server")
        self.setMinimumWidth(420)

        self._build_ui()

        if config:
            self._populate(config)

    # ---------- UI construction ----------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("my-server")
        form.addRow("Connection &Name:", self._name_edit)

        self._host_edit = QLineEdit()
        self._host_edit.setPlaceholderText("192.168.1.100 or hostname")
        form.addRow("&Host:", self._host_edit)

        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(22)
        form.addRow("&Port:", self._port_spin)

        self._user_edit = QLineEdit()
        self._user_edit.setPlaceholderText("ubuntu")
        form.addRow("&Username:", self._user_edit)

        # Key file with browse button
        key_row = QHBoxLayout()
        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText("~/.ssh/id_rsa (optional)")
        key_row.addWidget(self._key_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_key)
        key_row.addWidget(browse_btn)
        form.addRow("&Key File:", key_row)

        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setPlaceholderText("(optional)")
        form.addRow("Pass&word:", self._password_edit)

        layout.addLayout(form)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate(self, config: ConnectionConfig) -> None:
        self._name_edit.setText(config.name)
        self._host_edit.setText(config.host)
        self._port_spin.setValue(config.port)
        self._user_edit.setText(config.username)
        self._key_edit.setText(config.key_file)

    # ---------- slots ----------

    def _browse_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select SSH Private Key",
            str(Path.home() / ".ssh"),
            "All Files (*)",
        )
        if path:
            self._key_edit.setText(path)

    def _validate_and_accept(self) -> None:
        if not self._name_edit.text().strip():
            self._name_edit.setFocus()
            return
        if not self._host_edit.text().strip():
            self._host_edit.setFocus()
            return
        self.accept()

    # ---------- result accessors ----------

    def get_connection_config(self) -> ConnectionConfig:
        return ConnectionConfig(
            name=self._name_edit.text().strip(),
            host=self._host_edit.text().strip(),
            port=self._port_spin.value(),
            username=self._user_edit.text().strip(),
            key_file=self._key_edit.text().strip(),
        )

    def get_password(self) -> str:
        return self._password_edit.text()
