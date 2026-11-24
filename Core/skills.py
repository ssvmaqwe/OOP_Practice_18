from dataclasses import dataclass
from typing import Optional, Dict, List
from Core.stats import StatusEffect, Modifier

DAMAGE_KINDS = ("physical", "magic")


@dataclass
class Skill:
    skill_id: str
    name: str
    kind: str
    power: int = 0
    cooldown: int = 0
    target: str = "enemy"
    res_pen: float = 0.0
    effect: Optional[StatusEffect] = None
    description: str = ""

    @property
    def deals_damage(self) -> bool:
        return self.kind in DAMAGE_KINDS


class SkillLibrary:
    _skills: Dict[str, Skill] = {
        "strike": Skill("strike", "Потужний удар", "physical", power=15, cooldown=2,
                        description="Фізичний удар з бонусом +15 до шкоди"),
        "pierce": Skill("pierce", "Пробивний постріл", "physical", power=8, cooldown=2, res_pen=0.4,
                        description="Ігнорує 40% резисту цілі"),
        "poison_arrow": Skill("poison_arrow", "Отруйна стріла", "physical", power=5, cooldown=3,
                              effect=StatusEffect("Отрута", "debuff", 3, hp_per_turn=-6),
                              description="Шкода + отрута 6 HP за крок (3 кроки)"),
        "war_cry": Skill("war_cry", "Бойовий клич", "buff", cooldown=4, target="self",
                         effect=StatusEffect("Бойовий клич", "buff", 2, [Modifier("power", 0.3)]),
                         description="+30% до всієї шкоди на 2 кроки"),
        "fireball": Skill("fireball", "Вогняна куля", "magic", power=20, cooldown=3,
                          effect=StatusEffect("Опік", "debuff", 2, hp_per_turn=-5),
                          description="Магічна шкода, ігнорує броню, накладає опік"),
        "curse": Skill("curse", "Прокляття", "debuff", cooldown=4,
                       effect=StatusEffect("Прокляття", "debuff", 2,
                                           [Modifier("weaken", 0.3), Modifier("resist", -0.15)]),
                       description="Ціль б'є на 30% слабше, резист -15%"),
        "heal": Skill("heal", "Лікування", "heal", power=30, cooldown=2, target="ally",
                      description="Відновлює здоров'я союзнику"),
        "blessing": Skill("blessing", "Благословення", "buff", cooldown=4, target="ally",
                          effect=StatusEffect("Благословення", "buff", 3, [Modifier("armor", 8)], hp_per_turn=5),
                          description="+8 броні та +5 HP за крок (3 кроки)"),
        "slam": Skill("slam", "Розмашистий удар", "physical", power=10, cooldown=2,
                      description="Важкий удар ворога"),
        "slime_bolt": Skill("slime_bolt", "Слизовий заряд", "magic", power=10, cooldown=2,
                            effect=StatusEffect("Липкість", "debuff", 2, [Modifier("speed", -40)]),
                            description="Магічна шкода, сповільнює ціль"),
    }

    CLASS_SKILLS: Dict[str, List[str]] = {
        "Воїн": ["strike", "war_cry"],
        "Маг": ["fireball", "curse"],
        "Цілитель": ["heal", "blessing"],
        "Лучник": ["pierce", "poison_arrow"],
    }

    @classmethod
    def get(cls, skill_id: str) -> Skill:
        if skill_id not in cls._skills:
            raise KeyError(f"Невідома навичка: {skill_id}")
        return cls._skills[skill_id]

    @classmethod
    def exists(cls, skill_id: str) -> bool:
        return skill_id in cls._skills

    @classmethod
    def all(cls) -> List[Skill]:
        return list(cls._skills.values())

    @classmethod
    def for_class(cls, char_class: str) -> List[str]:
        return list(cls.CLASS_SKILLS.get(char_class, ["strike"]))
