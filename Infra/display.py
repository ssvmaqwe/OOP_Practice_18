from typing import List
from Core.interfaces import IRenderer
from Core.characters import CharacterProfile
from Core.combatant import Combatant
from Core.game import Game, GameStatus
from Core.actions import ActionRecord
from Core.skills import SkillLibrary


class CLIGraphic:
    @staticmethod
    def banner(title: str) -> str:
        return f"\n{'=' * 40}\n  {title}\n{'=' * 40}"

    @staticmethod
    def progress_bar(current: int, maximum: int) -> str:
        if maximum <= 0:
            return "[----------]"
        filled = max(0, min(10, int(10 * (current / maximum))))
        return f"[{'#' * filled}{'-' * (10 - filled)}] {current}/{maximum}"

    @staticmethod
    def table(headers: List[str], rows: List[List[str]]) -> str:
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(str(cell)))
        res = [" | ".join(f"{h:<{widths[i]}}" for i, h in enumerate(headers)),
               "-" * (sum(widths) + 3 * (len(headers) - 1))]
        for row in rows:
            res.append(" | ".join(f"{str(c):<{widths[i]}}" for i, c in enumerate(row)))
        return "\n".join(res)


class ProfileConsoleRenderer(IRenderer[CharacterProfile]):
    def render(self, data: CharacterProfile) -> str:
        s = data.stats
        skills = ", ".join(SkillLibrary.get(x).name for x in data.skills if SkillLibrary.exists(x)) or "немає"
        items = ", ".join(i.name for i in data.items) or "немає"
        lines = [
            f"Персонаж: {data.name} [{data.id}]  (джерело: {data.source})",
            f"Клас: {data.char_class}",
            f"Здоров'я: {s.health} | Шкода: {s.damage} | Магія: {s.magic}",
            f"Броня: {s.armor} | Резист: {int(s.resist * 100)}% | Швидкість: {s.speed}",
            f"Навички: {skills}",
            f"Предмети: {items}",
        ]
        if data.description:
            lines.append(f"Опис: {data.description}")
        return "\n".join(lines)


class CombatantConsoleRenderer(IRenderer[Combatant]):
    def render(self, data: Combatant) -> str:
        effects = ", ".join(f"{e.name}({e.duration})" for e in data.effects) or "—"
        state = "" if data.is_alive else " [ПЕРЕМОЖЕНИЙ]"
        return (f"{data.uid:<3} {data.name:<16} {CLIGraphic.progress_bar(data.hp, data.max_hp)}"
                f"  шв.{data.speed:<4} ефекти: {effects}{state}")


class GameConsoleRenderer(IRenderer[Game]):
    STATUS = {GameStatus.IDLE: "Не розпочата", GameStatus.ACTIVE: "Триває",
              GameStatus.WON: "Перемога", GameStatus.LOST: "Поразка"}

    def __init__(self):
        self.unit_renderer = CombatantConsoleRenderer()

    def render(self, data: Game) -> str:
        if not data.combatants:
            return "Гра ще не розпочата. Використайте play_start <id>."
        turn = data.current_turn
        lines = [f"--- СТАТУС ГРИ ---",
                 f"Статус: {self.STATUS[data.status]} | Крок: {turn.number if turn else 0} | Очки: {data.score}",
                 "Герої:"]
        lines += ["  " + self.unit_renderer.render(c) for c in data.heroes]
        lines.append("Вороги:")
        lines += ["  " + self.unit_renderer.render(c) for c in data.enemies]
        if turn:
            order = " → ".join(data.combatants[u].name for u in turn.order)
            lines.append(f"Порядок дій у кроці: {order}")
        actor = data.current_actor
        if actor:
            lines.append(f"\nЗараз ходить: {actor.name} ({actor.uid})")
            acts = []
            for key, (title, cd) in data.available_actions().items():
                acts.append(f"{key} — {title}" + (f" (перезарядка {cd})" if cd else ""))
            lines.append("Доступні дії: " + "; ".join(acts))
        return "\n".join(lines)


class HistoryConsoleRenderer:
    def render(self, records: List[ActionRecord]) -> str:
        if not records:
            return "Історія порожня."
        lines: List[str] = []
        current = None
        for r in records:
            if r.turn != current:
                current = r.turn
                lines.append(f"── Крок {r.turn} ──")
            lines.append(f"  • {r.text}")
        return "\n".join(lines)
