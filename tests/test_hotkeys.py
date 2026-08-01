import sys
from types import ModuleType

import pytest

from soundmaster.hotkeys import HotkeyManager


def test_start_reports_repair_action_when_keyboard_is_missing(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "keyboard", None)

    with pytest.raises(RuntimeError, match="setup_env.bat"):
        HotkeyManager().start({1: "alt+1"}, lambda _sound_id: None, {1: object()})


def test_start_registers_and_stop_removes_hotkeys(monkeypatch) -> None:
    registered: list[tuple[str, object]] = []
    removed: list[object] = []
    keyboard = ModuleType("keyboard")

    def add_hotkey(sequence: str, callback, suppress: bool):
        handle = {"sequence": sequence, "callback": callback, "suppress": suppress}
        registered.append((sequence, handle))
        return handle

    keyboard.add_hotkey = add_hotkey  # type: ignore[attr-defined]
    keyboard.remove_hotkey = removed.append  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "keyboard", keyboard)

    callback_ids: list[int] = []
    manager = HotkeyManager()
    manager.start({1: "alt+1", 2: "ctrl+2"}, callback_ids.append, {1: object()})

    assert manager.active is True
    assert [sequence for sequence, _handle in registered] == ["alt+1"]
    registered[0][1]["callback"]()
    assert callback_ids == [1]

    manager.stop()
    assert removed == [registered[0][1]]
    assert manager.active is False
