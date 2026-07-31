"""SoundMaster application entry point."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from soundmaster.core.config import load_config
from soundmaster.core.legal import load_legal_profile
from soundmaster.core.logger import setup_logging
from soundmaster.version import __version__
from soundmaster.ui.bootstrap_window import BootstrapWindow


def main() -> int:
    """Start the Step 1 bootstrap application."""

    config, paths = load_config()
    paths.ensure_runtime_directories()
    logger = setup_logging(paths.logs)
    logger.info("Starting %s bootstrap", config.app_name)
    logger.info("Persistent data directory: %s", paths.data_dir)

    app = QApplication(sys.argv)
    app.setApplicationName(config.app_name)
    app.setApplicationVersion(__version__)

    legal_profile = load_legal_profile(paths.legal_profile)
    window = BootstrapWindow(legal_profile, paths.legal_profile)
    window.show()
    exit_code = app.exec()
    logger.info("Application exited with code %s", exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
