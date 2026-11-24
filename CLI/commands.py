from typing import Callable, Optional
from CLI.presenter import BaseCommandStrategy, Command, Args, CLI
from Core.catalog import CharacterCatalog
from Core.characters import CharacterManager, CharacterProfile, CharacterService
from Core.combatant import CombatantFactory, EnemyLibrary
from Core.game import Game
from Core.actions import GameRuleError
from Core.skills import SkillLibrary
from Core.stats import Stats
from Core.saves import SaveManager, ProfileStorage, SaveError, SaveInfo, DEFAULT_SLOT, BUILTIN
from Infra.display import (CLIGraphic, ProfileConsoleRenderer, GameConsoleRenderer,
                           HistoryConsoleRenderer)

DEFAULT_ENEMIES = ["goblin", "slime"]
STATUS_NAMES = {"idle": "—", "active": "Триває", "won": "Перемога", "lost": "Поразка"}
SOURCE_NAMES = {BUILTIN: "вбудований", "custom": "власний", "api": "API"}


def format_save(info: SaveInfo) -> str:
    when = info.saved_at.replace("T", " ")[:19]
    return f"«{info.slot}» від {when}, крок {info.turn}, {STATUS_NAMES.get(info.status, info.status)}"


class CatalogStrategy(BaseCommandStrategy):
    def __init__(self, manager: CharacterManager, service: CharacterService,
                 storage: ProfileStorage, cli: CLI, reader: Callable[[str], str] = input):
        super().__init__()
        self.manager = manager
        self.service = service
        self.storage = storage
        self.cli = cli
        self.read = reader
        self.renderer = ProfileConsoleRenderer()

        self.register_command(Command("list", "Список персонажів у каталозі", self._cmd_list))
        self.register_command(Command("show", "Деталі персонажа (show <id>)", self._cmd_show))
        self.register_command(Command("create", "Створити власного персонажа (зберігається одразу)", self._cmd_create))
        self.register_command(Command("import", "Завантажити персонажа з API (import <name>)", self._cmd_import))
        self.register_command(Command("sources", "Імена, доступні для імпорту", self._cmd_sources))
        self.register_command(Command("delete", "Видалити власного персонажа (delete <id>)", self._cmd_delete))
        self.register_command(Command("save", "Примусово зберегти каталог персонажів", self._cmd_save))

    def _persist(self) -> bool:
        try:
            self.storage.save()
            return True
        except OSError as e:
            print(f"[Помилка збереження] {e}")
            return False

    def _cmd_list(self, args: Args) -> bool:
        profiles = self.manager.get_all()
        if not profiles:
            print("Каталог порожній.")
            return True
        print(CLIGraphic.banner("КАТАЛОГ ПЕРСОНАЖІВ"))
        rows = [[p.id, p.name, p.char_class, str(p.stats.health), str(p.stats.damage),
                 str(p.stats.magic), str(p.stats.armor), str(p.stats.speed), SOURCE_NAMES.get(p.source, p.source)]
                for p in profiles]
        print(CLIGraphic.table(["ID", "Ім'я", "Клас", "HP", "Шкода", "Магія", "Броня", "Шв.", "Тип"], rows))
        return True

    def _cmd_show(self, args: Args) -> bool:
        if not args.params:
            print("Вкажіть ID (напр. show warrior_1)")
            return True
        profile = self.manager.get_character(args.params[0])
        if not profile:
            print("Не знайдено.")
            return True
        profile.use_renderer(self.renderer)
        self.cli.display(profile)
        return True

    def _ask_int(self, prompt: str, default: int) -> int:
        raw = self.read(f"{prompt} [{default}]: ").strip()
        return int(raw) if raw else default

    def _cmd_create(self, args: Args) -> bool:
        print(CLIGraphic.banner("СТВОРЕННЯ ПЕРСОНАЖА"))
        char_id = self.read("ID: ").strip()
        name = self.read("Ім'я: ").strip()
        if not char_id or not name:
            print("ID та ім'я обов'язкові.")
            return True
        existing = self.manager.get_character(char_id)
        if existing and existing.source == BUILTIN:
            print("Цей ID зайнятий вбудованим персонажем.")
            return True
        classes = ", ".join(SkillLibrary.CLASS_SKILLS)
        char_class = self.read(f"Клас ({classes}): ").strip() or "Воїн"
        try:
            stats = Stats(
                health=self._ask_int("Здоров'я", 100),
                damage=self._ask_int("Шкода", 15),
                magic=self._ask_int("Магія", 5),
                armor=self._ask_int("Броня", 5),
                resist=self._ask_int("Резист, %", 10) / 100,
                speed=self._ask_int("Швидкість", 100),
            )
        except ValueError:
            print("Характеристики мають бути числами!")
            return True
        if stats.health <= 0 or stats.speed <= 0:
            print("Здоров'я та швидкість мають бути більшими за 0.")
            return True
        gfx_url = self.read("Графіка (URL): ").strip() or "default.png"
        self.manager.add_character(CharacterProfile(char_id, name, char_class, stats, gfx_url=gfx_url))
        if self._persist():
            print(f"Персонажа {name} створено і збережено. Навички: {', '.join(SkillLibrary.for_class(char_class))}.")
        return True

    def _cmd_import(self, args: Args) -> bool:
        if not args.params:
            print("Вкажіть ім'я (напр. import diluc). Список: sources")
            return True
        try:
            profile = self.service.import_character(args.params[0])
        except LookupError as e:
            print(e)
            return True
        if self._persist():
            print(f"Імпортовано і збережено: {profile.name} [{profile.id}] — клас {profile.char_class}")
        return True

    def _cmd_sources(self, args: Args) -> bool:
        names = self.service.available_names()
        print("Доступні для імпорту: " + (", ".join(names) if names else "немає"))
        return True

    def _cmd_delete(self, args: Args) -> bool:
        if not args.params:
            print("Вкажіть ID (напр. delete my_hero).")
            return True
        try:
            self.storage.delete(args.params[0])
        except SaveError as e:
            print(f"[Неможливо] {e}")
            return True
        print("Персонажа видалено.")
        return True

    def _cmd_save(self, args: Args) -> bool:
        if self._persist():
            print(f"Каталог збережено (власних персонажів: {len(self.storage.user_profiles())}).")
        return True


