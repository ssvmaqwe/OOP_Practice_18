import json
from datetime import datetime, timedelta
from pathlib import Path
import pytest
from Core.characters import CharacterManager, CharacterProfile
from Core.combatant import CombatantFactory
from Core.game import Game
from Core.saves import SaveManager, ProfileStorage, SaveError, migrate_legacy, AUTOSAVE_SLOT
from Core.stats import Stats
from Infra.storage import (AppDataLocator, JsonFileStore, JsonProfileRepository, JsonGameRepository,
                           LegacyRepositoryFile)


def new_game():
    hero = CombatantFactory.from_profile(CharacterProfile("w", "Воїн", "Воїн", Stats(200, 40, 0, 10)), "h1")
    game = Game()
    game.start([hero], [CombatantFactory.from_template("goblin", "e1")])
    return game


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 24, 12, 0, 0)

    def __call__(self):
        self.now += timedelta(minutes=1)
        return self.now


def test_app_data_locations():
    home = Path("/home/anna")
    assert AppDataLocator.resolve({}, "linux", home) == home / ".local/share/oop-text-game"
    assert AppDataLocator.resolve({"XDG_DATA_HOME": "/data"}, "linux", home) == Path("/data/oop-text-game")
    assert AppDataLocator.resolve({"APPDATA": "C:/Users/anna/AppData/Roaming"}, "win32", home) == \
        Path("C:/Users/anna/AppData/Roaming/OOPTextGame")
    assert AppDataLocator.resolve({}, "darwin", home) == home / "Library/Application Support/OOPTextGame"
    assert AppDataLocator.resolve({"OOP_GAME_HOME": "/tmp/g"}, "win32", home) == Path("/tmp/g")


def test_file_envelope_and_atomic_write(tmp_path):
    store = JsonFileStore(tmp_path)
    store.write("saves/a.json", "save", {"x": 1})
    raw = json.loads((tmp_path / "saves/a.json").read_text(encoding="utf-8"))
    assert raw["format"] == "oop-text-game" and raw["version"] == 3 and raw["kind"] == "save"
    assert raw["data"] == {"x": 1}
    assert not list(tmp_path.rglob("*.tmp"))
    assert store.read("saves/a.json", "characters") is None


def test_corrupted_file_is_quarantined(tmp_path):
    store = JsonFileStore(tmp_path)
    (tmp_path / "characters.json").write_text("{ broken", encoding="utf-8")
    assert JsonProfileRepository(store).load_profiles() == []
    assert (tmp_path / "characters.json.corrupt").exists()
    assert store.warnings


def test_save_load_roundtrip_and_latest(tmp_path):
    saves = SaveManager(JsonGameRepository(JsonFileStore(tmp_path)), Clock())
    game = new_game()
    saves.save(game, "first")
    game.act("attack", "e1")
    saves.autosave(game)
    latest = saves.latest()
    assert latest.slot == AUTOSAVE_SLOT and latest.turn == game.current_turn.number
    restored = saves.load(latest.slot)
    assert restored.get("e1").hp == game.get("e1").hp
    assert restored.current_actor.uid == game.current_actor.uid
    assert [s.slot for s in saves.list_saves()] == [AUTOSAVE_SLOT, "first"]


def test_save_errors(tmp_path):
    saves = SaveManager(JsonGameRepository(JsonFileStore(tmp_path)))
    with pytest.raises(SaveError):
        saves.save(Game(), "slot1")
    with pytest.raises(SaveError):
        saves.save(new_game(), "bad slot!")
    with pytest.raises(SaveError):
        saves.load("missing")
    (tmp_path / "saves").mkdir()
    (tmp_path / "saves" / "broken.json").write_text("not json", encoding="utf-8")
    with pytest.raises(SaveError):
        saves.load("broken")


def test_only_user_profiles_are_written(tmp_path):
    repo = JsonProfileRepository(JsonFileStore(tmp_path))
    manager = CharacterManager()
    storage = ProfileStorage(manager, repo)
    storage.load([CharacterProfile("b1", "Base", "Воїн", Stats())])
    manager.add_character(CharacterProfile("u1", "User", "Маг", Stats(magic=30)))
    assert storage.save() == 1
    assert [p["id"] for p in repo.load_profiles()] == ["u1"]

    manager2 = CharacterManager()
    ProfileStorage(manager2, repo).load([CharacterProfile("b1", "Base", "Воїн", Stats())])
    assert {p.id for p in manager2.get_all()} == {"b1", "u1"}
    with pytest.raises(SaveError):
        ProfileStorage(manager2, repo).delete("b1")


def test_legacy_migration(tmp_path):
    old_game = new_game()
    legacy_path = tmp_path / "repository.json"
    legacy_path.write_text(json.dumps({
        "characters": [
            {"id": "warrior_1", "name": "Артур", "char_class": "Воїн", "hp": 120, "attack": 28},
            {"id": "rogue", "name": "Тінь", "char_class": "Лучник", "hp": 90, "attack": 20},
        ],
        "game_state": old_game.to_config().to_dict(),
    }, ensure_ascii=False), encoding="utf-8")

    store = JsonFileStore(tmp_path / "data")
    manager = CharacterManager()
    storage = ProfileStorage(manager, JsonProfileRepository(store))
    storage.load([CharacterProfile("warrior_1", "Артур", "Воїн", Stats())])
    saves = SaveManager(JsonGameRepository(store))
    legacy = LegacyRepositoryFile(legacy_path)
    messages = migrate_legacy(legacy.read(), storage, saves, legacy.modified_at())
    legacy.mark_migrated()

    assert len(messages) == 2
    assert [p.id for p in storage.user_profiles()] == ["rogue"]
    assert saves.load("imported").get("e1").hp == old_game.get("e1").hp
    assert not legacy_path.exists() and (tmp_path / "repository.json.migrated").exists()


def test_old_practice13_state_is_skipped(tmp_path):
    store = JsonFileStore(tmp_path)
    storage = ProfileStorage(CharacterManager(), JsonProfileRepository(store))
    saves = SaveManager(JsonGameRepository(store))
    messages = migrate_legacy({"game_state": {"enemy_hp": 50, "turn": 3}}, storage, saves, "2026-11-01T10:00:00")
    assert "застарілий" in messages[0]
    assert saves.list_saves() == []
