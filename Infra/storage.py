import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Mapping
from Core.interfaces import IProfileRepository, IGameRepository

APP_NAME = "OOPTextGame"
LINUX_APP_NAME = "oop-text-game"
ENV_HOME = "OOP_GAME_HOME"
FILE_FORMAT = "oop-text-game"
FILE_VERSION = 3


class AppDataLocator:
    @staticmethod
    def resolve(env: Optional[Mapping[str, str]] = None, platform: Optional[str] = None,
                home: Optional[Path] = None) -> Path:
        env = os.environ if env is None else env
        platform = platform or sys.platform
        home = Path(home) if home else Path.home()
        if env.get(ENV_HOME):
            return Path(env[ENV_HOME])
        if platform.startswith("win"):
            base = env.get("APPDATA") or str(home / "AppData" / "Roaming")
            return Path(base) / APP_NAME
        if platform == "darwin":
            return home / "Library" / "Application Support" / APP_NAME
        base = env.get("XDG_DATA_HOME") or str(home / ".local" / "share")
        return Path(base) / LINUX_APP_NAME


class JsonFileStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.warnings: List[str] = []

    def path(self, relative: str) -> Path:
        return self.root / relative

    def write(self, relative: str, kind: str, payload: Any) -> Path:
        target = self.path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "format": FILE_FORMAT, "version": FILE_VERSION, "kind": kind,
            "written_at": datetime.now().isoformat(timespec="seconds"), "data": payload,
        }
        tmp = target.with_name(target.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(envelope, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
        return target

    def read(self, relative: str, kind: str) -> Optional[Any]:
        target = self.path(relative)
        if not target.exists():
            return None
        try:
            with open(target, "r", encoding="utf-8") as f:
                envelope = json.load(f)
            if not isinstance(envelope, dict) or envelope.get("format") != FILE_FORMAT:
                raise ValueError("невідомий формат файлу")
            if envelope.get("kind") != kind:
                raise ValueError(f"очікувався тип '{kind}'")
            if envelope.get("version", 0) > FILE_VERSION:
                raise ValueError("файл створено новішою версією гри")
            return envelope.get("data")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as e:
            self._quarantine(target, str(e))
            return None

    def _quarantine(self, target: Path, reason: str) -> None:
        backup = target.with_name(target.name + ".corrupt")
        try:
            os.replace(target, backup)
            self.warnings.append(f"Файл {target.name} пошкоджений ({reason}), його перейменовано на {backup.name}")
        except OSError:
            self.warnings.append(f"Файл {target.name} пошкоджений ({reason})")

    def delete(self, relative: str) -> bool:
        target = self.path(relative)
        if target.exists():
            target.unlink()
            return True
        return False

    def list(self, folder: str, suffix: str = ".json") -> List[str]:
        directory = self.path(folder)
        if not directory.is_dir():
            return []
        return sorted(f"{folder}/{p.name}" for p in directory.iterdir() if p.is_file() and p.name.endswith(suffix))


class JsonProfileRepository(IProfileRepository):
    FILE = "characters.json"
    KIND = "characters"

    def __init__(self, store: JsonFileStore):
        self.store = store

    def load_profiles(self) -> List[Dict[str, Any]]:
        data = self.store.read(self.FILE, self.KIND)
        return list(data) if isinstance(data, list) else []

    def save_profiles(self, profiles: List[Dict[str, Any]]) -> None:
        self.store.write(self.FILE, self.KIND, profiles)


class JsonGameRepository(IGameRepository):
    FOLDER = "saves"
    KIND = "save"

    def __init__(self, store: JsonFileStore):
        self.store = store

    def _file(self, slot: str) -> str:
        return f"{self.FOLDER}/{slot}.json"

    def save_game(self, slot: str, data: Dict[str, Any]) -> None:
        self.store.write(self._file(slot), self.KIND, data)

    def load_game(self, slot: str) -> Optional[Dict[str, Any]]:
        data = self.store.read(self._file(slot), self.KIND)
        return data if isinstance(data, dict) else None

    def list_saves(self) -> List[Dict[str, Any]]:
        result = []
        for relative in self.store.list(self.FOLDER):
            data = self.store.read(relative, self.KIND)
            if isinstance(data, dict) and isinstance(data.get("meta"), dict):
                result.append(data["meta"])
        return result

    def delete_save(self, slot: str) -> bool:
        return self.store.delete(self._file(slot))


class LegacyRepositoryFile:
    def __init__(self, path: Path):
        self.path = Path(path)

    def read(self) -> Optional[Dict[str, Any]]:
        if not self.path.exists():
            return None
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def modified_at(self) -> str:
        return datetime.fromtimestamp(self.path.stat().st_mtime).isoformat(timespec="seconds")

    def mark_migrated(self) -> None:
        os.replace(self.path, self.path.with_name(self.path.name + ".migrated"))
