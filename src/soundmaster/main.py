"""SoundMaster application entry point."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from soundmaster.core.config import load_config
from soundmaster.core.legal import load_legal_profile
from soundmaster.core.logger import setup_logging
from soundmaster.resources import get_app_icon
from soundmaster.ui.main_window import MainWindow
from soundmaster.version import __version__


def main() -> int:
    """Start the Step 1 bootstrap application."""

    config, paths = load_config()
    paths.ensure_runtime_directories()
    logger = setup_logging(paths.logs)
    logger.info("Starting %s", config.app_name)
    logger.info("Persistent data directory: %s", paths.data_dir)

    app = QApplication(sys.argv)
    app.setApplicationName(config.app_name)
    app.setApplicationVersion(__version__)
    icon = get_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    legal_profile = load_legal_profile(paths.legal_profile)
    window = MainWindow(legal_profile, paths.legal_profile, paths, config)
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    exit_code = app.exec()
    logger.info("Application exited with code %s", exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
