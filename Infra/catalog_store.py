import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from Core.interfaces import ICatalogRepository, IPortraitStore
from Infra.storage import JsonFileStore

IMAGE_EXTENSIONS = ("png", "webp", "jpg")


class JsonCatalogRepository(ICatalogRepository):
    FILE = "catalog.json"
    KIND = "catalog"

    def __init__(self, store: JsonFileStore):
        self.store = store

    def load_entries(self) -> List[Dict[str, Any]]:
        data = self.store.read(self.FILE, self.KIND)
        return list(data) if isinstance(data, list) else []

    def save_entries(self, entries: List[Dict[str, Any]]) -> None:
        self.store.write(self.FILE, self.KIND, entries)


class FilePortraitStore(IPortraitStore):
    """Буфер портретів: кожна картинка зберігається у portraits/<slug>.<розширення>."""

    FOLDER = "portraits"

    def __init__(self, root: Path):
        self.root = Path(root) / self.FOLDER

    @staticmethod
    def _safe(slug: str) -> str:
        return re.sub(r"[^a-z0-9_-]+", "-", slug.lower()).strip("-") or "unknown"

    def find(self, slug: str) -> Optional[str]:
        name = self._safe(slug)
        for ext in IMAGE_EXTENSIONS:
            path = self.root / f"{name}.{ext}"
            if path.is_file() and path.stat().st_size > 0:
                return str(path)
        return None

    def put(self, slug: str, data: bytes, ext: str) -> str:
        ext = ext if ext in IMAGE_EXTENSIONS else "png"
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / f"{self._safe(slug)}.{ext}"
        tmp = target.with_name(target.name + f".{os.getpid()}.{threading.get_ident()}.tmp")
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, target)
        return str(target)

    def count(self) -> int:
        return sum(1 for p in self.root.glob("*") if p.suffix.lstrip(".") in IMAGE_EXTENSIONS) \
            if self.root.is_dir() else 0
