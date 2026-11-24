import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PyQt6.QtWidgets")


def test_window_with_catalog_cards(tmp_path):
    from app import build_app
    from GUI.viewmodel import GameViewModel, AnswerQueue
    from GUI.catalog_viewmodel import CatalogViewModel
    from GUI.window import GameWindow

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    answers = AnswerQueue()
    ctx = build_app(tmp_path, reader=answers, legacy_file=None, online=False)
    vm = GameViewModel(ctx, answers)
    window = GameWindow(vm, CatalogViewModel(ctx.catalog, vm))
    window.resize(1200, 800)
    window.show()
    tab = window.catalog_tab
    tab.pool.waitForDone(10000)
    for _ in range(20):
        app.processEvents()
    assert window.tabs.count() == 2
    assert len(tab.cards) == 5
    card = tab.cards["diluc"]
    assert not card.portrait.pixmap().isNull()
    tab.add_to_game("diluc")
    app.processEvents()
    assert any(h.hero_id == "diluc" for h in vm.heroes())
    tab.search.setText("гео")
    app.processEvents()
    assert list(tab.cards) == ["zhongli"]
    window.close()
