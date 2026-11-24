import os
import sys
from app import parse_launch_options
from version import __version__, APP_TITLE


def main(argv=None):
    options = parse_launch_options(sys.argv[1:] if argv is None else argv)
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if options.show_version:
        print(f"{APP_TITLE} {__version__}")
        return 0

    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        print("Для графічного інтерфейсу потрібна бібліотека PyQt6.")
        print("Встановіть її командою:  pip install -r requirements.txt")
        return 1

    from app import build_app, setup_logging
    from GUI.viewmodel import GameViewModel, AnswerQueue
    from GUI.window import GameWindow
    from GUI.catalog_viewmodel import CatalogViewModel
    from Infra.storage import AppDataLocator

    data_dir = options.data_dir or AppDataLocator.resolve()
    setup_logging(data_dir, options.debug)
    qt_app = QApplication(sys.argv[:1])
    answers = AnswerQueue()
    ctx = build_app(data_dir, reader=answers, debug=options.debug)
    vm = GameViewModel(ctx, answers)
    window = GameWindow(vm, CatalogViewModel(ctx.catalog, vm))
    if options.debug:
        window.setWindowTitle(window.windowTitle() + " [DEBUG]")
    window.show()
    return qt_app.exec()


if __name__ == "__main__":
    sys.exit(main())
