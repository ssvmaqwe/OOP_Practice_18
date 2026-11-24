from typing import Dict, Any, List, Optional, Iterable
from Core.interfaces import IRenderable
from Core.stats import Stats, Item, Modifier, StatusEffect
from Core.skills import Skill, SkillLibrary
from Core.characters import CharacterProfile

HERO = "hero"
ENEMY = "enemy"


class Combatant(IRenderable['Combatant']):
    def __init__(self, uid: str, name: str, team: str, base: Stats,
                 skills: Optional[List[Skill]] = None, items: Optional[List[Item]] = None,
                 profile_id: str = "", char_class: str = ""):
        super().__init__()
        self.uid = uid
        self.name = name
        self.team = team
        self.base = base.copy()
        self.skills: List[Skill] = skills or []
        self.items: List[Item] = items or []
        self.effects: List[StatusEffect] = []
        self.cooldowns: Dict[str, int] = {}
        self.profile_id = profile_id
        self.char_class = char_class
        self.hp = self.max_hp

    def _modifiers(self) -> Iterable[Modifier]:
        for item in self.items:
            yield from item.modifiers
        for effect in self.effects:
            yield from effect.modifiers

    def flat_bonus(self, stat: str) -> float:
        return sum(m.value for m in self._modifiers() if m.stat == stat)

    def stat(self, name: str) -> float:
        return getattr(self.base, name) + self.flat_bonus(name)

    @property
    def max_hp(self) -> int:
        return int(self.base.health + self.flat_bonus("health"))

    @property
    def speed(self) -> int:
        return max(1, int(self.stat("speed")))

    @property
    def power_multiplier(self) -> float:
        return 1.0 + self.flat_bonus("power")

    @property
    def weaken(self) -> float:
        return self.flat_bonus("weaken")

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    def take_damage(self, amount: int) -> int:
        dealt = min(self.hp, max(0, amount))
        self.hp -= dealt
        return dealt

    def restore(self, amount: int) -> int:
        healed = min(self.max_hp - self.hp, max(0, amount))
        self.hp += healed
        return healed

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        return next((s for s in self.skills if s.skill_id == skill_id), None)

    def is_ready(self, skill: Skill) -> bool:
        return self.cooldowns.get(skill.skill_id, 0) <= 0

    def put_on_cooldown(self, skill: Skill) -> None:
        if skill.cooldown > 0:
            self.cooldowns[skill.skill_id] = skill.cooldown

    def has_effect(self, name: str) -> bool:
        return any(e.name == name for e in self.effects)

    def apply_effect(self, effect: StatusEffect, turn: int) -> None:
        fresh = effect.copy()
        fresh.applied_turn = turn
        self.effects = [e for e in self.effects if e.name != fresh.name]
        self.effects.append(fresh)
        self.hp = min(self.hp, self.max_hp)

    def start_turn(self, turn: int) -> List[str]:
        messages: List[str] = []
        for skill_id in list(self.cooldowns):
            self.cooldowns[skill_id] -= 1
            if self.cooldowns[skill_id] <= 0:
                del self.cooldowns[skill_id]

        remaining: List[StatusEffect] = []
        for effect in self.effects:
            if effect.applied_turn >= turn:
                remaining.append(effect)
                continue
            if effect.hp_per_turn < 0:
                lost = self.take_damage(-effect.hp_per_turn)
                messages.append(f"{self.name} втрачає {lost} HP від ефекту «{effect.name}»")
            elif effect.hp_per_turn > 0:
                got = self.restore(effect.hp_per_turn)
                if got:
                    messages.append(f"{self.name} відновлює {got} HP від ефекту «{effect.name}»")
            effect.duration -= 1
            if effect.duration > 0:
                remaining.append(effect)
            else:
                messages.append(f"Ефект «{effect.name}» на {self.name} закінчився")
        self.effects = remaining
        self.hp = min(self.hp, self.max_hp)
        return messages

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid, "name": self.name, "team": self.team,
            "base": self.base.to_dict(), "hp": self.hp,
            "skills": [s.skill_id for s in self.skills],
            "items": [i.to_dict() for i in self.items],
            "effects": [e.to_dict() for e in self.effects],
            "cooldowns": dict(self.cooldowns),
            "profile_id": self.profile_id, "char_class": self.char_class,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Combatant':
        c = Combatant(
            data["uid"], data["name"], data["team"], Stats.from_dict(data["base"]),
            [SkillLibrary.get(s) for s in data.get("skills", []) if SkillLibrary.exists(s)],
            [Item.from_dict(i) for i in data.get("items", [])],
            data.get("profile_id", ""), data.get("char_class", ""),
        )
        c.effects = [StatusEffect.from_dict(e) for e in data.get("effects", [])]
        c.cooldowns = {k: int(v) for k, v in data.get("cooldowns", {}).items()}
        c.hp = max(0, min(int(data.get("hp", c.max_hp)), c.max_hp))
        return c


class EnemyLibrary:
    _templates: Dict[str, Dict[str, Any]] = {
        "goblin": {"name": "Гоблін", "stats": Stats(90, 18, 0, 4, 0.10, 0.0, 120), "skills": ["slam"]},
        "slime": {"name": "Слизовий маг", "stats": Stats(70, 8, 20, 2, 0.30, 0.0, 90), "skills": ["slime_bolt"]},
        "wolf": {"name": "Лютий вовк", "stats": Stats(70, 14, 0, 1, 0.0, 0.0, 200), "skills": []},
        "orc": {"name": "Орк-вождь", "stats": Stats(160, 24, 0, 10, 0.05, 0.0, 80), "skills": ["slam", "war_cry"]},
    }

    @classmethod
    def ids(cls) -> List[str]:
        return list(cls._templates)

    @classmethod
    def exists(cls, template_id: str) -> bool:
        return template_id in cls._templates

    @classmethod
    def describe(cls, template_id: str) -> Dict[str, Any]:
        return cls._templates[template_id]


class CombatantFactory:
    @staticmethod
    def from_profile(profile: CharacterProfile, uid: str) -> Combatant:
        skills = [SkillLibrary.get(s) for s in profile.skills if SkillLibrary.exists(s)]
        return Combatant(uid, profile.name, HERO, profile.stats, skills,
                         [Item(i.item_id, i.name, list(i.modifiers)) for i in profile.items],
                         profile.id, profile.char_class)

    @staticmethod
    def from_template(template_id: str, uid: str) -> Combatant:
        if not EnemyLibrary.exists(template_id):
            raise KeyError(f"Невідомий ворог: {template_id}")
        t = EnemyLibrary.describe(template_id)
        return Combatant(uid, t["name"], ENEMY, t["stats"],
                         [SkillLibrary.get(s) for s in t["skills"]], [], template_id, "Ворог")