class GameStrategy(BaseCommandStrategy):
    def __init__(self, game: Game, manager: CharacterManager, saves: SaveManager, cli: CLI):
        super().__init__()
        self.game = game
        self.manager = manager
        self.saves = saves
        self.cli = cli
        self.game_renderer = GameConsoleRenderer()
        self.history_renderer = HistoryConsoleRenderer()

        self.register_command(Command("play_start",
                                      "Почати бій (play_start <id> [<id>...] [--enemies=goblin,wolf])",
                                      self._cmd_start))
        self.register_command(Command("play_action", "Дія героя (play_action <дія> [ціль])", self._cmd_action))
        self.register_command(Command("play_status", "Стан бою і доступні дії", self._cmd_status))
        self.register_command(Command("play_history", "Історія кроків (play_history [--last=N])", self._cmd_history))
        self.register_command(Command("continue", "Продовжити з останнього збереження", self._cmd_continue))
        self.register_command(Command("game_save", f"Зберегти гру у слот (game_save [слот], типово {DEFAULT_SLOT})",
                                      self._cmd_save))
        self.register_command(Command("game_load", "Завантажити гру зі слоту (game_load [слот])", self._cmd_load))
        self.register_command(Command("saves", "Список збережень", self._cmd_saves))
        self.register_command(Command("save_delete", "Видалити збереження (save_delete <слот>)", self._cmd_save_delete))
        self.register_command(Command("enemies", "Список типів ворогів", self._cmd_enemies))
        self.register_command(Command("skills", "Довідник навичок", self._cmd_skills))

    def _print_records(self, records) -> None:
        for r in records:
            prefix = f"[Крок {r.turn}] " if r.actor != "system" else ""
            print(f"{prefix}{r.text}")

    def autosave(self) -> None:
        try:
            self.saves.autosave(self.game)
        except (OSError, SaveError) as e:
            print(f"[Автозбереження не вдалося] {e}")

    def _cmd_start(self, args: Args) -> bool:
        if not args.params:
            print("Вкажіть ID персонажів (напр. play_start warrior_1).")
            return True
        heroes = []
        for i, pid in enumerate(args.params, start=1):
            profile = self.manager.get_character(pid)
            if not profile:
                print(f"Персонажа '{pid}' не знайдено.")
                return True
            heroes.append(CombatantFactory.from_profile(profile, f"h{i}"))
        enemy_ids = [e for e in args.flags.get("enemies", ",".join(DEFAULT_ENEMIES)).split(",") if e]
        unknown = [e for e in enemy_ids if not EnemyLibrary.exists(e)]
        if unknown:
            print(f"Невідомі вороги: {', '.join(unknown)}. Див. 'enemies'.")
            return True
        enemies = [CombatantFactory.from_template(t, f"e{i}") for i, t in enumerate(enemy_ids, start=1)]
        self.game = Game(self.game.calculator, self.game.behavior)
        print(CLIGraphic.banner("ТЕКСТОВА ГРА"))
        self._print_records(self.game.start(heroes, enemies))
        self.autosave()
        self._cmd_status(args)
        return True

    def _cmd_action(self, args: Args) -> bool:
        if not args.params:
            print("Вкажіть дію (напр. play_action attack e1).")
            return True
        target = args.params[1] if len(args.params) > 1 else None
        try:
            records = self.game.act(args.params[0], target)
        except GameRuleError as e:
            print(f"[Неможливо] {e}")
            return True
        self._print_records(records)
        self.autosave()
        if self.game.is_active:
            actor = self.game.current_actor
            print(f"\nХід героя: {actor.name} ({actor.uid}). 'play_status' — деталі.")
        else:
            print(f"\nГру завершено. Рахунок: {self.game.score}")
        return True

    def _cmd_status(self, args: Args) -> bool:
        self.game.use_renderer(self.game_renderer)
        self.cli.display(self.game)
        return True

    def _cmd_history(self, args: Args) -> bool:
        records = self.game.all_records()
        last: Optional[str] = args.flags.get("last")
        if last and last.isdigit():
            turns = sorted({r.turn for r in records})[-int(last):]
            records = [r for r in records if r.turn in turns]
        print(CLIGraphic.banner("ІСТОРІЯ БОЮ"))
        print(self.history_renderer.render(records))
        return True

    def _load_slot(self, slot: str) -> bool:
        try:
            self.game = self.saves.load(slot, self.game.calculator, self.game.behavior)
        except SaveError as e:
            print(f"[Неможливо] {e}")
            return False
        print(f"Гру відновлено зі слоту «{slot}».")
        self._cmd_status(Args("", "play_status", [], {}))
        return True

    def _cmd_continue(self, args: Args) -> bool:
        latest = self.saves.latest()
        if latest is None:
            print("Збережень ще немає. Почніть гру: play_start <id>.")
            return True
        print(f"Останнє збереження: {format_save(latest)}")
        self._load_slot(latest.slot)
        return True

    def _cmd_save(self, args: Args) -> bool:
        slot = args.params[0] if args.params else DEFAULT_SLOT
        try:
            info = self.saves.save(self.game, slot)
        except SaveError as e:
            print(f"[Неможливо] {e}")
            return True
        except OSError as e:
            print(f"[Помилка запису] {e}")
            return True
        print(f"Збережено: {format_save(info)}")
        return True

    def _cmd_load(self, args: Args) -> bool:
        if not args.params:
            return self._cmd_continue(args)
        self._load_slot(args.params[0])
        return True

    def _cmd_saves(self, args: Args) -> bool:
        saves = self.saves.list_saves()
        if not saves:
            print("Збережень немає.")
            return True
        print(CLIGraphic.banner("ЗБЕРЕЖЕННЯ"))
        rows = [[s.slot + (" (авто)" if s.is_auto else ""), s.saved_at.replace("T", " ")[:19], str(s.turn),
                 STATUS_NAMES.get(s.status, s.status), str(s.score), ", ".join(s.heroes)] for s in saves]
        print(CLIGraphic.table(["Слот", "Збережено", "Крок", "Статус", "Очки", "Герої"], rows))
        return True

    def _cmd_save_delete(self, args: Args) -> bool:
        if not args.params:
            print("Вкажіть слот (напр. save_delete slot1).")
            return True
        try:
            deleted = self.saves.delete(args.params[0])
        except SaveError as e:
            print(f"[Неможливо] {e}")
            return True
        print("Збереження видалено." if deleted else "Такого збереження немає.")
        return True

    def _cmd_enemies(self, args: Args) -> bool:
        rows = []
        for tid in EnemyLibrary.ids():
            t = EnemyLibrary.describe(tid)
            s = t["stats"]
            rows.append([tid, t["name"], str(s.health), str(s.damage), str(s.magic),
                         str(s.armor), f"{int(s.resist * 100)}%", str(s.speed)])
        print(CLIGraphic.table(["ID", "Назва", "HP", "Шкода", "Магія", "Броня", "Резист", "Шв."], rows))
        return True

    def _cmd_skills(self, args: Args) -> bool:
        rows = [[s.skill_id, s.name, s.kind, str(s.power), str(s.cooldown), s.description]
                for s in SkillLibrary.all()]
        print(CLIGraphic.table(["ID", "Назва", "Тип", "Сила", "Перезар.", "Опис"], rows))
        return True


