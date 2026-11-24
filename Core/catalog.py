import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional
from Core.characters import ApiProfileMapper, CharacterProfile
from Core.interfaces import ICharacterSource, IImageSource, ICatalogRepository, IPortraitStore

log = logging.getLogger("textgame.catalog")

ELEMENTS_UA = {"Pyro": "Піро", "Hydro": "Гідро", "Electro": "Електро", "Cryo": "Кріо",
               "Anemo": "Анемо", "Geo": "Гео", "Dendro": "Дендро"}
WEAPONS_UA = {"Sword": "Меч", "Claymore": "Дворучний меч", "Polearm": "Спис", "Bow": "Лук",
              "Catalyst": "Каталізатор"}


@dataclass
class CatalogEntry:
    slug: str
    name: str
    title: str = ""
    vision: str = ""
    weapon: str = ""
    nation: str = ""
    affiliation: str = ""
    rarity: int = 0
    birthday: str = ""
    constellation: str = ""
    description: str = ""
    icon_url: str = ""
    portrait: str = ""

    @property
    def stars(self) -> str:
        return "★" * self.rarity if self.rarity else "—"

    @property
    def element_ua(self) -> str:
        return ELEMENTS_UA.get(self.vision, self.vision or "—")

    @property
    def weapon_ua(self) -> str:
        return WEAPONS_UA.get(self.weapon, self.weapon or "—")

    @property
    def short_info(self) -> str:
        return " · ".join(x for x in (self.element_ua, self.weapon_ua, self.nation) if x and x != "—")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'CatalogEntry':
        known = CatalogEntry.__dataclass_fields__
        return CatalogEntry(**{k: v for k, v in data.items() if k in known})

    def to_api_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "vision": self.vision, "weapon": self.weapon,
                "rarity": self.rarity, "description": self.description}


class CatalogParser:
    """Перетворює сиру JSON-відповідь API на CatalogEntry, перевіряючи й нормалізуючи поля."""

    MAX_DESCRIPTION = 400

    @staticmethod
    def _text(raw: Dict[str, Any], key: str) -> str:
        value = raw.get(key)
        return re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else ""

    @staticmethod
    def _birthday(value: Any) -> str:
        match = re.fullmatch(r"\d{4}-(\d{2})-(\d{2})", str(value or ""))
        return f"{match.group(2)}.{match.group(1)}" if match else ""

    @staticmethod
    def _rarity(value: Any) -> int:
        try:
            return max(0, min(5, int(value)))
        except (TypeError, ValueError):
            return 0

    @classmethod
    def parse(cls, slug: str, raw: Any, icon_url: str = "") -> Optional[CatalogEntry]:
        if not isinstance(raw, dict):
            return None
        name = cls._text(raw, "name")
        if not name:
            return None
        description = cls._text(raw, "description")
        if len(description) > cls.MAX_DESCRIPTION:
            description = description[:cls.MAX_DESCRIPTION - 1].rstrip() + "…"
        return CatalogEntry(
            slug=slug, name=name, title=cls._text(raw, "title"), vision=cls._text(raw, "vision"),
            weapon=cls._text(raw, "weapon"), nation=cls._text(raw, "nation"),
            affiliation=cls._text(raw, "affiliation"), rarity=cls._rarity(raw.get("rarity")),
            birthday=cls._birthday(raw.get("birthday")), constellation=cls._text(raw, "constellation"),
            description=description, icon_url=icon_url,
        )


@dataclass
class RefreshResult:
    total: int = 0
    added: int = 0
    failed: List[str] = field(default_factory=list)
    offline: bool = False


class CharacterCatalog:
    """Каталог усіх доступних персонажів з API з локальним кешем даних і портретів."""

    def __init__(self, source: ICharacterSource, images: IImageSource,
                 repository: ICatalogRepository, portraits: IPortraitStore, workers: int = 8):
        self.source = source
        self.images = images
        self.repository = repository
        self.portraits = portraits
        self.workers = workers
        self._entries: Dict[str, CatalogEntry] = {}
        self._lock = threading.RLock()
        self.requests = 0

    def load_cached(self) -> int:
        with self._lock:
            self._entries.clear()
            for item in self.repository.load_entries():
                if isinstance(item, dict) and item.get("slug") and item.get("name"):
                    entry = CatalogEntry.from_dict(item)
                    entry.portrait = self.portraits.find(entry.slug) or ""
                    self._entries[entry.slug] = entry
            return len(self._entries)

    def entries(self, query: str = "") -> List[CatalogEntry]:
        query = query.strip().lower()
        with self._lock:
            items = sorted(self._entries.values(), key=lambda e: e.name.lower())
        if not query:
            return items
        return [e for e in items if query in " ".join(
            (e.slug, e.name, e.vision, e.weapon, e.nation, e.element_ua, e.weapon_ua)).lower()]

    def get(self, slug: str) -> Optional[CatalogEntry]:
        with self._lock:
            return self._entries.get(slug.lower().strip())

    def is_empty(self) -> bool:
        with self._lock:
            return not self._entries

    def _fetch_one(self, slug: str) -> Optional[CatalogEntry]:
        self.requests += 1
        entry = CatalogParser.parse(slug, self.source.fetch(slug), self.images.image_url(slug))
        if entry:
            entry.portrait = self.portraits.find(slug) or ""
        return entry

    def refresh(self, progress: Optional[Callable[[int, int], None]] = None) -> RefreshResult:
        self.requests += 1
        names = [n for n in self.source.list_names() if isinstance(n, str) and n.strip()]
        result = RefreshResult(total=len(names))
        if not names:
            result.offline = True
            return result
        done = 0
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            for slug, entry in zip(names, pool.map(self._fetch_one, names)):
                done += 1
                if entry is None:
                    result.failed.append(slug)
                else:
                    with self._lock:
                        if slug not in self._entries:
                            result.added += 1
                        self._entries[slug] = entry
                if progress:
                    progress(done, len(names))
        self.save()
        log.info("Каталог оновлено: %d записів, помилок %d", result.total, len(result.failed))
        return result

    def save(self) -> None:
        with self._lock:
            data = [e.to_dict() for e in self.entries()]
        for item in data:
            item["portrait"] = ""
        self.repository.save_entries(data)

    def portrait(self, slug: str, download: bool = True) -> Optional[str]:
        entry = self.get(slug)
        if entry is None:
            return None
        cached = self.portraits.find(entry.slug)
        if cached or not download:
            entry.portrait = cached or ""
            return cached
        self.requests += 1
        image = self.images.fetch_image(entry.slug)
        if not image:
            return None
        data, ext = image
        entry.portrait = self.portraits.put(entry.slug, data, ext)
        return entry.portrait

    def download_portraits(self, slugs: Optional[List[str]] = None,
                           progress: Optional[Callable[[int, int], None]] = None) -> int:
        slugs = slugs if slugs is not None else [e.slug for e in self.entries()]
        loaded = 0
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            for done, path in enumerate(pool.map(self.portrait, slugs), 1):
                loaded += 1 if path else 0
                if progress:
                    progress(done, len(slugs))
        return loaded

    def to_profile(self, slug: str) -> Optional[CharacterProfile]:
        entry = self.get(slug)
        if entry is None:
            return None
        profile = ApiProfileMapper.from_api(entry.to_api_dict())
        profile.id = entry.slug
        if entry.icon_url:
            profile.gfx_url = entry.icon_url
        return profile
