"""SoundMaster's dark studio visual system and lightweight motion helpers."""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QWidget

APP_STYLE = """
* {
    font-family: "Segoe UI";
    color: #e8eee9;
}
QMainWindow, QWidget {
    background: #080a09;
}
QLabel#eyebrow {
    color: #70d18b;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
}
QLabel#pageTitle {
    color: #f3f7f3;
    font-size: 26px;
    font-weight: 700;
}
QLabel#pageSubtitle, QLabel#muted {
    color: #829087;
}
QWidget#sidebar {
    background: #0b0e0c;
    border-right: 1px solid #1d2921;
}
QLabel#brandMark {
    color: #f0f7f1;
    font-size: 19px;
    font-weight: 700;
}
QLabel#brandMeta {
    color: #5d7564;
    font-size: 9px;
    letter-spacing: 2px;
}
QToolButton#advancedButton {
    color: #829087;
    border: 0;
    padding: 4px 0;
    text-align: left;
}
QToolButton#advancedButton:hover {
    color: #baf4c7;
}
QPushButton#navButton, QPushButton#settingsButton {
    text-align: left;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 12px 13px;
    color: #91a096;
    background: transparent;
}
QPushButton#navButton:hover, QPushButton#settingsButton:hover {
    color: #e8f5eb;
    background: #111a14;
    border-color: #203728;
}
QPushButton#navButton:checked {
    color: #baf4c7;
    background: #122219;
    border-color: #2c6240;
}
QWidget#soundCard, QWidget#myInstantCard, QWidget#downloadRow {
    background: #0f1511;
    border: 1px solid #203326;
    border-radius: 10px;
    padding: 4px;
}
QWidget#soundCard:hover, QWidget#myInstantCard:hover {
    border-color: #5aaa70;
    background: #121c15;
}
QWidget#downloadRow {
    padding: 8px;
}
QPushButton {
    color: #c9d8cc;
    background: #111713;
    border: 1px solid #263a2b;
    border-radius: 7px;
    padding: 9px 13px;
}
QPushButton:hover {
    color: #baf4c7;
    background: #17251a;
    border-color: #4a9a61;
}
QPushButton#primaryButton {
    color: #061009;
    background: #6ed18a;
    border: 1px solid #91e3a4;
    border-radius: 7px;
    padding: 10px 15px;
    font-weight: 700;
}
QPushButton#primaryButton:hover {
    background: #91e3a4;
}
QPushButton#primaryButton:pressed, QPushButton#secondaryButton:pressed {
    padding-top: 11px;
    padding-bottom: 9px;
}
QPushButton#secondaryButton, QPushButton#ghostButton {
    color: #d1dfd4;
    background: #111713;
    border: 1px solid #263a2b;
    border-radius: 7px;
    padding: 9px 13px;
}
QPushButton#secondaryButton:hover, QPushButton#ghostButton:hover {
    color: #baf4c7;
    background: #17251a;
    border-color: #4a9a61;
}
QLineEdit, QTextEdit, QComboBox, QTableWidget, QListWidget {
    color: #e8eee9;
    background: #0f1411;
    border: 1px solid #243329;
    border-radius: 7px;
    padding: 8px 10px;
    selection-background-color: #2d7143;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
    border-color: #6ed18a;
}
QGroupBox, QWidget#panel, QWidget#voiceAdvanced {
    color: #c9d8cc;
    background: #0d120f;
    border: 1px solid #1d2b21;
    border-radius: 10px;
    margin-top: 8px;
    padding: 12px;
}
QScrollArea {
    background: transparent;
    border: 0;
}
QProgressBar {
    min-height: 5px;
    max-height: 5px;
    border: 0;
    border-radius: 2px;
    background: #18231b;
    text-align: center;
}
QProgressBar::chunk {
    border-radius: 2px;
    background: #6ed18a;
}
QCheckBox {
    spacing: 8px;
    color: #aebdb1;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid #3a5541;
    border-radius: 3px;
    background: #0d120f;
}
QCheckBox::indicator:checked {
    background: #6ed18a;
    border-color: #91e3a4;
}
QStatusBar {
    color: #83a18a;
    background: #0b0e0c;
    border-top: 1px solid #17231a;
}
QHeaderView::section {
    color: #8ea493;
    background: #111812;
    border: 0;
    border-bottom: 1px solid #263a2b;
    padding: 8px;
}
QTableWidget {
    gridline-color: #1c2920;
}
QToolTip {
    color: #eff8f0;
    background: #111a14;
    border: 1px solid #3a6a47;
    padding: 5px;
}
"""


def animate_opacity(widget: QWidget, start: float, end: float, duration: int = 260) -> QPropertyAnimation:
    """Fade a widget without changing layout geometry; keep animation owned by widget."""

    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setDuration(duration)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    widget._soundmaster_animation = animation  # type: ignore[attr-defined]
    return animation
