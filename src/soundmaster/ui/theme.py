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
QWidget#content {
    background: #080a09;
}
/* The QWidget rule above also matches labels, checkboxes and sliders, which
   would then punch opaque page-coloured holes into every card. Keep them
   transparent so they inherit whatever surface they sit on. */
QLabel, QCheckBox, QSlider, QToolButton, QSplitter {
    background: transparent;
}
QWidget#voiceSetupBar, QWidget#voiceActionBar, QWidget#voiceHistoryPanel {
    background: transparent;
}
QWidget#stepCard {
    background: #0d120f;
    border: 1px solid #1e2c23;
    border-radius: 12px;
}
QLabel#stepBadge {
    color: #061009;
    background: #6ed18a;
    border-radius: 13px;
    font-size: 13px;
    font-weight: 700;
}
QLabel#stepTitle {
    color: #f0f7f1;
    font-size: 15px;
    font-weight: 700;
}
QWidget#lockedCard {
    background: #0d120f;
    border: 1px solid #3a2a20;
    border-radius: 14px;
}
QWidget#consentPanel, QWidget#consentPanelHighlight {
    background: #0d120f;
    border: 1px solid #1e2c23;
    border-radius: 12px;
}
QWidget#consentPanelHighlight {
    border: 2px solid #6ed18a;
    background: #101a13;
}
QLabel#consentTitle {
    color: #f0f7f1;
    font-size: 17px;
    font-weight: 700;
}
QLabel#consentBody {
    color: #b8c8bc;
}
QLabel#dangerNote {
    color: #f0c9a8;
    background: #17110c;
    border: 1px solid #4a3524;
    border-radius: 8px;
    padding: 10px;
}
QCheckBox#consentCheck {
    color: #e8f5eb;
    font-weight: 600;
    padding: 4px 0;
}
QWidget#consentAction, QWidget#consentActionHighlight {
    background: #101a13;
    border: 1px solid #26402f;
    border-radius: 10px;
}
QWidget#consentActionHighlight {
    border: 2px solid #6ed18a;
    background: #13251a;
}
QLabel#redirectBanner {
    color: #cdeed7;
    background: #12241a;
    border: 1px solid #2c6240;
    border-left: 4px solid #6ed18a;
    border-radius: 8px;
    padding: 10px 12px;
}
QWidget#playerBar {
    background: #101711;
    border: 1px solid #24382b;
    border-radius: 10px;
}
QLabel#playerTitle {
    color: #d1dfd4;
}
QLabel#playerTime {
    color: #7f9186;
    font-size: 11px;
}
QPushButton#playerButton {
    color: #061009;
    background: #6ed18a;
    border: 1px solid #91e3a4;
    border-radius: 7px;
    font-size: 14px;
    font-weight: 700;
    min-height: 32px;
}
QPushButton#playerButton:hover {
    background: #91e3a4;
}
QPushButton#playerButton:disabled {
    color: #55665b;
    background: #131a15;
    border-color: #1c2a21;
}
QSlider#playerSlider::groove:horizontal {
    height: 4px;
    border-radius: 2px;
    background: #1c2a21;
}
QSlider#playerSlider::sub-page:horizontal {
    height: 4px;
    border-radius: 2px;
    background: #6ed18a;
}
QSlider#playerSlider::handle:horizontal {
    width: 12px;
    margin: -5px 0;
    border-radius: 6px;
    background: #baf4c7;
}
QSlider#playerSlider::handle:horizontal:disabled {
    background: #33473a;
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
QPushButton#navButton, QPushButton#settingsButton, QPushButton#navButtonLocked {
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
QPushButton#navButtonLocked {
    color: #55655a;
    border-style: dashed;
    border-color: transparent;
}
QPushButton#navButtonLocked:hover {
    color: #8a9a8f;
    background: #10150f;
    border-color: #34452f;
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
    min-height: 32px;
    padding: 6px 11px;
}
QPushButton:hover {
    color: #baf4c7;
    background: #17251a;
    border-color: #4a9a61;
}
QPushButton#recordingButton {
    color: #061009;
    background: #baf4c7;
    border-color: #d7f9df;
    font-weight: 700;
}
QPushButton#primaryButton {
    color: #061009;
    background: #6ed18a;
    border: 1px solid #91e3a4;
    border-radius: 7px;
    min-height: 34px;
    padding: 7px 13px;
    font-weight: 700;
}
QPushButton#primaryButton:hover, QPushButton#compactPrimaryButton:hover {
    background: #91e3a4;
}
QPushButton#compactPrimaryButton {
    color: #061009;
    background: #6ed18a;
    border: 1px solid #91e3a4;
    border-radius: 7px;
    min-height: 30px;
    padding: 5px 10px;
    font-weight: 700;
}
QPushButton#primaryButton:pressed, QPushButton#compactPrimaryButton:pressed,
QPushButton#secondaryButton:pressed, QPushButton#compactButton:pressed {
    background: #4fbb70;
}
QPushButton#secondaryButton, QPushButton#ghostButton {
    color: #d1dfd4;
    background: #111713;
    border: 1px solid #263a2b;
    border-radius: 7px;
    min-height: 32px;
    padding: 6px 11px;
}
QPushButton#compactButton, QPushButton#iconButton {
    min-height: 30px;
    padding: 5px 9px;
}
QPushButton#iconButton {
    min-width: 34px;
    max-width: 42px;
    padding-left: 5px;
    padding-right: 5px;
}
QPushButton#secondaryButton:hover, QPushButton#ghostButton:hover {
    color: #baf4c7;
    background: #17251a;
    border-color: #4a9a61;
}
QLineEdit, QComboBox, QTableWidget, QListWidget {
    color: #e8eee9;
    background: #0f1411;
    border: 1px solid #243329;
    border-radius: 7px;
    min-height: 32px;
    padding: 6px 9px;
    selection-background-color: #2d7143;
}
QTextEdit {
    padding: 10px;
}
QTextEdit#voiceText {
    min-height: 90px;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
    border-color: #6ed18a;
}
QLineEdit#compactSearch {
    min-height: 28px;
    padding: 4px 8px;
}
QLabel#sectionLabel {
    color: #c9d8cc;
    font-weight: 600;
}
QGroupBox, QWidget#panel, QWidget#voiceAdvanced {
    color: #c9d8cc;
    background: #0d120f;
    border: 1px solid #1d2b21;
    border-radius: 10px;
    margin-top: 8px;
    padding: 10px;
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
QScrollBar:vertical {
    width: 9px;
    margin: 0;
    border: 0;
    background: transparent;
}
QScrollBar:horizontal {
    height: 9px;
    margin: 0;
    border: 0;
    background: transparent;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    border-radius: 4px;
    background: #24382b;
}
QScrollBar::handle:vertical {
    min-height: 30px;
}
QScrollBar::handle:horizontal {
    min-width: 30px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: #3d6b4c;
}
QScrollBar::add-line, QScrollBar::sub-line {
    height: 0;
    width: 0;
    border: 0;
    background: transparent;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}
