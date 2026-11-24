from app import build_app
from GUI.viewmodel import GameViewModel, AnswerQueue, OUTPUT, STATE


def make_vm(tmp_path):
    answers = AnswerQueue()
    ctx = build_app(tmp_path, reader=answers, legacy_file=None, online=False)
    return GameViewModel(ctx, answers)


def test_output_goes_to_listeners(tmp_path):
    vm = make_vm(tmp_path)
    received, states = [], []
    vm.subscribe(OUTPUT, received.append)
    vm.subscribe(STATE, lambda: states.append(1))
    vm.startup()
    vm.execute("enemies")
    assert "Вітаю" in received[0]
    assert received[1].startswith("> enemies") and "Гоблін" in received[1]
    assert len(states) == 2


def test_lists_for_start_panel(tmp_path):
    vm = make_vm(tmp_path)
    assert [h.hero_id for h in vm.heroes()] == ["warrior_1", "mage_1", "healer_1"]
    assert "goblin" in [e.template_id for e in vm.enemy_templates()]
    assert vm.actions() == [] and vm.status_line() == "Бій не розпочато"


def test_battle_through_viewmodel(tmp_path):
    vm = make_vm(tmp_path)
    out = vm.start(["warrior_1", "healer_1"], ["goblin"])
    assert "ТЕКСТОВА ГРА" in out and vm.is_active
    actions = {a.action_id: a for a in vm.actions()}
    assert {"attack", "defend", "strike", "war_cry"} <= set(actions) or {"heal", "blessing"} <= set(actions)
    actor = vm.game.current_actor
    attack_targets = vm.targets_for("attack")
    assert attack_targets and all(vm.game.get(t.uid).team != actor.team for t in attack_targets)
    assert [t.uid for t in vm.targets_for("defend")] == [actor.uid]

    hp_before = vm.game.get("e1").hp
    vm.act("attack", "e1")
    assert vm.game.get("e1").hp < hp_before
    assert "Крок" in vm.status_line()


def test_cooldown_is_visible(tmp_path):
    vm = make_vm(tmp_path)
    vm.start(["warrior_1"], ["orc"])
    vm.act("strike", "e1")
    strike = next(a for a in vm.actions() if a.action_id == "strike")
    assert not strike.ready and "перезарядка" in strike.label


def test_start_requires_selection(tmp_path):
    vm = make_vm(tmp_path)
    received = []
    vm.subscribe(OUTPUT, received.append)
    vm.start([], ["goblin"])
    vm.start(["warrior_1"], [])
    assert "героя" in received[0] and "ворога" in received[1]
    assert not vm.is_active


def test_save_buttons(tmp_path):
    vm = make_vm(tmp_path)
    vm.start(["warrior_1"], ["goblin"])
    vm.save("before")
    vm.act("attack", "e1")
    slots = [r.slot for r in vm.saves()]
    assert set(slots) == {"before", "autosave"}
    assert any(r.is_auto for r in vm.saves())

    hp_after = vm.game.get("e1").hp
    vm.load("before")
    assert vm.game.get("e1").hp > hp_after
    vm.delete_save("before")
    assert [r.slot for r in vm.saves()] == ["autosave"]


def test_continue_after_restart(tmp_path):
    vm = make_vm(tmp_path)
    vm.start(["warrior_1"], ["goblin"])
    vm.act("attack", "e1")
    hp = vm.game.get("e1").hp
    vm.shutdown()

    vm2 = make_vm(tmp_path)
    received = []
    vm2.subscribe(OUTPUT, received.append)
    vm2.startup()
    assert "Продовжити останнє" in received[0]
    vm2.continue_game()
    assert vm2.is_active and vm2.game.get("e1").hp == hp


def test_create_and_import_from_gui(tmp_path):
    vm = make_vm(tmp_path)
    vm.create_character("rogue", "Тінь", "Лучник", 90, 20, 5, 3, 15, 130)
    vm.import_character("venti")
    ids = [h.hero_id for h in vm.heroes()]
    assert "rogue" in ids and "venti" in ids
    assert make_vm(tmp_path).ctx.manager.get_character("rogue").stats.speed == 130


def test_bad_command_does_not_crash(tmp_path):
    vm = make_vm(tmp_path)
    out = vm.execute("fly_to_moon")
    assert "Невідома команда" in out
    assert vm.act("attack") and not vm.is_active
