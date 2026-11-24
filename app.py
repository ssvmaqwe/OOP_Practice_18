import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional
from CLI.presenter import CLI
from CLI.commands import CatalogStrategy, GameStrategy, SystemStrategy, RosterStrategy
from Core.catalog import CharacterCatalog
from Core.characters import CharacterManager, CharacterProfile, CharacterService
from Core.game import Game
from Core.saves import SaveManager, ProfileStorage, migrate_legacy
from Core.stats import Stats, Item, Modifier
from Infra.storage import (AppDataLocator, JsonFileStore, JsonProfileRepository, JsonGameRepository,
                           LegacyRepositoryFile)
from Infra.api import GenshinApiSource, StubCharacterSource, FallbackCharacterSource, NoImageSource
from Infra.catalog_store import JsonCatalogRepository, FilePortraitStore
from version import __version__, APP_TITLE


def default_profiles() -> List[CharacterProfile]:
    return [
        CharacterProfile("warrior_1", "Артур", "Воїн", Stats(130, 24, 0, 8, 0.10, 0.0, 100),
                         items=[Item("sword", "Сталевий меч", [Modifier("damage", 6)])]),
        CharacterProfile("mage_1", "Мерлін", "Маг", Stats(85, 10, 22, 2, 0.25, 0.10, 110),
                         items=[Item("staff", "Посох мудреця", [Modifier("magic", 5), Modifier("power", 0.1)])]),
        CharacterProfile("healer_1", "Ліра", "Цілитель", Stats(95, 9, 20, 4, 0.20, 0.0, 105)),
    ]


@dataclass
class LaunchOptions:
    data_dir: Optional[Path] = None
    debug: bool = False
    show_version: bool = False
    rest: List[str] = field(default_factory=list)


def parse_launch_options(argv: List[str]) -> LaunchOptions:
    options = LaunchOptions()
    for arg in argv:
        if arg.startswith("--data-dir="):
            options.data_dir = Path(arg.split("=", 1)[1]).expanduser()
        elif arg == "--debug":
            options.debug = True
        elif arg in ("--version", "-V"):
            options.show_version = True
        else:
            options.rest.append(arg)
    return options


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        if (getattr(stream, "encoding", "") or "").lower().replace("-", "") != "utf8" and not stream.isatty():
            stream.reconfigure(encoding="utf-8", errors="replace")


def setup_logging(data_dir: Path, debug: bool) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    log_file = data_dir / "textgame.log"
    handlers = [logging.FileHandler(log_file, encoding="utf-8")]
    if debug and sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(level=logging.DEBUG if debug else logging.WARNING, handlers=handlers, force=True,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("textgame").info("Запуск %s %s (%s)", APP_TITLE, __version__,
                                        "debug" if debug else "release")
    return log_file


@dataclass
class AppContext:
    cli: CLI
    manager: CharacterManager
    storage: ProfileStorage
    saves: SaveManager
    game_strategy: GameStrategy
    data_dir: Path
    catalog: Optional[CharacterCatalog] = None
    messages: List[str] = field(default_factory=list)

    @property
    def game(self) -> Game:
        return self.game_strategy.game


def build_app(data_dir: Optional[Path] = None, reader: Callable[[str], str] = input,
              legacy_file: Optional[Path] = Path("repository.json"), online: bool = True,
              debug: bool = False) -> AppContext:
    data_dir = Path(data_dir) if data_dir else AppDataLocator.resolve()
    store = JsonFileStore(data_dir)
    manager = CharacterManager()
    storage = ProfileStorage(manager, JsonProfileRepository(store))
    saves = SaveManager(JsonGameRepository(store))
    api = GenshinApiSource()
    source = FallbackCharacterSource(api, StubCharacterSource()) if online else StubCharacterSource()
    service = CharacterService(manager, source)
    catalog = CharacterCatalog(source, api if online else NoImageSource(),
                               JsonCatalogRepository(store), FilePortraitStore(data_dir))

    messages: List[str] = []
    try:
        storage.load(default_profiles())
        catalog.load_cached()
        if legacy_file is not None:
            legacy = LegacyRepositoryFile(legacy_file)
            legacy_data = legacy.read()
            if legacy_data:
                messages += migrate_legacy(legacy_data, storage, saves, legacy.modified_at())
                legacy.mark_migrated()
    except OSError as e:
        messages.append(f"[Попередження] Не вдалося прочитати дані: {e}")
    messages += [f"[Попередження] {w}" for w in store.warnings]

    cli = CLI(debug=debug)
    game_strategy = GameStrategy(Game(), manager, saves, cli)
    cli.use_strategy(CatalogStrategy(manager, service, storage, cli, reader))
    cli.use_strategy(RosterStrategy(catalog, manager, storage))
    cli.use_strategy(game_strategy)
    cli.use_strategy(SystemStrategy(cli, str(data_dir)))
    return AppContext(cli, manager, storage, saves, game_strategy, data_dir, catalog, messages)
