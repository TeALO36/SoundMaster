"""Windows global hotkey integration.

The dependency is imported lazily so SoundMaster can still show a useful startup
error if a manually copied or incomplete installation is missing it. Hook
callbacks only emit identifiers; the Qt UI owns the actual audio playback and
therefore remains on the GUI thread.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

_LOGGER = logging.getLogger(__name__)


class HotkeyManager:
    """Register configured key combinations through the bundled ``keyboard`` package."""

    def __init__(self) -> None:
        self.active = False
        self._keyboard: Any = None
        self._handles: list[Any] = []

    def start(
        self,
        bindings: dict[int, str],
        callback: Callable[[int], None],
        sounds: dict[int, object] | None = None,
    ) -> None:
        if self.active:
            return
        try:
            import keyboard
        except ImportError as error:
            raise RuntimeError(
                "Le composant Windows des raccourcis manque. "
                "Relancez setup_env.bat pour réparer l’installation de SoundMaster."
            ) from error
        if not bindings:
            raise RuntimeError("Aucun raccourci enregistré pour un favori.")

        available_ids = set(sounds or bindings)
        try:
            for sound_id, sequence in bindings.items():
                if sound_id not in available_ids or not sequence.strip():
                    continue
                handle = keyboard.add_hotkey(
                    sequence.strip(),
                    lambda selected_id=sound_id: callback(selected_id),
                    suppress=False,
                )
                self._handles.append(handle)
        except Exception as error:
            self.stop()
            raise RuntimeError(f"Impossible d’activer les raccourcis globaux : {error}") from error
        self._keyboard = keyboard
        self.active = bool(self._handles)
        if not self.active:
            raise RuntimeError("Aucun raccourci valide n’a pu être activé.")

    def stop(self) -> None:
        if self._keyboard is not None:
            for handle in self._handles:
                try:
                    self._keyboard.remove_hotkey(handle)
                except (RuntimeError, ValueError, KeyError) as error:
                    _LOGGER.debug("Could not remove global hotkey: %s", error)
        self._handles.clear()
        self._keyboard = None
        self.active = False
