from pathlib import Path

from soundmaster.data.library import SoundLibrary


def test_voice_profiles_can_share_a_sample(tmp_path: Path) -> None:
    library = SoundLibrary(tmp_path / "soundmaster.db")
    sample = tmp_path / "shared.wav"
    first = library.add_voice_profile("First setup", sample)
    second = library.add_voice_profile("Second setup", sample)

    assert first.id != second.id
    assert [profile.name for profile in library.voice_profiles()] == [
        "Second setup",
        "First setup",
    ]
    assert library.voice_profile_sample_references(sample) == 2
    library.delete_voice_profile(first.id)
    assert library.voice_profile_sample_references(sample) == 1
    library.close()


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
    reopened.clear_keybind(item.id)
    assert reopened.keybinds() == {}
    reopened.set_keybind(item.id, "Alt+1")
    assert reopened.preference("minimize_to_tray") == ""
    reopened.set_preference("minimize_to_tray", "true")
    assert reopened.preference("minimize_to_tray") == "true"
    generation = reopened.add_voice_generation(
        "Test voice", "Hello", audio, tmp_path / "generated.wav", "pocket-tts", duration_seconds=3.5
    )
    assert reopened.voice_generations("hello")[0].id == generation.id
    assert reopened.voice_generations("hello")[0].duration_seconds == 3.5
    assert reopened.avg_generation_time("pocket-tts") == 3.5
    assert reopened.avg_generation_time("nonexistent") is None

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
    updated_sample = tmp_path / "managed-sample-2.wav"
    updated = reopened.update_voice_profile(
        profile.id,
        name="Discord voice updated",
        ref_text="Salut",
        engine_key="qwen3-tts",
        language="French",
        settings={"temperature": 0.8},
        sample_path=updated_sample,
    )
    assert updated is not None
    assert updated.name == "Discord voice updated"
    assert updated.sample_path == str(updated_sample)
    deleted_sample = reopened.delete_voice_profile(profile.id)
    assert deleted_sample == updated_sample
    assert reopened.voice_profiles() == []
    reopened.close()


def test_generation_history_records_filters_and_deletes_by_voice(tmp_path: Path) -> None:
    """The history must say which voice spoke, filter on it, and be erasable."""

    library = SoundLibrary(tmp_path / "soundmaster.db")
    sample = tmp_path / "sample.wav"
    sample.write_bytes(b"RIFF")
    first = tmp_path / "a.wav"
    first.write_bytes(b"RIFF")
    second = tmp_path / "b.wav"
    second.write_bytes(b"RIFF")
    third = tmp_path / "c.wav"
    third.write_bytes(b"RIFF")

    library.add_voice_generation("a", "Bonjour tout le monde", sample, first,
                                 "pocket-tts", profile_name="Discord")
    library.add_voice_generation("b", "Attention derriere toi", sample, second,
                                 "pocket-tts", profile_name="Jeu")
    # A generation made without saving a voice keeps an empty profile.
    library.add_voice_generation("c", "Sans profil", sample, third, "pocket-tts")

    assert library.voice_generation_profiles() == ["Discord", "Jeu"]
    assert [g.profile_name for g in library.voice_generations()] == ["", "Jeu", "Discord"]

    # Filtering by voice.
    assert [g.title for g in library.voice_generations(profile_name="Discord")] == ["a"]
    assert len(library.voice_generations(profile_name="Jeu")) == 1
    assert len(library.voice_generations()) == 3

    # Searching covers the spoken text and the voice name, not just the title.
    assert [g.title for g in library.voice_generations("derriere")] == ["b"]
    assert [g.title for g in library.voice_generations("discord")] == ["a"]

    # Both filters combine.
    assert library.voice_generations("bonjour", "Jeu") == []

    removed = library.delete_voice_generation(
        library.voice_generations(profile_name="Discord")[0].id
    )
    assert removed == first
    assert len(library.voice_generations()) == 2

    remaining = library.clear_voice_generations()
    assert sorted(p.name for p in remaining) == ["b.wav", "c.wav"]
    assert library.voice_generations() == []
    assert library.voice_generation_profiles() == []
    library.close()


def test_history_columns_are_added_to_an_existing_database(tmp_path: Path) -> None:
    """An install created before the column must not break on upgrade."""

    import sqlite3

    database = tmp_path / "old.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE voice_generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            sample_path TEXT NOT NULL,
            output_path TEXT NOT NULL,
            model TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO voice_generations(title, text, sample_path, output_path, model)
        VALUES ('ancien', 'texte', 's.wav', 'o.wav', 'pocket-tts');
        """
    )
    connection.commit()
    connection.close()

    library = SoundLibrary(database)
    generations = library.voice_generations()

    assert len(generations) == 1
    assert generations[0].profile_name == ""
    assert generations[0].duration_seconds == 0.0
    library.close()


def test_deleting_a_sound_also_removes_its_shortcut(tmp_path: Path) -> None:
    library = SoundLibrary(tmp_path / "soundmaster.db")
    audio = tmp_path / "s.wav"
    audio.write_bytes(b"RIFF")
    sound = library.add_sound("Son", audio, favorite=True)
    library.set_keybind(sound.id, "alt+9")

    library.delete_sound(sound.id)

    assert library.sounds() == []
    assert library.keybinds() == {}
    library.close()
