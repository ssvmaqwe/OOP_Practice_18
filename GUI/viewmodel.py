import io
import shlex
from contextlib import redirect_stdout
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
from app import AppContext
from CLI.commands import format_save, STATUS_NAMES, SOURCE_NAMES
from Core.actions import ActionResolver, GameRuleError
from Core.combatant import EnemyLibrary, HERO
from Core.saves import DEFAULT_SLOT

OUTPUT = "output"
STATE = "state"


@dataclass
class HeroOption:
    hero_id: str
    label: str


@dataclass
class EnemyOption:
    template_id: str
    label: str


@dataclass
class ActionOption:
    action_id: str
    title: str
    cooldown: Optional[int]
    target_side: str

    @property
    def ready(self) -> bool:
        return not self.cooldown

    @property
    def label(self) -> str:
        return self.title + (f" (перезарядка {self.cooldown})" if self.cooldown else "")


@dataclass
class TargetOption:
    uid: str
    label: str


@dataclass
class SaveRow:
    slot: str
    label: str
    is_auto: bool


class AnswerQueue:
    def __init__(self):
        self._answers: List[str] = []
        self.prompts: List[str] = []

    def feed(self, answers: List[str]) -> None:
        self._answers = list(answers)

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._answers.pop(0) if self._answers else ""


class GameViewModel:
    def __init__(self, ctx: AppContext, answers: Optional[AnswerQueue] = None):
        self.ctx = ctx
        self.answers = answers or AnswerQueue()
        self.log: List[str] = []
        self._listeners: Dict[str, List[Callable]] = {OUTPUT: [], STATE: []}

    def subscribe(self, event: str, callback: Callable) -> None:
        self._listeners[event].append(callback)

    def _emit(self, event: str, *args) -> None:
        for callback in self._listeners[event]:
            callback(*args)

    def _write(self, text: str) -> None:
        if not text:
            return
        self.log.append(text)
        self._emit(OUTPUT, text)

    def execute(self, command: str) -> str:
        command = command.strip()
        if not command:
            return ""
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            self.ctx.cli.exec_command(command)
        text = buffer.getvalue()
        self._write(f"> {command}\n{text}")
        self._emit(STATE)
        return text

    def startup(self) -> None:
        lines = list(self.ctx.messages)
        lines.append("Вітаю у «Текстовій грі»! Оберіть героїв і ворогів праворуч та натисніть «Почати бій».")
        latest = self.ctx.saves.latest()
        if latest:
            lines.append(f"Знайдено збереження {format_save(latest)}. Натисніть «Продовжити останнє».")
        self._write("\n".join(lines) + "\n")
        self._emit(STATE)

    def shutdown(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            self.ctx.game_strategy.autosave()

    @property
    def game(self):
        return self.ctx.game

    @property
    def is_active(self) -> bool:
        return self.game.is_active

    @property
    def data_dir(self) -> str:
        return str(self.ctx.data_dir)

    def status_line(self) -> str:
        game = self.game
        if not game.combatants:
            return "Бій не розпочато"
        turn = game.current_turn.number if game.current_turn else 0
        line = f"{STATUS_NAMES.get(game.status, game.status)} | Крок {turn} | Очки {game.score}"
        actor = game.current_actor
        if actor:
            line += f" | Ходить: {actor.name} ({actor.uid})"
        return line

    def heroes(self) -> List[HeroOption]:
        return [HeroOption(p.id, f"{p.name} — {p.char_class} ({SOURCE_NAMES.get(p.source, p.source)})")
                for p in self.ctx.manager.get_all()]

    def enemy_templates(self) -> List[EnemyOption]:
        result = []
        for tid in EnemyLibrary.ids():
            t = EnemyLibrary.describe(tid)
            result.append(EnemyOption(tid, f"{t['name']} (HP {t['stats'].health}, шв. {t['stats'].speed})"))
        return result

    def actions(self) -> List[ActionOption]:
        actor = self.game.current_actor
        if actor is None or actor.team != HERO:
            return []
        result = []
        for action_id, (title, cooldown) in self.game.available_actions().items():
            side = ActionResolver.resolve(actor, action_id).target_side
            result.append(ActionOption(action_id, title, cooldown, side))
        return result

    def targets_for(self, action_id: str) -> List[TargetOption]:
        actor = self.game.current_actor
        if actor is None:
            return []
        try:
            side = ActionResolver.resolve(actor, action_id).target_side
        except GameRuleError:
            return []
        if side == "self":
            return [TargetOption(actor.uid, f"{actor.name} (сам)")]
        alive = [c for c in self.game.combatants.values() if c.is_alive]
        chosen = [c for c in alive if (c.team == actor.team) == (side == "ally")]
        return [TargetOption(c.uid, f"{c.name} [{c.uid}] {c.hp}/{c.max_hp} HP") for c in chosen]

    def saves(self) -> List[SaveRow]:
        rows = []
        for info in self.ctx.saves.list_saves():
            when = info.saved_at.replace("T", " ")[:16]
            heroes = ", ".join(info.heroes)
            rows.append(SaveRow(info.slot, f"{info.slot}{' (авто)' if info.is_auto else ''} — {when}, "
                                           f"крок {info.turn}, {STATUS_NAMES.get(info.status, info.status)}, {heroes}",
                                info.is_auto))
        return rows

    def start(self, hero_ids: List[str], enemy_ids: List[str]) -> str:
        if not hero_ids:
            self._write("Оберіть хоча б одного героя.\n")
            return ""
        if not enemy_ids:
            self._write("Оберіть хоча б одного ворога.\n")
            return ""
        heroes = " ".join(shlex.quote(h) for h in hero_ids)
        return self.execute(f"play_start {heroes} --enemies={','.join(enemy_ids)}")

    def act(self, action_id: str, target_uid: Optional[str] = None) -> str:
        command = f"play_action {shlex.quote(action_id)}"
        if target_uid:
            command += f" {shlex.quote(target_uid)}"
        return self.execute(command)

    def save(self, slot: str = DEFAULT_SLOT) -> str:
        return self.execute(f"game_save {shlex.quote(slot or DEFAULT_SLOT)}")

    def load(self, slot: str) -> str:
        return self.execute(f"game_load {shlex.quote(slot)}")

    def continue_game(self) -> str:
        return self.execute("continue")

    def delete_save(self, slot: str) -> str:
        return self.execute(f"save_delete {shlex.quote(slot)}")

    def show_status(self) -> str:
        return self.execute("play_status")

    def show_history(self) -> str:
        return self.execute("play_history")

    def show_help(self) -> str:
        return self.execute("help")

    def create_character(self, char_id: str, name: str, char_class: str, health: int, damage: int,
                         magic: int, armor: int, resist_percent: int, speed: int, gfx_url: str = "") -> str:
        self.answers.feed([char_id, name, char_class, str(health), str(damage), str(magic),
                           str(armor), str(resist_percent), str(speed), gfx_url])
        return self.execute("create")

    def character_classes(self) -> List[str]:
        from Core.skills import SkillLibrary
        return list(SkillLibrary.CLASS_SKILLS)

    def import_character(self, name: str) -> str:
        return self.execute(f"import {shlex.quote(name)}")
