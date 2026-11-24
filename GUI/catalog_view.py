from typing import Dict, Set
from PyQt6.QtCore import Qt, QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea, QLineEdit,
    QPushButton, QMessageBox, QProgressBar, QSizePolicy,
)
from GUI.catalog_viewmodel import CatalogViewModel, CardData, CARDS, PORTRAIT, PROGRESS

PORTRAIT_SIZE = 128
CARD_WIDTH = 210
ELEMENT_COLORS = {"Піро": "#e2583e", "Гідро": "#3d8fd6", "Електро": "#9b5de5", "Кріо": "#7fc8d8",
                  "Анемо": "#3cb98b", "Гео": "#d1a43b", "Дендро": "#7fb53d"}


class _Bridge(QObject):
    """Передає події з фонових потоків у головний потік Qt (queued connection)."""
    cards_changed = pyqtSignal()
    portrait_ready = pyqtSignal(str, str)
    progress = pyqtSignal(int, int)
    refreshed = pyqtSignal(str)


class _Task(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self) -> None:
        try:
            self.fn()
        except Exception:  # фонова задача не повинна валити застосунок
            import logging
            logging.getLogger("textgame.gui").exception("Помилка фонової задачі")


def placeholder(card: CardData) -> QPixmap:
    element = card.info.split(" · ")[0] if card.info else ""
    pixmap = QPixmap(PORTRAIT_SIZE, PORTRAIT_SIZE)
    pixmap.fill(QColor(ELEMENT_COLORS.get(element, "#8a8f98")))
    painter = QPainter(pixmap)
    painter.setPen(QColor("white"))
    font = QFont()
    font.setPointSize(30)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, card.initials)
    painter.end()
    return pixmap


class CharacterCard(QFrame):
    """Композитний елемент списку: портрет, ім'я, рідкість, коротка інформація, кнопки."""

    def __init__(self, card: CardData, view: 'CatalogTab'):
        super().__init__()
        self.card = card
        self.view = view
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedWidth(CARD_WIDTH)
        self.setObjectName("card")
        self.setStyleSheet("#card { background: palette(base); border: 1px solid palette(mid); border-radius: 8px; }")
        self.setToolTip(card.description or card.name)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        self.portrait = QLabel()
        self.portrait.setFixedSize(PORTRAIT_SIZE, PORTRAIT_SIZE)
        self.portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.portrait, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.set_portrait(card.portrait)

        name = QLabel(card.name)
        name.setStyleSheet("font-weight: bold; font-size: 14px;")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name)
        if card.title:
            title = QLabel(card.title)
            title.setStyleSheet("font-style: italic; color: gray;")
            title.setWordWrap(True)
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(title)
        stars = QLabel(card.stars)
        stars.setStyleSheet("color: #d4a017; font-size: 14px;")
        stars.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(stars)
        info = QLabel(card.info or "—")
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info)

        buttons = QHBoxLayout()
        more = QPushButton("Детальніше")
        more.clicked.connect(lambda: self.view.show_details(self.card))
        add = QPushButton("У грі ✓" if card.in_game else "У гру")
        add.setEnabled(not card.in_game)
        add.clicked.connect(lambda: self.view.add_to_game(self.card.slug))
        buttons.addWidget(more)
        buttons.addWidget(add)
        layout.addLayout(buttons)

    def set_portrait(self, path: str) -> None:
        pixmap = QPixmap(path) if path else QPixmap()
        if pixmap.isNull():
            pixmap = placeholder(self.card)
        self.portrait.setPixmap(pixmap.scaled(PORTRAIT_SIZE, PORTRAIT_SIZE, Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation))


