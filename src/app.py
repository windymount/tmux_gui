"""TmuxPilot application entry point.

Sets up the PySide6 + asyncio event loop via qasync and launches the main window.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from PySide6.QtWidgets import QApplication

from src.core.config import AppConfig
from src.main_window import MainWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("TmuxPilot")
    app.setOrganizationName("TmuxPilot")

    # Load config
    config = AppConfig.load()

    # Create main window
    window = MainWindow(config)
    window.show()

    # Integrate asyncio with Qt event loop via qasync
    try:
        import qasync

        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)
        with loop:
            loop.run_forever()
    except ImportError:
        logger.warning(
            "qasync not available — falling back to standard Qt event loop. "
            "Async SSH operations will not work."
        )
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
