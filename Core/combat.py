from dataclasses import dataclass
from typing import Optional
from Core.combatant import Combatant
from Core.skills import Skill

PHYSICAL = "physical"
MAGIC = "magic"


@dataclass
class DamageReport:
    amount: int
    damage_type: str
    blocked: bool = False
    resist_multiplier: float = 1.0
    power_multiplier: float = 1.0


class DamageCalculator:
    @staticmethod
    def resist_multiplier(attacker: Combatant, target: Combatant, skill: Optional[Skill] = None) -> float:
        res_pen = attacker.stat("res_pen") + (skill.res_pen if skill else 0.0)
        return max(0.0, 1.0 - target.stat("resist") + res_pen)

    @staticmethod
    def power_multiplier(attacker: Combatant) -> float:
        return max(0.0, attacker.power_multiplier - attacker.weaken)

    def physical(self, attacker: Combatant, target: Combatant, skill: Optional[Skill] = None) -> DamageReport:
        dmg_flat = attacker.base.damage
        bonus_flat = attacker.flat_bonus("damage") + (skill.power if skill else 0)
        after_armor = dmg_flat + bonus_flat - target.stat("armor")
        if after_armor <= 0:
            return DamageReport(0, PHYSICAL, blocked=True)
        res_mult = self.resist_multiplier(attacker, target, skill)
        pow_mult = self.power_multiplier(attacker)
        amount = round(after_armor * res_mult * pow_mult)
        return DamageReport(amount, PHYSICAL, False, res_mult, pow_mult)

    def magic(self, attacker: Combatant, target: Combatant, skill: Optional[Skill] = None) -> DamageReport:
        dmg_flat = attacker.base.magic
        bonus_flat = attacker.flat_bonus("magic") + (skill.power if skill else 0)
        res_mult = self.resist_multiplier(attacker, target, skill)
        pow_mult = self.power_multiplier(attacker)
        amount = round((dmg_flat * res_mult + bonus_flat) * pow_mult)
        return DamageReport(max(0, amount), MAGIC, False, res_mult, pow_mult)

    def calculate(self, attacker: Combatant, target: Combatant, skill: Optional[Skill] = None) -> DamageReport:
        if skill and skill.kind == MAGIC:
            return self.magic(attacker, target, skill)
        return self.physical(attacker, target, skill)

    def heal(self, healer: Combatant, skill: Skill) -> int:
        return round((skill.power + healer.stat("magic") * 0.5) * healer.power_multiplier)