QTabWidget::pane {
    border: 1px solid #1d2b21;
    border-radius: 10px;
    top: -1px;
}
QTabBar::tab {
    color: #91a096;
    background: #0d120f;
    border: 1px solid #1d2b21;
    border-bottom: 0;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 8px 16px;
    margin-right: 3px;
}
QTabBar::tab:selected {
    color: #baf4c7;
    background: #122219;
    border-color: #2c6240;
}
QTabBar::tab:hover:!selected {
    color: #d1dfd4;
    background: #111a14;
}
"""


def animate_opacity(widget: QWidget, start: float, end: float, duration: int = 260) -> QPropertyAnimation:
    """Fade a page safely without stacking paint effects or animations.

    Cards intentionally use stylesheet hover states instead of this helper. Page
    transitions are infrequent, but navigation can still happen before a prior
    animation finishes; keeping one effect and one animation per widget avoids
    Qt's painter conflicts and stale effects.
    """

    previous = getattr(widget, "_soundmaster_animation", None)
    if isinstance(previous, QPropertyAnimation):
        previous.stop()

    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    effect.setOpacity(start)

    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setDuration(duration)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def finish() -> None:
        if getattr(widget, "_soundmaster_animation", None) is animation:
            effect.setOpacity(end)
            if end >= 1.0:
                widget.setGraphicsEffect(None)
            widget._soundmaster_animation = None  # type: ignore[attr-defined]

    animation.finished.connect(finish)
    widget._soundmaster_animation = animation  # type: ignore[attr-defined]
    animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return animation


def pulse_attention(
    widget: QWidget, loops: int = 3, duration: int = 620
) -> QPropertyAnimation:
    """Blink a widget so an automatic redirect is visibly explained.

    Landing on a settings page without a visual cue reads as an unexplained
    detour, so the row the user was sent to pulses instead of merely being
    scrolled into view. One effect and one animation per widget, like
    :func:`animate_opacity`.
    """

    previous = getattr(widget, "_soundmaster_pulse", None)
    if isinstance(previous, QPropertyAnimation):
        previous.stop()

    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    effect.setOpacity(1.0)

    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(1.0)
    animation.setKeyValueAt(0.5, 0.3)
    animation.setEndValue(1.0)
    animation.setLoopCount(loops)
    animation.setEasingCurve(QEasingCurve.Type.InOutSine)

    def finish() -> None:
        if getattr(widget, "_soundmaster_pulse", None) is animation:
            effect.setOpacity(1.0)
            widget.setGraphicsEffect(None)
            widget._soundmaster_pulse = None  # type: ignore[attr-defined]

    animation.finished.connect(finish)
    widget._soundmaster_pulse = animation  # type: ignore[attr-defined]
    animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return animation
