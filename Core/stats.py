from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List

STAT_NAMES = ("health", "damage", "magic", "armor", "resist", "res_pen", "speed")
SPECIAL_MODIFIERS = ("power", "weaken")


@dataclass
class Stats:
    health: int = 100
    damage: int = 10
    magic: int = 0
    armor: int = 0
    resist: float = 0.0
    res_pen: float = 0.0
    speed: int = 100

    def copy(self) -> 'Stats':
        return Stats(**asdict(self))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Stats':
        return Stats(**{k: data[k] for k in STAT_NAMES if k in data})


@dataclass
class Modifier:
    stat: str
    value: float

    def __post_init__(self):
        if self.stat not in STAT_NAMES + SPECIAL_MODIFIERS:
            raise ValueError(f"Невідома характеристика модифікатора: {self.stat}")

    def to_dict(self) -> Dict[str, Any]:
        return {"stat": self.stat, "value": self.value}

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Modifier':
        return Modifier(data["stat"], data["value"])


@dataclass
class StatusEffect:
    name: str
    kind: str
    duration: int
    modifiers: List[Modifier] = field(default_factory=list)
    hp_per_turn: int = 0
    applied_turn: int = 0

    def copy(self) -> 'StatusEffect':
        return StatusEffect(self.name, self.kind, self.duration,
                            [Modifier(m.stat, m.value) for m in self.modifiers],
                            self.hp_per_turn, self.applied_turn)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "kind": self.kind, "duration": self.duration,
            "modifiers": [m.to_dict() for m in self.modifiers],
            "hp_per_turn": self.hp_per_turn, "applied_turn": self.applied_turn,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'StatusEffect':
        return StatusEffect(
            data["name"], data["kind"], data["duration"],
            [Modifier.from_dict(m) for m in data.get("modifiers", [])],
            data.get("hp_per_turn", 0), data.get("applied_turn", 0),
        )


@dataclass
class Item:
    item_id: str
    name: str
    modifiers: List[Modifier] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"item_id": self.item_id, "name": self.name,
                "modifiers": [m.to_dict() for m in self.modifiers]}

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Item':
        return Item(data["item_id"], data["name"],
                    [Modifier.from_dict(m) for m in data.get("modifiers", [])])
