import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, Iterable
from Core.interfaces import IGameRepository, IProfileRepository
from Core.characters import CharacterManager, CharacterProfile
from Core.game import Game, GameConfig, GameStatus
from Core.combat import DamageCalculator
from Core.ai import IEnemyBehavior

AUTOSAVE_SLOT = "autosave"
DEFAULT_SLOT = "slot1"
IMPORTED_SLOT = "imported"
BUILTIN = "builtin"
SLOT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


class SaveError(Exception):
    pass


@dataclass
class SaveInfo:
    slot: str
    saved_at: str
    turn: int
    status: str
    score: int
    heroes: List[str] = field(default_factory=list)

    @property
    def is_auto(self) -> bool:
        return self.slot == AUTOSAVE_SLOT

    def to_dict(self) -> Dict[str, Any]:
        return {"slot": self.slot, "saved_at": self.saved_at, "turn": self.turn,
                "status": self.status, "score": self.score, "heroes": list(self.heroes)}

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'SaveInfo':
        return SaveInfo(data["slot"], data.get("saved_at", ""), data.get("turn", 0),
                        data.get("status", GameStatus.IDLE), data.get("score", 0), list(data.get("heroes", [])))

    @staticmethod
    def describe(game: Game, slot: str, saved_at: str) -> 'SaveInfo':
        turn = game.current_turn.number if game.current_turn else 0
        return SaveInfo(slot, saved_at, turn, game.status, game.score, [h.name for h in game.heroes])


class SaveManager:
    def __init__(self, repo: IGameRepository, clock: Callable[[], datetime] = datetime.now):
        self.repo = repo
        self.clock = clock

    @staticmethod
    def validate_slot(slot: str) -> str:
        slot = (slot or "").strip()
        if not SLOT_PATTERN.match(slot):
            raise SaveError("Назва слоту: 1–32 символи, лише латинські літери, цифри, '_' або '-'")
        return slot

    def _now(self) -> str:
        return self.clock().isoformat(timespec="microseconds")

    def save(self, game: Game, slot: str = DEFAULT_SLOT) -> SaveInfo:
        slot = self.validate_slot(slot)
        if game.status == GameStatus.IDLE:
            raise SaveError("Немає гри для збереження")
        info = SaveInfo.describe(game, slot, self._now())
        self.repo.save_game(slot, {"meta": info.to_dict(), "game": game.to_config().to_dict()})
        return info

    def autosave(self, game: Game) -> Optional[SaveInfo]:
        if game.status == GameStatus.IDLE:
            return None
        return self.save(game, AUTOSAVE_SLOT)

    def load(self, slot: str, calculator: Optional[DamageCalculator] = None,
             behavior: Optional[IEnemyBehavior] = None) -> Game:
        slot = self.validate_slot(slot)
        data = self.repo.load_game(slot)
        if not data or "game" not in data:
            raise SaveError(f"Збереження '{slot}' не знайдено")
        try:
            config = GameConfig.from_dict(data["game"])
            return Game.from_config(config, calculator, behavior)
        except (ValueError, KeyError, TypeError) as e:
            raise SaveError(f"Збереження '{slot}' пошкоджене: {e}")

    def list_saves(self) -> List[SaveInfo]:
        infos = []
        for meta in self.repo.list_saves():
            try:
                infos.append(SaveInfo.from_dict(meta))
            except (KeyError, TypeError):
                continue
        return sorted(infos, key=lambda i: i.saved_at, reverse=True)

    def latest(self) -> Optional[SaveInfo]:
        saves = self.list_saves()
        return saves[0] if saves else None

    def delete(self, slot: str) -> bool:
        return self.repo.delete_save(self.validate_slot(slot))

    def import_state(self, slot: str, state: Dict[str, Any], saved_at: str) -> SaveInfo:
        game = Game.from_config(GameConfig.from_dict(state))
        info = SaveInfo.describe(game, self.validate_slot(slot), saved_at)
        self.repo.save_game(info.slot, {"meta": info.to_dict(), "game": game.to_config().to_dict()})
        return info


class ProfileStorage:
    def __init__(self, manager: CharacterManager, repo: IProfileRepository):
        self.manager = manager
        self.repo = repo

    def load(self, builtins: Iterable[CharacterProfile]) -> int:
        self.manager.clear()
        for profile in builtins:
            profile.source = BUILTIN
            self.manager.add_character(profile)
        loaded = 0
        for data in self.repo.load_profiles():
            try:
                profile = CharacterProfile.from_dict(data)
            except (KeyError, TypeError, ValueError):
                continue
            if profile.source == BUILTIN:
                continue
            self.manager.add_character(profile)
            loaded += 1
        return loaded

    def user_profiles(self) -> List[CharacterProfile]:
        return [p for p in self.manager.get_all() if p.source != BUILTIN]

    def save(self) -> int:
        profiles = self.user_profiles()
        self.repo.save_profiles([p.to_dict() for p in profiles])
        return len(profiles)

    def delete(self, char_id: str) -> None:
        profile = self.manager.get_character(char_id)
        if profile is None:
            raise SaveError(f"Персонажа '{char_id}' не знайдено")
        if profile.source == BUILTIN:
            raise SaveError("Вбудованих персонажів видаляти не можна")
        self.manager.remove_character(char_id)
        self.save()


def migrate_legacy(data: Dict[str, Any], storage: ProfileStorage, saves: SaveManager,
                   saved_at: str) -> List[str]:
    messages: List[str] = []
    added = 0
    for item in data.get("characters", []) or []:
        try:
            profile = CharacterProfile.from_dict(item)
        except (KeyError, TypeError, ValueError):
            continue
        if storage.manager.get_character(profile.id):
            continue
        profile.source = "custom"
        storage.manager.add_character(profile)
        added += 1
    if added:
        storage.save()
        messages.append(f"Перенесено персонажів зі старого repository.json: {added}")

    state = data.get("game_state")
    if state:
        try:
            saves.import_state(IMPORTED_SLOT, state, saved_at)
            messages.append(f"Старе збереження гри перенесено у слот '{IMPORTED_SLOT}'")
        except (ValueError, KeyError, TypeError):
            messages.append("Старе збереження гри має застарілий формат і не перенесене")
    return messages
