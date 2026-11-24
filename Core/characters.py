import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from Core.interfaces import IRenderable, ICharacterSource
from Core.stats import Stats, Item
from Core.skills import SkillLibrary


@dataclass(eq=False)
class CharacterProfile(IRenderable['CharacterProfile']):
    id: str
    name: str
    char_class: str
    stats: Stats
    skills: List[str] = field(default_factory=list)
    items: List[Item] = field(default_factory=list)
    gfx_url: str = ""
    source: str = "custom"
    description: str = ""

    def __post_init__(self):
        IRenderable.__init__(self)
        if not self.skills:
            self.skills = SkillLibrary.for_class(self.char_class)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "char_class": self.char_class,
            "stats": self.stats.to_dict(), "skills": list(self.skills),
            "items": [i.to_dict() for i in self.items], "gfx_url": self.gfx_url,
            "source": self.source, "description": self.description,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'CharacterProfile':
        if "stats" in data:
            stats = Stats.from_dict(data["stats"])
        else:
            stats = Stats(health=data.get("max_hp", data.get("hp", 100)), damage=data.get("attack", 10))
        return CharacterProfile(
            data["id"], data["name"], data.get("char_class", ""), stats,
            [s for s in data.get("skills", []) if SkillLibrary.exists(s)],
            [Item.from_dict(i) for i in data.get("items", [])],
            data.get("gfx_url", ""), data.get("source", "custom"), data.get("description", ""),
        )


class CharacterManager:
    def __init__(self):
        self._characters: Dict[str, CharacterProfile] = {}

    def add_character(self, profile: CharacterProfile) -> None:
        self._characters[profile.id] = profile

    def clear(self) -> None:
        self._characters.clear()

    def remove_character(self, char_id: str) -> bool:
        return self._characters.pop(char_id, None) is not None

    def get_character(self, char_id: str) -> Optional[CharacterProfile]:
        return self._characters.get(char_id)

    def get_all(self) -> List[CharacterProfile]:
        return list(self._characters.values())

    def load_from_list(self, items: List[Dict[str, Any]]) -> None:
        self._characters.clear()
        for item in items:
            self.add_character(CharacterProfile.from_dict(item))

    def export_to_list(self) -> List[Dict[str, Any]]:
        return [p.to_dict() for p in self._characters.values()]


class ApiProfileMapper:
    VISION_CLASS = {
        "Pyro": "Маг", "Electro": "Маг", "Hydro": "Цілитель", "Dendro": "Цілитель",
        "Geo": "Воїн", "Anemo": "Лучник", "Cryo": "Лучник",
    }
    WEAPON_SPEED = {"Sword": 110, "Bow": 120, "Catalyst": 100, "Claymore": 85, "Polearm": 105}
    HEAVY_WEAPONS = ("Claymore", "Polearm")

    @staticmethod
    def slug(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unknown"

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> CharacterProfile:
        name = data.get("name") or "Невідомий"
        rarity = int(data.get("rarity", 4) or 4)
        vision = data.get("vision", "")
        weapon = data.get("weapon", "")
        char_class = cls.VISION_CLASS.get(vision, "Воїн")
        caster = char_class in ("Маг", "Цілитель")

        stats = Stats(
            health=80 + rarity * 10,
            damage=8 + rarity * 3,
            magic=rarity * 4 if caster else rarity * 2,
            armor=rarity * 2 + (4 if weapon in cls.HEAVY_WEAPONS else 0),
            resist=round(min(0.25, 0.04 * rarity), 2),
            speed=cls.WEAPON_SPEED.get(weapon, 100),
        )
        description = (data.get("description") or "").strip()
        return CharacterProfile(
            id=cls.slug(name), name=name, char_class=char_class, stats=stats,
            gfx_url=f"https://genshin.jmp.blue/characters/{cls.slug(name)}/icon",
            source="api", description=description[:200],
        )


class CharacterService:
    def __init__(self, manager: CharacterManager, source: ICharacterSource):
        self.manager = manager
        self.source = source

    def import_character(self, name: str) -> CharacterProfile:
        raw = self.source.fetch(name)
        if not raw:
            raise LookupError(f"Персонажа '{name}' не знайдено в джерелі даних")
        profile = ApiProfileMapper.from_api(raw)
        self.manager.add_character(profile)
        return profile

    def available_names(self) -> List[str]:
        return self.source.list_names()
