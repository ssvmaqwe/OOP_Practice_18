from pathlib import Path
from app import build_app
from Core.catalog import CatalogParser, CharacterCatalog, CatalogEntry
from Core.interfaces import ICharacterSource, IImageSource
from Infra.catalog_store import JsonCatalogRepository, FilePortraitStore
from Infra.storage import JsonFileStore

RAW = {
    "diluc": {"name": "Diluc", "title": "The Dark Side of Dawn", "vision": "Pyro", "weapon": "Claymore",
              "nation": "Mondstadt", "affiliation": "Dawn Winery", "rarity": 5, "birthday": "0000-04-30",
              "constellation": "Noctua", "description": "The tycoon   of a winery."},
    "venti": {"name": "Venti", "vision": "Anemo", "weapon": "Bow", "nation": "Mondstadt", "rarity": "5"},
    "broken": {"title": "no name"},
}
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


class FakeSource(ICharacterSource):
    def __init__(self, data=None):
        self.data = RAW if data is None else data
        self.calls = 0

    def fetch(self, name):
        self.calls += 1
        return self.data.get(name)

    def list_names(self):
        self.calls += 1
        return list(self.data)


class FakeImages(IImageSource):
    def __init__(self):
        self.calls = 0

    def image_url(self, slug):
        return f"https://example.test/{slug}/icon"

    def fetch_image(self, slug):
        self.calls += 1
        return (PNG, "png") if slug != "venti" else None


def make_catalog(tmp_path, source=None, images=None):
    store = JsonFileStore(tmp_path)
    return CharacterCatalog(source or FakeSource(), images or FakeImages(),
                            JsonCatalogRepository(store), FilePortraitStore(tmp_path), workers=2)


def test_parser_normalizes_api_json():
    entry = CatalogParser.parse("diluc", RAW["diluc"], "url")
    assert entry.name == "Diluc" and entry.rarity == 5 and entry.stars == "★★★★★"
    assert entry.birthday == "30.04" and entry.description == "The tycoon of a winery."
    assert entry.short_info == "Піро · Дворучний меч · Mondstadt" and entry.icon_url == "url"
    assert CatalogParser.parse("venti", RAW["venti"]).rarity == 5
    assert CatalogParser.parse("broken", RAW["broken"]) is None
    assert CatalogParser.parse("x", "not json object") is None
    assert len(CatalogParser.parse("x", {"name": "X", "description": "a" * 1000}).description) == 400


def test_refresh_skips_bad_records_and_persists(tmp_path):
    catalog = make_catalog(tmp_path)
    result = catalog.refresh()
    assert result.total == 3 and result.added == 2 and result.failed == ["broken"]
    assert [e.slug for e in catalog.entries()] == ["diluc", "venti"]
    assert [e.slug for e in catalog.entries("анемо")] == ["venti"]

    offline = make_catalog(tmp_path, source=FakeSource({}))
    assert offline.load_cached() == 2
    assert offline.refresh().offline and offline.get("diluc").title == "The Dark Side of Dawn"


def test_portraits_are_cached_on_disk(tmp_path):
    images = FakeImages()
    catalog = make_catalog(tmp_path, images=images)
    catalog.refresh()
    path = catalog.portrait("diluc")
    assert path and Path(path).read_bytes() == PNG and Path(path).parent.name == "portraits"
    assert catalog.portrait("diluc") == path and images.calls == 1
    assert catalog.portrait("venti") is None
    assert catalog.download_portraits() == 1

    again = make_catalog(tmp_path, images=FakeImages())
    again.load_cached()
    assert again.get("diluc").portrait == path
    assert again.portrait("diluc") == path and again.images.calls == 0


def test_entry_roundtrip_and_profile():
    entry = CatalogParser.parse("diluc", RAW["diluc"], "https://img")
    assert CatalogEntry.from_dict({**entry.to_dict(), "unknown": 1}) == entry


def test_cli_catalog_commands(tmp_path, capsys):
    ctx = build_app(tmp_path, legacy_file=None, online=False)
    ctx.cli.exec_command("catalog")
    out = capsys.readouterr().out
    assert "КАТАЛОГ API (5)" in out and "Zhongli" in out
    ctx.cli.exec_command("catalog_show venti")
    out = capsys.readouterr().out
    assert "Анемо" in out and "catalog_add venti" in out
    ctx.cli.exec_command("catalog_add venti")
    assert "доступний для гри" in capsys.readouterr().out
    assert ctx.manager.get_character("venti").source == "api"
    reloaded = build_app(tmp_path, legacy_file=None, online=False)
    assert reloaded.manager.get_character("venti") is not None
    assert reloaded.catalog.get("venti") is not None
    reloaded.cli.exec_command("catalog_show nobody")
    assert "немає" in capsys.readouterr().out


def test_image_type_detection():
    from Infra.api import sniff_image
    assert sniff_image(PNG) == "png"
    assert sniff_image(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp"
    assert sniff_image(b"\xff\xd8\xff\xe0") == "jpg"
    assert sniff_image(b"<html>", "text/html") is None
