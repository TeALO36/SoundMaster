"""Application resource loaders and assets management."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QIcon


def get_resource_dir() -> Path:
    """Return the directory containing application resources."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "soundmaster" / "resources"
    return Path(__file__).resolve().parent


def get_resource_path(filename: str) -> Path:
    """Return the absolute path to a resource file."""
    return get_resource_dir() / filename


def get_app_icon() -> QIcon:
    """Return the application QIcon."""
    icon_png = get_resource_path("icon.png")
    if icon_png.is_file():
        return QIcon(str(icon_png))
    icon_ico = get_resource_path("icon.ico")
    if icon_ico.is_file():
        return QIcon(str(icon_ico))
    return QIcon()


def get_settings_icon() -> QIcon:
    """Return the settings gear QIcon."""
    settings_png = get_resource_path("settings.png")
    if settings_png.is_file():
        return QIcon(str(settings_png))
    return QIcon()


_icon_cache: dict[str, QIcon] = {}


def get_icon(name: str) -> QIcon:
    """Return a themed SVG icon by base name (without extension).

    Icons are loaded from the resources directory and cached so that
    repeated calls for the same name share a single QIcon instance.
    Returns a null QIcon when the file is missing.
    """
    if name in _icon_cache:
        return _icon_cache[name]
    svg_path = get_resource_path(f"{name}.svg")
    icon = QIcon(str(svg_path)) if svg_path.is_file() else QIcon()
    _icon_cache[name] = icon
    return icon
