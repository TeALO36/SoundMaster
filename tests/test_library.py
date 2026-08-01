from pathlib import Path

from soundmaster.data.library import SoundLibrary


def test_library_persists_favorites_history_and_keybinds(tmp_path: Path) -> None:
    database = tmp_path / "soundmaster.db"
    audio = tmp_path / "hello.wav"
    audio.write_bytes(b"RIFF")

    library = SoundLibrary(database)
    item = library.add_sound("Hello", audio, source="local")
    library.set_keybind(item.id, "Alt+1")
    library.record_use(item.id)
    library.set_favorite(item.id, False)
    library.close()

    reopened = SoundLibrary(database)
    loaded = reopened.sounds()[0]
    assert loaded.title == "Hello"
    assert loaded.favorite is False
    assert loaded.last_used_at is not None
    assert reopened.keybinds() == {item.id: "Alt+1"}
    assert reopened.preference("minimize_to_tray") == ""
    reopened.set_preference("minimize_to_tray", "true")
    assert reopened.preference("minimize_to_tray") == "true"
    generation = reopened.add_voice_generation(
        "Test voice", "Hello", audio, tmp_path / "generated.wav", "local-test"
    )
    assert reopened.voice_generations("hello")[0].id == generation.id

    profile = reopened.add_voice_profile(
        "Discord voice",
        tmp_path / "managed-sample.wav",
        ref_text="Bonjour",
        engine_key="omnivoice",
        language="French",
        settings={"temperature": 0.4, "speed": 1.1, "capture_output": "Headset"},
    )
    reopened.close()

    reopened = SoundLibrary(database)
    loaded_profile = reopened.voice_profiles()[0]
    assert loaded_profile.id == profile.id
    assert loaded_profile.name == "Discord voice"
    assert loaded_profile.engine_key == "omnivoice"
    assert loaded_profile.settings["temperature"] == 0.4
    assert loaded_profile.settings["capture_output"] == "Headset"
    deleted_sample = reopened.delete_voice_profile(profile.id)
    assert deleted_sample == tmp_path / "managed-sample.wav"
    assert reopened.voice_profiles() == []
    reopened.close()
