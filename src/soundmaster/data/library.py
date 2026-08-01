"""Local SQLite storage for SoundMaster's soundboard data."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SoundItem:
    id: int
    title: str
    path: str
    source: str
    favorite: bool
    created_at: str
    last_used_at: str | None


@dataclass(frozen=True, slots=True)
class VoiceGeneration:
    id: int
    title: str
    text: str
    sample_path: str
    output_path: str
    model: str
    created_at: str


@dataclass(frozen=True, slots=True)
class VoiceProfile:
    id: int
    name: str
    sample_path: str
    ref_text: str
    engine_key: str
    language: str
    settings: dict[str, object]
    created_at: str


class SoundLibrary:
    """Small, dependency-free repository for local soundboard data."""

    SCHEMA_VERSION = 4

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.database_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                path TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL DEFAULT 'local',
                favorite INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_used_at TEXT
            );
            CREATE TABLE IF NOT EXISTS keybinds (
                sound_id INTEGER PRIMARY KEY,
                sequence TEXT NOT NULL,
                FOREIGN KEY(sound_id) REFERENCES sounds(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS voice_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sample_path TEXT NOT NULL,
                ref_text TEXT NOT NULL DEFAULT '',
                engine_key TEXT NOT NULL DEFAULT 'qwen3-tts',
                language TEXT NOT NULL DEFAULT 'Auto',
                settings_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS voice_generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                text TEXT NOT NULL,
                sample_path TEXT NOT NULL,
                output_path TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO schema_meta(key, value) VALUES ('version', '4')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value;
            """
        )
        self._migrate_voice_profiles_sample_paths()
        self._connection.execute(
            "INSERT INTO schema_meta(key, value) VALUES ('version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(self.SCHEMA_VERSION),),
        )
        self._connection.commit()

    def _migrate_voice_profiles_sample_paths(self) -> None:
        """Remove the legacy one-profile-per-sample constraint."""

        unique_sample_index = False
        for index in self._connection.execute("PRAGMA index_list('voice_profiles')").fetchall():
            if not bool(index["unique"]):
                continue
            columns = self._connection.execute(
                f"PRAGMA index_info('{str(index['name']).replace(chr(39), chr(39) * 2)}')"
            ).fetchall()
            if [str(column["name"]) for column in columns] == ["sample_path"]:
                unique_sample_index = True
                break
        if not unique_sample_index:
            return

        self._connection.execute("ALTER TABLE voice_profiles RENAME TO voice_profiles_legacy")
        self._connection.execute(
            """
            CREATE TABLE voice_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sample_path TEXT NOT NULL,
                ref_text TEXT NOT NULL DEFAULT '',
                engine_key TEXT NOT NULL DEFAULT 'qwen3-tts',
                language TEXT NOT NULL DEFAULT 'Auto',
                settings_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._connection.execute(
            """
            INSERT INTO voice_profiles
                (id, name, sample_path, ref_text, engine_key, language, settings_json, created_at)
            SELECT id, name, sample_path, ref_text, engine_key, language, settings_json, created_at
            FROM voice_profiles_legacy
            """
        )
        self._connection.execute("DROP TABLE voice_profiles_legacy")

    def close(self) -> None:
        self._connection.close()

    def add_sound(self, title: str, path: Path, source: str = "local", favorite: bool = True) -> SoundItem:
        self._connection.execute(
            """
            INSERT INTO sounds(title, path, source, favorite)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET title=excluded.title, source=excluded.source
            """,
            (title.strip() or path.stem, str(path), source, int(favorite)),
        )
        self._connection.commit()
        row = self._connection.execute("SELECT * FROM sounds WHERE path = ?", (str(path),)).fetchone()
        assert row is not None
        return self._item(row)

    def sounds(self, query: str = "", favorites_only: bool = False) -> list[SoundItem]:
        clauses = []
        parameters: list[object] = []
        if query.strip():
            clauses.append("LOWER(title) LIKE ?")
            parameters.append(f"%{query.strip().lower()}%")
        if favorites_only:
            clauses.append("favorite = 1")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._connection.execute(
            f"SELECT * FROM sounds {where} ORDER BY favorite DESC, COALESCE(last_used_at, created_at) DESC",
            parameters,
        ).fetchall()
        return [self._item(row) for row in rows]

    def set_favorite(self, sound_id: int, favorite: bool) -> None:
        self._connection.execute("UPDATE sounds SET favorite = ? WHERE id = ?", (int(favorite), sound_id))
        self._connection.commit()

    def record_use(self, sound_id: int) -> None:
        self._connection.execute(
            "UPDATE sounds SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?", (sound_id,)
        )
        self._connection.commit()

    def set_keybind(self, sound_id: int, sequence: str) -> None:
        self._connection.execute(
            "INSERT INTO keybinds(sound_id, sequence) VALUES (?, ?) "
            "ON CONFLICT(sound_id) DO UPDATE SET sequence=excluded.sequence",
            (sound_id, sequence.strip()),
        )
        self._connection.commit()

    def keybinds(self) -> dict[int, str]:
        rows = self._connection.execute("SELECT sound_id, sequence FROM keybinds").fetchall()
        return {int(row["sound_id"]): str(row["sequence"]) for row in rows}

    def clear_keybind(self, sound_id: int) -> None:
        """Remove the shortcut assigned to one favorite."""

        self._connection.execute("DELETE FROM keybinds WHERE sound_id = ?", (sound_id,))
        self._connection.commit()

    def set_preference(self, key: str, value: str) -> None:
        self._connection.execute(
            "INSERT INTO preferences(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self._connection.commit()

    def preference(self, key: str, default: str = "") -> str:
        row = self._connection.execute("SELECT value FROM preferences WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def add_voice_profile(
        self,
        name: str,
        sample_path: Path,
        ref_text: str = "",
        engine_key: str = "qwen3-tts",
        language: str = "Auto",
        settings: dict[str, object] | None = None,
    ) -> VoiceProfile:
        encoded_settings = json.dumps(settings or {}, ensure_ascii=False, sort_keys=True)
        cursor = self._connection.execute(
            """
            INSERT INTO voice_profiles(name, sample_path, ref_text, engine_key, language, settings_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                name.strip() or sample_path.stem,
                str(sample_path),
                ref_text.strip(),
                engine_key,
                language or "Auto",
                encoded_settings,
            ),
        )
        self._connection.commit()
        row = self._connection.execute(
            "SELECT * FROM voice_profiles WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        assert row is not None
        return self._voice_profile(row)

    def voice_profiles(self, query: str = "") -> list[VoiceProfile]:
        if query.strip():
            rows = self._connection.execute(
                "SELECT * FROM voice_profiles WHERE LOWER(name) LIKE ? ORDER BY id DESC",
                (f"%{query.strip().lower()}%",),
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM voice_profiles ORDER BY id DESC"
            ).fetchall()
        return [self._voice_profile(row) for row in rows]

    def update_voice_profile(
        self,
        profile_id: int,
        *,
        name: str,
        ref_text: str,
        engine_key: str,
        language: str,
        settings: dict[str, object],
        sample_path: Path | None = None,
    ) -> VoiceProfile | None:
        self._connection.execute(
            """
            UPDATE voice_profiles SET name=?, sample_path=COALESCE(?, sample_path),
                ref_text=?, engine_key=?, language=?, settings_json=?
            WHERE id=?
            """,
            (
                name.strip() or "Voix sans nom",
                str(sample_path) if sample_path is not None else None,
                ref_text.strip(),
                engine_key,
                language or "Auto",
                json.dumps(settings, ensure_ascii=False, sort_keys=True),
                profile_id,
            ),
        )
        self._connection.commit()
        row = self._connection.execute(
            "SELECT * FROM voice_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        return self._voice_profile(row) if row is not None else None

    def delete_voice_profile(self, profile_id: int) -> Path | None:
        row = self._connection.execute(
            "SELECT sample_path FROM voice_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if row is None:
            return None
        sample_path = Path(str(row["sample_path"]))
        self._connection.execute("DELETE FROM voice_profiles WHERE id = ?", (profile_id,))
        self._connection.commit()
        return sample_path

    def voice_profile_sample_references(self, sample_path: Path) -> int:
        """Return how many setups still refer to a sample path."""

        row = self._connection.execute(
            "SELECT COUNT(*) AS count FROM voice_profiles WHERE sample_path = ?",
            (str(sample_path),),
        ).fetchone()
        return int(row["count"]) if row is not None else 0

    def add_voice_generation(
        self, title: str, text: str, sample_path: Path, output_path: Path, model: str
    ) -> VoiceGeneration:
        cursor = self._connection.execute(
            "INSERT INTO voice_generations(title, text, sample_path, output_path, model) VALUES (?, ?, ?, ?, ?)",
            (title.strip() or "Voix générée", text, str(sample_path), str(output_path), model),
        )
        self._connection.commit()
        row = self._connection.execute(
            "SELECT * FROM voice_generations WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        assert row is not None
        return self._voice_generation(row)

    def voice_generations(self, query: str = "") -> list[VoiceGeneration]:
        if query.strip():
            rows = self._connection.execute(
                "SELECT * FROM voice_generations WHERE LOWER(title) LIKE ? "
                "OR LOWER(text) LIKE ? ORDER BY id DESC",
                (f"%{query.strip().lower()}%", f"%{query.strip().lower()}%"),
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM voice_generations ORDER BY id DESC"
            ).fetchall()
        return [self._voice_generation(row) for row in rows]

    @staticmethod
    def _voice_profile(row: sqlite3.Row) -> VoiceProfile:
        try:
            settings = json.loads(str(row["settings_json"]))
        except (TypeError, json.JSONDecodeError):
            settings = {}
        if not isinstance(settings, dict):
            settings = {}
        return VoiceProfile(
            id=int(row["id"]),
            name=str(row["name"]),
            sample_path=str(row["sample_path"]),
            ref_text=str(row["ref_text"]),
            engine_key=str(row["engine_key"]),
            language=str(row["language"]),
            settings=settings,
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _item(row: sqlite3.Row) -> SoundItem:
        return SoundItem(
            id=int(row["id"]),
            title=str(row["title"]),
            path=str(row["path"]),
            source=str(row["source"]),
            favorite=bool(row["favorite"]),
            created_at=str(row["created_at"]),
            last_used_at=row["last_used_at"],
        )

    @staticmethod
    def _voice_generation(row: sqlite3.Row) -> VoiceGeneration:
        return VoiceGeneration(
            id=int(row["id"]),
            title=str(row["title"]),
            text=str(row["text"]),
            sample_path=str(row["sample_path"]),
            output_path=str(row["output_path"]),
            model=str(row["model"]),
            created_at=str(row["created_at"]),
        )