class RosterStrategy(BaseCommandStrategy):
    """Каталог усіх персонажів з API: список, деталі, портрети, додавання у гру."""

    def __init__(self, catalog: CharacterCatalog, manager: CharacterManager, storage: ProfileStorage):
        super().__init__()
        self.catalog = catalog
        self.manager = manager
        self.storage = storage
        self.register_command(Command("catalog", "Усі персонажі з API (catalog [пошук] [--refresh])", self._cmd_catalog))
        self.register_command(Command("catalog_refresh", "Оновити каталог з сервера", self._cmd_refresh))
        self.register_command(Command("catalog_show", "Інформація і графіка (catalog_show <slug>)", self._cmd_show))
        self.register_command(Command("portraits", "Завантажити портрети у кеш (portraits [slug|--all])",
                                      self._cmd_portraits))
        self.register_command(Command("catalog_add", "Додати персонажа з каталогу у гру (catalog_add <slug>)",
                                      self._cmd_add))

    def _ensure_loaded(self) -> None:
        if self.catalog.is_empty():
            print("Локальний каталог порожній — завантажую з сервера…")
            self._cmd_refresh(None)

    def _cmd_refresh(self, args) -> bool:
        result = self.catalog.refresh()
        if result.offline:
            print("[Немає з'єднання] Сервер недоступний, показано збережений каталог.")
            return True
        print(f"Каталог оновлено: {result.total} персонажів, нових {result.added}.")
        if result.failed:
            print(f"Не вдалося отримати: {', '.join(result.failed[:10])}" + (" …" if len(result.failed) > 10 else ""))
        return True

    def _cmd_catalog(self, args: Args) -> bool:
        if "refresh" in args.flags:
            self._cmd_refresh(args)
        else:
            self._ensure_loaded()
        entries = self.catalog.entries(" ".join(args.params))
        if not entries:
            print("Нічого не знайдено.")
            return True
        print(CLIGraphic.banner(f"КАТАЛОГ API ({len(entries)})"))
        rows = [[e.slug, e.name, e.stars, e.element_ua, e.weapon_ua, e.nation or "—",
                 "файл" if e.portrait else (e.icon_url or "—")] for e in entries]
        print(CLIGraphic.table(["Slug", "Ім'я", "Рідк.", "Стихія", "Зброя", "Регіон", "Графіка"], rows))
        print("Деталі: catalog_show <slug>; у гру: catalog_add <slug>")
        return True

    def _cmd_show(self, args: Args) -> bool:
        if not args.params:
            print("Вкажіть slug (напр. catalog_show diluc)")
            return True
        self._ensure_loaded()
        entry = self.catalog.get(args.params[0])
        if not entry:
            print("У каталозі такого персонажа немає. Спробуйте catalog_refresh.")
            return True
        path = self.catalog.portrait(entry.slug, download="no-download" not in args.flags)
        print(CLIGraphic.banner(entry.name.upper()))
        lines = [("Титул", entry.title), ("Рідкість", entry.stars), ("Стихія", entry.element_ua),
                 ("Зброя", entry.weapon_ua), ("Регіон", entry.nation), ("Організація", entry.affiliation),
                 ("Сузір'я", entry.constellation), ("День народження", entry.birthday),
                 ("Графіка (URL)", entry.icon_url), ("Портрет (файл)", path or "не завантажено")]
        for label, value in lines:
            if value:
                print(f"{label + ':':<17} {value}")
        if entry.description:
            print(f"\n{entry.description}")
        in_game = self.manager.get_character(entry.slug)
        print("\nУ грі: так" if in_game else f"\nДодати у гру: catalog_add {entry.slug}")
        return True

    def _cmd_portraits(self, args: Args) -> bool:
        self._ensure_loaded()
        slugs = None if ("all" in args.flags or not args.params) else [s.lower() for s in args.params]
        before = sum(1 for e in self.catalog.entries() if e.portrait)
        loaded = self.catalog.download_portraits(slugs)
        after = sum(1 for e in self.catalog.entries() if e.portrait)
        print(f"Портретів у кеші: {after} (нових завантажено: {max(0, after - before)}, доступно {loaded}).")
        return True

    def _cmd_add(self, args: Args) -> bool:
        if not args.params:
            print("Вкажіть slug (напр. catalog_add diluc)")
            return True
        self._ensure_loaded()
        profile = self.catalog.to_profile(args.params[0])
        if profile is None:
            print("У каталозі такого персонажа немає.")
            return True
        existing = self.manager.get_character(profile.id)
        if existing and existing.source == BUILTIN:
            print("Цей ID зайнятий вбудованим персонажем.")
            return True
        self.manager.add_character(profile)
        try:
            self.storage.save()
        except OSError as e:
            print(f"[Помилка збереження] {e}")
            return True
        print(f"{profile.name} [{profile.id}] тепер доступний для гри — клас {profile.char_class}.")
        return True


