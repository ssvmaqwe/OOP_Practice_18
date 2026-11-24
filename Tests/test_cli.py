from CLI.presenter import CLI, ArgParser
from CLI.commands import CatalogStrategy, GameStrategy, SystemStrategy
from Core.characters import CharacterManager, CharacterProfile, CharacterService
from Core.game import Game
from Core.saves import SaveManager, ProfileStorage
from Core.stats import Stats
from Infra.storage import JsonFileStore, JsonProfileRepository, JsonGameRepository
from Infra.api import StubCharacterSource


def test_arg_parser():
    args = ArgParser.parse_args('play_start "warrior_1" --enemies=goblin,wolf -v')
    assert args.command == "play_start"
    assert args.params == ["warrior_1"]
    assert args.flags == {"enemies": "goblin,wolf", "v": "true"}


def builtins():
    return [CharacterProfile("w1", "Воїн", "Воїн", Stats(150, 30, 0, 8, 0.1, 0.0, 100))]


def build(data_dir, answers=None):
    store = JsonFileStore(data_dir)
    manager = CharacterManager()
    storage = ProfileStorage(manager, JsonProfileRepository(store))
    storage.load(builtins())
    saves = SaveManager(JsonGameRepository(store))
    cli = CLI()
    reader = (lambda _: next(answers)) if answers else input
    cli.use_strategy(CatalogStrategy(manager, CharacterService(manager, StubCharacterSource()), storage, cli, reader))
    gs = GameStrategy(Game(), manager, saves, cli)
    cli.use_strategy(gs)
    cli.use_strategy(SystemStrategy(cli, str(data_dir)))
    return cli, manager, gs, saves


def test_continue_after_restart(tmp_path, capsys):
    cli, manager, gs, saves = build(tmp_path)
    assert cli.exec_command("import diluc")
    assert cli.exec_command("play_start w1 diluc --enemies=goblin")
    assert cli.exec_command("play_action attack e1")
    turn = gs.game.current_turn.number
    hp = gs.game.get("e1").hp
    history = [r.text for r in gs.game.all_records()]

    cli2, manager2, gs2, _ = build(tmp_path)
    assert manager2.get_character("diluc") is not None
    assert not gs2.game.is_active
    assert cli2.exec_command("continue")
    assert gs2.game.is_active
    assert gs2.game.current_turn.number == turn
    assert gs2.game.get("e1").hp == hp
    assert [r.text for r in gs2.game.all_records()] == history
    assert "Гру відновлено" in capsys.readouterr().out


def test_manual_slots(tmp_path, capsys):
    cli, _, gs, saves = build(tmp_path)
    cli.exec_command("play_start w1 --enemies=goblin")
    cli.exec_command("game_save before_boss")
    cli.exec_command("play_action attack e1")
    hp_after = gs.game.get("e1").hp
    cli.exec_command("game_load before_boss")
    assert gs.game.get("e1").hp > hp_after
    cli.exec_command("saves")
    out = capsys.readouterr().out
    assert "before_boss" in out and "autosave" in out
    assert {s.slot for s in saves.list_saves()} == {"before_boss", "autosave"}
    cli.exec_command("save_delete before_boss")
    assert {s.slot for s in saves.list_saves()} == {"autosave"}


def test_bad_slot_name(tmp_path, capsys):
    cli, _, _, _ = build(tmp_path)
    cli.exec_command("play_start w1")
    cli.exec_command("game_save ../hack")
    assert "Назва слоту" in capsys.readouterr().out
    assert not (tmp_path / "hack.json").exists()


def test_continue_without_saves(tmp_path, capsys):
    cli, _, _, _ = build(tmp_path)
    cli.exec_command("continue")
    assert "Збережень ще немає" in capsys.readouterr().out


def test_cli_rejects_unknown_enemy(tmp_path, capsys):
    cli, _, gs, _ = build(tmp_path)
    cli.exec_command("play_start w1 --enemies=dragon")
    assert not gs.game.is_active
    assert "Невідомі вороги" in capsys.readouterr().out


def test_create_character_is_persisted(tmp_path):
    answers = iter(["m1", "Маг", "Маг", "90", "8", "25", "2", "20", "110", ""])
    cli, manager, _, _ = build(tmp_path, answers)
    cli.exec_command("create")
    p = manager.get_character("m1")
    assert p.stats.magic == 25 and p.stats.resist == 0.2 and p.skills == ["fireball", "curse"]

    _, manager2, _, _ = build(tmp_path)
    assert manager2.get_character("m1").stats.magic == 25

    cli2, manager3, _, _ = build(tmp_path)
    cli2.exec_command("delete m1")
    cli2.exec_command("delete w1")
    assert manager3.get_character("w1") is not None
    _, manager4, _, _ = build(tmp_path)
    assert manager4.get_character("m1") is None
