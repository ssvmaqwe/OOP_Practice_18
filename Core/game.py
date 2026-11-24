from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from Core.interfaces import IRenderable
from Core.combatant import Combatant, HERO, ENEMY
from Core.combat import DamageCalculator
from Core.actions import ActionRecord, ActionResolver, IAction, GameRuleError
from Core.ai import IEnemyBehavior, AggressiveBehavior

SAVE_VERSION = 2


class GameStatus:
    IDLE = "idle"
    ACTIVE = "active"
    WON = "won"
    LOST = "lost"


class TurnScheduler:
    BASE_SPEED = 100

    @classmethod
    def actions_per_turn(cls, speed: int) -> int:
        return max(1, speed // cls.BASE_SPEED)

    @classmethod
    def build(cls, combatants: List[Combatant]) -> List[str]:
        slots = []
        for index, c in enumerate(combatants):
            if not c.is_alive:
                continue
            count = cls.actions_per_turn(c.speed)
            for i in range(count):
                slots.append((i / count, -c.speed, index, c.uid))
        slots.sort()
        return [s[3] for s in slots]


@dataclass
class Turn:
    number: int
    order: List[str]
    position: int = 0
    records: List[ActionRecord] = field(default_factory=list)
    started: List[str] = field(default_factory=list)

    @property
    def finished(self) -> bool:
        return self.position >= len(self.order)

    def to_dict(self) -> Dict[str, Any]:
        return {"number": self.number, "order": list(self.order), "position": self.position,
                "records": [r.to_dict() for r in self.records], "started": list(self.started)}

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Turn':
        return Turn(data["number"], list(data["order"]), data.get("position", 0),
                    [ActionRecord.from_dict(r) for r in data.get("records", [])],
                    list(data.get("started", [])))


@dataclass
class GameConfig:
    status: str = GameStatus.IDLE
    score: int = 0
    combatants: List[Dict[str, Any]] = field(default_factory=list)
    turns: List[Dict[str, Any]] = field(default_factory=list)
    version: int = SAVE_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {"version": self.version, "status": self.status, "score": self.score,
                "combatants": self.combatants, "turns": self.turns}

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'GameConfig':
        if not data or data.get("version") != SAVE_VERSION:
            raise ValueError("Збереження має несумісний формат")
        return GameConfig(data.get("status", GameStatus.IDLE), data.get("score", 0),
                          list(data.get("combatants", [])), list(data.get("turns", [])))


class Game(IRenderable['Game']):
    WIN_BONUS = 500
    TURN_PENALTY = 20

    def __init__(self, calculator: Optional[DamageCalculator] = None,
                 behavior: Optional[IEnemyBehavior] = None):
        super().__init__()
        self.calculator = calculator or DamageCalculator()
        self.behavior = behavior or AggressiveBehavior()
        self.combatants: Dict[str, Combatant] = {}
        self.history: List[Turn] = []
        self.status = GameStatus.IDLE
        self.score = 0

    @property
    def is_active(self) -> bool:
        return self.status == GameStatus.ACTIVE

    @property
    def heroes(self) -> List[Combatant]:
        return [c for c in self.combatants.values() if c.team == HERO]

    @property
    def enemies(self) -> List[Combatant]:
        return [c for c in self.combatants.values() if c.team == ENEMY]

    @property
    def current_turn(self) -> Optional[Turn]:
        return self.history[-1] if self.history else None

    @property
    def current_actor(self) -> Optional[Combatant]:
        turn = self.current_turn
        if not self.is_active or turn is None or turn.finished:
            return None
        return self.combatants.get(turn.order[turn.position])

    def get(self, uid: str) -> Optional[Combatant]:
        return self.combatants.get(uid)

    def start(self, heroes: List[Combatant], enemies: List[Combatant]) -> List[ActionRecord]:
        if not heroes:
            raise GameRuleError("Потрібен хоча б один герой")
        if not enemies:
            raise GameRuleError("Потрібен хоча б один ворог")
        self.combatants = {c.uid: c for c in heroes + enemies}
        self.history = []
        self.score = 0
        self.status = GameStatus.ACTIVE
        self._begin_turn()
        self._run_until_player()
        return self.all_records()

    def act(self, action_id: str, target_uid: Optional[str] = None) -> List[ActionRecord]:
        if self.status in (GameStatus.WON, GameStatus.LOST):
            raise GameRuleError("Бій завершено. Почніть новий: play_start <id>")
        actor = self.current_actor
        if actor is None:
            raise GameRuleError("Гра не розпочата. Використайте play_start <id>")
        if actor.team != HERO:
            raise GameRuleError("Зараз хід ворога")
        action = ActionResolver.resolve(actor, action_id)
        target = self._pick_target(actor, action, target_uid)
        action.validate(actor, target)
        start = len(self.all_records())
        self._execute(actor, action, target)
        self.current_turn.position += 1
        self._check_end()
        self._run_until_player()
        return self.all_records()[start:]

    def available_actions(self) -> Dict[str, Any]:
        actor = self.current_actor
        return ActionResolver.available(actor) if actor else {}

    def all_records(self) -> List[ActionRecord]:
        return [r for t in self.history for r in t.records]

    def _pick_target(self, actor: Combatant, action: IAction, target_uid: Optional[str]) -> Combatant:
        if target_uid:
            target = self.combatants.get(target_uid)
            if target is None:
                raise GameRuleError(f"Ціль '{target_uid}' не знайдено")
            return target
        if action.target_side == "self":
            return actor
        if action.target_side == "ally":
            allies = [c for c in self.combatants.values() if c.team == actor.team and c.is_alive]
            return min(allies, key=lambda c: (c.hp / c.max_hp, c.uid))
        opponents = [c for c in self.combatants.values() if c.team != actor.team and c.is_alive]
        return opponents[0]

    def _log(self, actor: Combatant, action: str, target: str, amount: int, text: str) -> None:
        turn = self.current_turn
        turn.records.append(ActionRecord(turn.number, actor.uid, action, target, amount, text))

    def _execute(self, actor: Combatant, action: IAction, target: Combatant) -> None:
        amount, text = action.execute(actor, target, self.calculator, self.current_turn.number)
        if actor.team == HERO and target.team == ENEMY:
            self.score += amount * 10
        self._log(actor, action.action_id, target.uid, amount, text)

    def _begin_turn(self) -> None:
        number = self.current_turn.number + 1 if self.current_turn else 1
        order = TurnScheduler.build(list(self.combatants.values()))
        self.history.append(Turn(number, order))

    def _prepare(self, actor: Combatant) -> None:
        turn = self.current_turn
        if actor.uid in turn.started:
            return
        turn.started.append(actor.uid)
        for message in actor.start_turn(turn.number):
            self._log(actor, "effect", actor.uid, 0, message)
        if not actor.is_alive:
            self._log(actor, "defeat", actor.uid, 0, f"{actor.name} переможений!")

    def _run_until_player(self) -> None:
        while self.is_active:
            turn = self.current_turn
            if turn.finished:
                self._begin_turn()
                continue
            actor = self.combatants[turn.order[turn.position]]
            if not actor.is_alive:
                turn.position += 1
                continue
            self._prepare(actor)
            self._check_end()
            if not self.is_active:
                break
            if not actor.is_alive:
                turn.position += 1
                continue
            if actor.team == HERO:
                break
            allies = [c for c in self.enemies if c.is_alive]
            opponents = [c for c in self.heroes if c.is_alive]
            action, target = self.behavior.choose(actor, allies, opponents)
            self._execute(actor, action, target)
            turn.position += 1
            self._check_end()

    def _check_end(self) -> None:
        if not self.is_active:
            return
        if not any(c.is_alive for c in self.enemies):
            self.status = GameStatus.WON
            bonus = max(0, self.WIN_BONUS - self.TURN_PENALTY * self.current_turn.number)
            self.score += bonus
            self._log_system(f"ПЕРЕМОГА! Бонус за швидкість: +{bonus} очок")
        elif not any(c.is_alive for c in self.heroes):
            self.status = GameStatus.LOST
            self._log_system("ПОРАЗКА. Усі герої переможені")

    def _log_system(self, text: str) -> None:
        turn = self.current_turn
        turn.records.append(ActionRecord(turn.number, "system", "end", "", 0, text))

    def to_config(self) -> GameConfig:
        return GameConfig(self.status, self.score,
                          [c.to_dict() for c in self.combatants.values()],
                          [t.to_dict() for t in self.history])

    @classmethod
    def from_config(cls, config: GameConfig, calculator: Optional[DamageCalculator] = None,
                    behavior: Optional[IEnemyBehavior] = None) -> 'Game':
        game = cls(calculator, behavior)
        game.combatants = {d["uid"]: Combatant.from_dict(d) for d in config.combatants}
        game.history = [Turn.from_dict(t) for t in config.turns]
        game.status = config.status
        game.score = config.score
        return game
