from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
from Core.catalog import CharacterCatalog, CatalogEntry, RefreshResult
from GUI.viewmodel import GameViewModel

CARDS = "cards"
PORTRAIT = "portrait"
PROGRESS = "progress"


@dataclass(frozen=True)
class CardData:
    slug: str
    name: str
    title: str
    stars: str
    info: str
    details: str
    description: str
    icon_url: str
    portrait: str
    in_game: bool

    @property
    def initials(self) -> str:
        parts = [p for p in self.name.replace("-", " ").split() if p]
        return "".join(p[0] for p in parts[:2]).upper() or "?"


class CatalogViewModel:
    """Стан вкладки «Каталог»: картки, фільтр, оновлення і портрети.

    Мережеві операції (refresh, load_portrait) викликаються з фонового потоку,
    тому вони не звертаються до віджетів — лише повертають дані та сповіщають слухачів.
    """

    def __init__(self, catalog: CharacterCatalog, game_vm: GameViewModel):
        self.catalog = catalog
        self.game_vm = game_vm
        self.query = ""
        self._listeners: Dict[str, List[Callable]] = {CARDS: [], PORTRAIT: [], PROGRESS: []}

    def subscribe(self, event: str, callback: Callable) -> None:
        self._listeners[event].append(callback)

    def _emit(self, event: str, *args) -> None:
        for callback in self._listeners[event]:
            callback(*args)

    @staticmethod
    def _card(entry: CatalogEntry, in_game: bool) -> CardData:
        details = "\n".join(f"{k}: {v}" for k, v in (
            ("Титул", entry.title), ("Регіон", entry.nation), ("Організація", entry.affiliation),
            ("Сузір'я", entry.constellation), ("День народження", entry.birthday)) if v)
        return CardData(entry.slug, entry.name, entry.title, entry.stars, entry.short_info, details,
                        entry.description, entry.icon_url, entry.portrait, in_game)

    def set_query(self, query: str) -> None:
        self.query = query
        self._emit(CARDS)

    def cards(self) -> List[CardData]:
        manager = self.game_vm.ctx.manager
        return [self._card(e, manager.get_character(e.slug) is not None)
                for e in self.catalog.entries(self.query)]

    def summary(self) -> str:
        entries = self.catalog.entries()
        shown = len(self.catalog.entries(self.query))
        with_portrait = sum(1 for e in entries if e.portrait)
        return f"Персонажів: {shown} з {len(entries)} · портретів у кеші: {with_portrait}"

    @property
    def needs_refresh(self) -> bool:
        return self.catalog.is_empty()

    def refresh(self) -> RefreshResult:
        result = self.catalog.refresh(lambda done, total: self._emit(PROGRESS, done, total))
        self._emit(CARDS)
        return result

    @staticmethod
    def describe(result: RefreshResult) -> str:
        if result.offline:
            return "Сервер недоступний — показано збережений каталог."
        text = f"Каталог оновлено: {result.total} персонажів, нових {result.added}."
        if result.failed:
            text += f" Не отримано: {len(result.failed)}."
        return text

    def load_portrait(self, slug: str) -> Optional[str]:
        path = self.catalog.portrait(slug)
        if path:
            self._emit(PORTRAIT, slug, path)
        return path

    def add_to_game(self, slug: str) -> str:
        text = self.game_vm.execute(f"catalog_add {slug}")
        self._emit(CARDS)
        return text