class CatalogTab(QWidget):
    def __init__(self, vm: CatalogViewModel):
        super().__init__()
        self.vm = vm
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(4)
        self.cards: Dict[str, CharacterCard] = {}
        self.requested: Set[str] = set()
        self.busy = False
        self._columns = 0

        self.bridge = _Bridge()
        self.bridge.cards_changed.connect(self.rebuild)
        self.bridge.portrait_ready.connect(self.on_portrait)
        self.bridge.progress.connect(self.on_progress)
        self.bridge.refreshed.connect(self.on_refreshed)
        vm.subscribe(CARDS, self.bridge.cards_changed.emit)
        vm.subscribe(PORTRAIT, self.bridge.portrait_ready.emit)
        vm.subscribe(PROGRESS, self.bridge.progress.emit)

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Пошук: ім'я, стихія, зброя, регіон…")
        self.search.textChanged.connect(self.vm.set_query)
        self.refresh_button = QPushButton("Оновити з сервера")
        self.refresh_button.clicked.connect(lambda: self.start_refresh())
        top.addWidget(self.search)
        top.addWidget(self.refresh_button)
        layout.addLayout(top)

        status = QHBoxLayout()
        self.summary = QLabel()
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.hide()
        status.addWidget(self.summary)
        status.addStretch(1)
        status.addWidget(self.progress)
        layout.addLayout(status)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.grid.setSpacing(10)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        self.rebuild()
        if self.vm.needs_refresh:
            self.start_refresh()

    def columns(self) -> int:
        width = self.scroll.viewport().width() or self.width()
        return max(1, width // (CARD_WIDTH + 12))

    def rebuild(self) -> None:
        while self.grid.count():
            widget = self.grid.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        self.cards.clear()
        columns = self._columns = self.columns()
        data = self.vm.cards()
        for index, card in enumerate(data):
            widget = CharacterCard(card, self)
            widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.cards[card.slug] = widget
            self.grid.addWidget(widget, index // columns, index % columns)
            if not card.portrait:
                self.request_portrait(card.slug)
        if not data:
            empty = QLabel("Каталог порожній. Натисніть «Оновити з сервера»." if not self.vm.query
                           else "Нічого не знайдено.")
            self.grid.addWidget(empty, 0, 0)
        self.summary.setText(self.vm.summary())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.columns() != self._columns:
            self.rebuild()

    def request_portrait(self, slug: str) -> None:
        if slug in self.requested:
            return
        self.requested.add(slug)
        self.pool.start(_Task(lambda: self.vm.load_portrait(slug)))

    def start_refresh(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.requested.clear()
        self.refresh_button.setEnabled(False)
        self.progress.setValue(0)
        self.progress.show()
        self.summary.setText("Завантаження каталогу з сервера…")
        self.pool.start(_Task(lambda: self.bridge.refreshed.emit(self.vm.describe(self.vm.refresh()))))

    def on_progress(self, done: int, total: int) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(done)

    def on_refreshed(self, message: str) -> None:
        self.busy = False
        self.refresh_button.setEnabled(True)
        self.progress.hide()
        self.rebuild()
        self.window().statusBar().showMessage(message, 8000)

    def on_portrait(self, slug: str, path: str) -> None:
        card = self.cards.get(slug)
        if card:
            card.set_portrait(path)
        self.summary.setText(self.vm.summary())

    def show_details(self, card: CardData) -> None:
        text = f"<h3>{card.name}</h3><p style='color:#d4a017'>{card.stars}</p><p>{card.info}</p>"
        if card.details:
            text += "<p>" + card.details.replace("\n", "<br>") + "</p>"
        if card.description:
            text += f"<p><i>{card.description}</i></p>"
        if card.icon_url:
            text += f"<p>Графіка: <a href='{card.icon_url}'>{card.icon_url}</a></p>"
        if card.portrait:
            text += f"<p>Локальний файл: {card.portrait}</p>"
        box = QMessageBox(self)
        box.setWindowTitle(card.name)
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(text)
        path = self.cards[card.slug].portrait.pixmap() if card.slug in self.cards else None
        if path is not None and not path.isNull():
            box.setIconPixmap(path)
        box.exec()

    def add_to_game(self, slug: str) -> None:
        self.vm.add_to_game(slug)
        self.window().statusBar().showMessage("Персонажа додано у список героїв на вкладці «Гра».", 6000)

    def shutdown(self) -> None:
        self.pool.clear()
        self.pool.waitForDone(3000)
