import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication  # noqa: E402

from soundmaster.core.legal import LegalProfile  # noqa: E402
from soundmaster.ui.legal_settings import LegalSettingsWidget, SettingsWindow  # noqa: E402


@pytest.fixture
def qapp() -> QApplication:
    application = QApplication.instance() or QApplication([])
    return application


def test_legal_settings_panel_builds_offscreen(qapp: QApplication, tmp_path: Path) -> None:
    widget = LegalSettingsWidget(LegalProfile(), tmp_path / "legal_profile.json")
    window = SettingsWindow(widget)

    assert widget.status_label.text()
    assert "Non prêt à commercialiser" in widget.status_label.text()
    assert window.windowTitle() == "SoundMaster — Paramètres"

    window.close()
