from abc import ABC, abstractmethod
from typing import List, Tuple
from Core.actions import IAction, AttackAction, SkillAction
from Core.combatant import Combatant


class IEnemyBehavior(ABC):
    @abstractmethod
    def choose(self, actor: Combatant, allies: List[Combatant],
               opponents: List[Combatant]) -> Tuple[IAction, Combatant]:
        pass


class AggressiveBehavior(IEnemyBehavior):
    def choose(self, actor, allies, opponents):
        target = min(opponents, key=lambda c: (c.hp, c.uid))
        for skill in actor.skills:
            if not actor.is_ready(skill):
                continue
            if skill.target == "self" and skill.effect and not actor.has_effect(skill.effect.name):
                return SkillAction(skill), actor
            if skill.target == "enemy":
                return SkillAction(skill), target
        return AttackAction(), target
