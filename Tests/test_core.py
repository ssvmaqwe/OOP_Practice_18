import pytest
from Core.stats import Stats, Item, Modifier, StatusEffect
from Core.skills import SkillLibrary
from Core.combatant import Combatant, CombatantFactory, HERO, ENEMY
from Core.combat import DamageCalculator
from Core.characters import CharacterProfile, CharacterManager, ApiProfileMapper, CharacterService
from Core.game import Game, GameConfig, GameStatus, TurnScheduler
from Core.actions import GameRuleError
from Infra.api import StubCharacterSource


def unit(uid, team, **stats):
    return Combatant(uid, uid, team, Stats(**stats))


calc = DamageCalculator()


def test_physical_damage_armor_and_resist():
    a = unit("a", HERO, damage=30)
    t = unit("t", ENEMY, armor=10, resist=0.2)
    assert calc.physical(a, t).amount == 16


def test_armor_fully_blocks():
    a = unit("a", HERO, damage=8)
    t = unit("t", ENEMY, armor=10)
    report = calc.physical(a, t)
    assert report.blocked and report.amount == 0


def test_res_pen_and_item_bonus():
    a = unit("a", HERO, damage=20, res_pen=0.1)
    a.items.append(Item("sw", "Меч", [Modifier("damage", 10)]))
    t = unit("t", ENEMY, armor=5, resist=0.3)
    assert calc.physical(a, t).amount == 20


def test_magic_ignores_armor_with_bonus_and_debuff():
    a = unit("a", HERO, magic=20)
    a.apply_effect(StatusEffect("buff", "buff", 2, [Modifier("power", 0.5)]), 1)
    a.apply_effect(StatusEffect("debuff", "debuff", 2, [Modifier("weaken", 0.25)]), 1)
    t = unit("t", ENEMY, armor=100, resist=0.5)
    assert calc.magic(a, t, SkillLibrary.get("fireball")).amount == 38


def test_resist_cannot_go_below_zero_multiplier():
    a = unit("a", HERO, damage=50)
    t = unit("t", ENEMY, resist=1.5)
    assert calc.physical(a, t).amount == 0


def test_speed_schedule():
    slow = unit("s100", HERO, speed=100)
    mid = unit("s150", HERO, speed=150)
    fast = unit("s200", ENEMY, speed=200)
    order = TurnScheduler.build([slow, mid, fast])
    assert order == ["s200", "s150", "s100", "s200"]


def test_effect_ticks_and_expires():
    c = unit("c", HERO, health=50)
    c.apply_effect(StatusEffect("Отрута", "debuff", 2, hp_per_turn=-5), 1)
    c.start_turn(1)
    assert c.hp == 50
    c.start_turn(2)
    c.start_turn(3)
    assert c.hp == 40 and not c.effects


def test_cooldown():
    c = CombatantFactory.from_profile(CharacterProfile("w", "W", "Воїн", Stats()), "h1")
    strike = c.get_skill("strike")
    c.put_on_cooldown(strike)
    assert not c.is_ready(strike)
    c.start_turn(2)
    c.start_turn(3)
    assert c.is_ready(strike)


def make_game(enemies=("goblin",)):
    hero = CombatantFactory.from_profile(
        CharacterProfile("w", "Воїн", "Воїн", Stats(200, 40, 0, 10, 0.1, 0.0, 100)), "h1")
    foes = [CombatantFactory.from_template(t, f"e{i}") for i, t in enumerate(enemies, 1)]
    game = Game()
    game.start([hero], foes)
    return game


def test_game_flow_until_victory():
    game = make_game()
    assert game.current_actor.uid == "h1"
    for _ in range(20):
        if not game.is_active:
            break
        game.act("attack", "e1")
    assert game.status == GameStatus.WON
    assert game.score > 0
    assert len(game.history) >= 2


def test_invalid_actions():
    game = make_game()
    with pytest.raises(GameRuleError):
        game.act("fireball")
    with pytest.raises(GameRuleError):
        game.act("attack", "h1")
    game.act("strike", "e1")
    if game.is_active:
        with pytest.raises(GameRuleError):
            game.act("strike", "e1")


def test_save_and_restore_game():
    game = make_game(("goblin", "slime"))
    game.act("war_cry")
    data = GameConfig.from_dict(game.to_config().to_dict())
    restored = Game.from_config(data)
    assert restored.current_actor.uid == game.current_actor.uid
    assert restored.get("h1").hp == game.get("h1").hp
    assert restored.get("h1").cooldowns == game.get("h1").cooldowns
    assert [r.text for r in restored.all_records()] == [r.text for r in game.all_records()]
    restored.act("attack", "e1")


def test_incompatible_save_rejected():
    with pytest.raises(ValueError):
        GameConfig.from_dict({"enemy_hp": 100, "turn": 3})


def test_api_mapper_and_import():
    profile = ApiProfileMapper.from_api({"name": "Hu Tao", "vision": "Pyro", "weapon": "Polearm", "rarity": 5})
    assert profile.id == "hu-tao" and profile.char_class == "Маг"
    assert profile.stats.speed == 105 and profile.skills == ["fireball", "curse"]

    manager = CharacterManager()
    service = CharacterService(manager, StubCharacterSource())
    service.import_character("venti")
    assert manager.get_character("venti").char_class == "Лучник"
    with pytest.raises(LookupError):
        service.import_character("nobody")


def test_legacy_profile_format():
    p = CharacterProfile.from_dict({"id": "warrior_1", "name": "Артур", "char_class": "Воїн",
                                    "hp": 120, "max_hp": 120, "attack": 28, "gfx_url": "art.png"})
    assert p.stats.health == 120 and p.stats.damage == 28
