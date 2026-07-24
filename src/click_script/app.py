from __future__ import annotations

import ctypes
import logging
import sys

from PySide6.QtWidgets import QApplication

from click_script.ui.main_window import MainWindow


def enable_windows_dpi_awareness() -> None:
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            logging.getLogger(__name__).debug("Unable to enable Windows DPI awareness")


def main() -> None:
    enable_windows_dpi_awareness()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Click Script")
    app.setOrganizationName("Click Script")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())
