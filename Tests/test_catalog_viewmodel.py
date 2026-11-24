from app import build_app
from GUI.viewmodel import GameViewModel, AnswerQueue
from GUI.catalog_viewmodel import CatalogViewModel, CARDS, PROGRESS


def make(tmp_path):
    answers = AnswerQueue()
    ctx = build_app(tmp_path, reader=answers, legacy_file=None, online=False)
    game_vm = GameViewModel(ctx, answers)
    return CatalogViewModel(ctx.catalog, game_vm), game_vm


def test_cards_after_refresh(tmp_path):
    vm, _ = make(tmp_path)
    events, progress = [], []
    vm.subscribe(CARDS, lambda: events.append(1))
    vm.subscribe(PROGRESS, lambda d, t: progress.append((d, t)))
    assert vm.needs_refresh
    result = vm.refresh()
    assert "5 персонажів" in vm.describe(result)
    assert progress[-1] == (5, 5) and events
    cards = vm.cards()
    assert [c.name for c in cards][:2] == ["Barbara", "Diluc"]
    diluc = next(c for c in cards if c.slug == "diluc")
    assert diluc.stars == "★★★★★" and diluc.initials == "D" and not diluc.in_game
    assert "з 5" in vm.summary()


def test_filter_and_add_to_game(tmp_path):
    vm, game_vm = make(tmp_path)
    vm.refresh()
    vm.set_query("лук")
    assert {c.slug for c in vm.cards()} == {"venti", "fischl"}
    text = vm.add_to_game("fischl")
    assert "доступний для гри" in text
    assert next(c for c in vm.cards() if c.slug == "fischl").in_game
    assert "fischl" in [h.hero_id for h in game_vm.heroes()]
    assert vm.load_portrait("fischl") is None
