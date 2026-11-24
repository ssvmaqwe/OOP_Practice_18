from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple
from Core.combatant import Combatant
from Core.combat import DamageCalculator
from Core.skills import Skill
from Core.stats import StatusEffect, Modifier


class GameRuleError(Exception):
    pass


@dataclass
class ActionRecord:
    turn: int
    actor: str
    action: str
    target: str
    amount: int
    text: str

    def to_dict(self) -> Dict[str, Any]:
        return {"turn": self.turn, "actor": self.actor, "action": self.action,
                "target": self.target, "amount": self.amount, "text": self.text}

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'ActionRecord':
        return ActionRecord(data["turn"], data["actor"], data["action"],
                            data.get("target", ""), data.get("amount", 0), data["text"])


class IAction(ABC):
    action_id: str = ""
    title: str = ""
    target_side: str = "enemy"

    def validate(self, actor: Combatant, target: Combatant) -> None:
        if not target.is_alive:
            raise GameRuleError(f"{target.name} вже не може бути ціллю")
        if self.target_side == "enemy" and target.team == actor.team:
            raise GameRuleError("Цю дію можна застосувати лише до ворога")
        if self.target_side == "ally" and target.team != actor.team:
            raise GameRuleError("Цю дію можна застосувати лише до союзника")
        if self.target_side == "self" and target is not actor:
            raise GameRuleError("Цю дію можна застосувати лише до себе")

    @abstractmethod
    def execute(self, actor: Combatant, target: Combatant, calc: DamageCalculator, turn: int) -> Tuple[int, str]:
        pass


class AttackAction(IAction):
    action_id = "attack"
    title = "Атака"
    target_side = "enemy"

    def execute(self, actor, target, calc, turn):
        report = calc.physical(actor, target)
        if report.blocked:
            return 0, f"{actor.name} атакує {target.name}, але броня повністю блокує удар"
        dealt = target.take_damage(report.amount)
        text = f"{actor.name} атакує {target.name}: {dealt} фізичної шкоди"
        if not target.is_alive:
            text += f". {target.name} переможений!"
        return dealt, text


class DefendAction(IAction):
    action_id = "defend"
    title = "Захист"
    target_side = "self"
    EFFECT = StatusEffect("Захисна стійка", "buff", 1, [Modifier("armor", 10), Modifier("resist", 0.2)])

    def execute(self, actor, target, calc, turn):
        actor.apply_effect(self.EFFECT, turn)
        return 0, f"{actor.name} стає в захисну стійку (+10 броні, +20% резисту до свого наступного кроку)"


class SkillAction(IAction):
    def __init__(self, skill: Skill):
        self.skill = skill
        self.action_id = skill.skill_id
        self.title = skill.name
        self.target_side = skill.target

    def validate(self, actor, target):
        if not actor.is_ready(self.skill):
            raise GameRuleError(
                f"Навичка «{self.skill.name}» перезаряджається ще {actor.cooldowns[self.skill.skill_id]} крок(и)")
        super().validate(actor, target)

    def execute(self, actor, target, calc, turn):
        skill = self.skill
        actor.put_on_cooldown(skill)
        amount = 0
        if skill.deals_damage:
            report = calc.calculate(actor, target, skill)
            if report.blocked:
                text = f"{actor.name} використовує «{skill.name}», але броня {target.name} блокує удар"
            else:
                amount = target.take_damage(report.amount)
                kind = "магічної" if report.damage_type == "magic" else "фізичної"
                text = f"{actor.name} використовує «{skill.name}» на {target.name}: {amount} {kind} шкоди"
        elif skill.kind == "heal":
            amount = target.restore(calc.heal(actor, skill))
            text = f"{actor.name} використовує «{skill.name}» на {target.name}: +{amount} HP"
        else:
            text = f"{actor.name} використовує «{skill.name}» на {target.name}"

        if skill.effect and target.is_alive:
            target.apply_effect(skill.effect, turn)
            text += f" [ефект «{skill.effect.name}» на {skill.effect.duration} кр.]"
        if not target.is_alive:
            text += f". {target.name} переможений!"
        return amount, text


class ActionResolver:
    @staticmethod
    def resolve(actor: Combatant, action_id: str) -> IAction:
        key = action_id.lower()
        if key == AttackAction.action_id:
            return AttackAction()
        if key == DefendAction.action_id:
            return DefendAction()
        skill = actor.get_skill(key)
        if skill:
            return SkillAction(skill)
        raise GameRuleError(f"{actor.name} не має дії '{action_id}'")

    @staticmethod
    def available(actor: Combatant) -> Dict[str, Tuple[str, Optional[int]]]:
        result: Dict[str, Tuple[str, Optional[int]]] = {
            AttackAction.action_id: (AttackAction.title, None),
            DefendAction.action_id: (DefendAction.title, None),
        }
        for skill in actor.skills:
            result[skill.skill_id] = (skill.name, actor.cooldowns.get(skill.skill_id))
        return result