class SystemStrategy(BaseCommandStrategy):
    def __init__(self, cli: CLI, data_dir: str = ""):
        super().__init__()
        self.cli = cli
        self.data_dir = data_dir
        self.register_command(Command("help", "Довідка", self._cmd_help))
        self.register_command(Command("storage", "Де зберігаються дані гри", self._cmd_storage))
        self.register_command(Command("version", "Версія програми", self._cmd_version))

    def _cmd_help(self, args: Args) -> bool:
        print(CLIGraphic.banner("ДОВІДКА"))
        rows = [[selector, desc] for selector, desc in self.cli.get_all_commands().items()]
        rows.append(["exit", "Вийти"])
        print(CLIGraphic.table(["Команда", "Опис"], rows))
        return True

    def _cmd_version(self, args: Args) -> bool:
        from version import __version__, APP_TITLE, AUTHOR
        mode = "debug" if getattr(self.cli, "debug", False) else "release"
        print(f"{APP_TITLE} {__version__} ({mode}) — {AUTHOR}")
        return True

    def _cmd_storage(self, args: Args) -> bool:
        print(f"Папка даних: {self.data_dir}")
        print("  characters.json — власні та імпортовані персонажі")
        print("  saves/<слот>.json — збереження гри (autosave — автоматичне)")
        print("  catalog.json — кеш каталогу персонажів з API")
        print("  portraits/ — кеш портретів персонажів")
        print("  textgame.log — журнал роботи програми")
        return True
