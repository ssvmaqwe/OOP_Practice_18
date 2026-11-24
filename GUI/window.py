from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QPlainTextEdit, QLineEdit, QPushButton, QListWidget, QListWidgetItem, QComboBox, QLabel,
    QInputDialog, QMessageBox, QDialog, QDialogButtonBox, QSpinBox, QAbstractItemView, QTabWidget,
)
from GUI.viewmodel import GameViewModel, OUTPUT, STATE
from GUI.catalog_viewmodel import CatalogViewModel
from version import __version__, APP_TITLE, AUTHOR

ROLE_ID = Qt.ItemDataRole.UserRole


class CreateCharacterDialog(QDialog):
    def __init__(self, classes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Новий персонаж")
        form = QFormLayout(self)
        self.char_id = QLineEdit()
        self.name = QLineEdit()
        self.char_class = QComboBox()
        self.char_class.addItems(classes)
        self.health = self._spin(1, 999, 100)
        self.damage = self._spin(0, 200, 15)
        self.magic = self._spin(0, 200, 5)
        self.armor = self._spin(0, 100, 5)
        self.resist = self._spin(0, 90, 10)
        self.speed = self._spin(1, 400, 100)
        form.addRow("ID:", self.char_id)
        form.addRow("Ім'я:", self.name)
        form.addRow("Клас:", self.char_class)
        form.addRow("Здоров'я:", self.health)
        form.addRow("Шкода:", self.damage)
        form.addRow("Магія:", self.magic)
        form.addRow("Броня:", self.armor)
        form.addRow("Резист, %:", self.resist)
        form.addRow("Швидкість:", self.speed)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    @staticmethod
    def _spin(low, high, value):
        box = QSpinBox()
        box.setRange(low, high)
        box.setValue(value)
        return box

    def values(self):
        return dict(char_id=self.char_id.text().strip(), name=self.name.text().strip(),
                    char_class=self.char_class.currentText(), health=self.health.value(),
                    damage=self.damage.value(), magic=self.magic.value(), armor=self.armor.value(),
                    resist_percent=self.resist.value(), speed=self.speed.value())


class GameWindow(QMainWindow):
    def __init__(self, vm: GameViewModel, catalog_vm: Optional[CatalogViewModel] = None):
        super().__init__()
        self.vm = vm
        self.catalog_tab = None
        self.setWindowTitle(f"{APP_TITLE} {__version__} — {AUTHOR}")
        self.resize(1200, 760)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_console())
        splitter.addWidget(self._build_side_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.tabs = QTabWidget()
        self.tabs.addTab(splitter, "Гра")
        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage(f"Дані гри: {vm.data_dir}")
        if catalog_vm is not None:
            from GUI.catalog_view import CatalogTab
            self.catalog_tab = CatalogTab(catalog_vm)
            self.tabs.addTab(self.catalog_tab, "Каталог персонажів")

        vm.subscribe(OUTPUT, self.append_output)
        vm.subscribe(STATE, self.refresh)
        self.refresh()
        vm.startup()

    def _build_console(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(10)
        self.console.setFont(font)
        layout.addWidget(self.console)

        row = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("Команда консолі, напр. play_status або enemies")
        self.command_input.returnPressed.connect(lambda: self.on_command())
        run = QPushButton("Виконати")
        run.clicked.connect(lambda: self.on_command())
        clear = QPushButton("Очистити")
        clear.clicked.connect(lambda: self.console.clear())
        row.addWidget(self.command_input)
        row.addWidget(run)
        row.addWidget(clear)
        layout.addLayout(row)
        return box

    def _build_side_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(self.status_label)

        start_box = QGroupBox("Новий бій")
        start_layout = QVBoxLayout(start_box)
        start_layout.addWidget(QLabel("Герої:"))
        self.hero_list = QListWidget()
        start_layout.addWidget(self.hero_list)
        start_layout.addWidget(QLabel("Вороги:"))
        self.enemy_list = QListWidget()
        start_layout.addWidget(self.enemy_list)
        start_buttons = QHBoxLayout()
        start = QPushButton("Почати бій")
        start.clicked.connect(lambda: self.on_start())
        create = QPushButton("Створити героя…")
        create.clicked.connect(lambda: self.on_create())
        imp = QPushButton("Імпорт з API…")
        imp.clicked.connect(lambda: self.on_import())
        for b in (start, create, imp):
            start_buttons.addWidget(b)
        start_layout.addLayout(start_buttons)
        layout.addWidget(start_box)

        turn_box = QGroupBox("Хід героя")
        turn_layout = QFormLayout(turn_box)
        self.action_combo = QComboBox()
        self.action_combo.currentIndexChanged.connect(lambda _: self.refresh_targets())
        self.target_combo = QComboBox()
        self.act_button = QPushButton("Виконати дію")
        self.act_button.clicked.connect(lambda: self.on_act())
        info_row = QHBoxLayout()
        status = QPushButton("Статус")
        status.clicked.connect(lambda: self.vm.show_status())
        history = QPushButton("Історія")
        history.clicked.connect(lambda: self.vm.show_history())
        info_row.addWidget(status)
        info_row.addWidget(history)
        turn_layout.addRow("Дія:", self.action_combo)
        turn_layout.addRow("Ціль:", self.target_combo)
        turn_layout.addRow(self.act_button)
        turn_layout.addRow(info_row)
        layout.addWidget(turn_box)

        save_box = QGroupBox("Збереження")
        save_layout = QVBoxLayout(save_box)
        self.save_list = QListWidget()
        self.save_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.save_list.itemDoubleClicked.connect(lambda _: self.on_load())
        save_layout.addWidget(self.save_list)
        row1 = QHBoxLayout()
        load = QPushButton("Завантажити")
        load.clicked.connect(lambda: self.on_load())
        cont = QPushButton("Продовжити останнє")
        cont.clicked.connect(lambda: self.vm.continue_game())
        row1.addWidget(load)
        row1.addWidget(cont)
        row2 = QHBoxLayout()
        save = QPushButton("Зберегти як…")
        save.clicked.connect(lambda: self.on_save())
        delete = QPushButton("Видалити")
        delete.clicked.connect(lambda: self.on_delete())
        row2.addWidget(save)
        row2.addWidget(delete)
        save_layout.addLayout(row1)
        save_layout.addLayout(row2)
        layout.addWidget(save_box)
        return panel

    def append_output(self, text: str) -> None:
        self.console.moveCursor(QTextCursor.MoveOperation.End)
        self.console.insertPlainText(text if text.endswith("\n") else text + "\n")
        self.console.moveCursor(QTextCursor.MoveOperation.End)

    @staticmethod
    def _checked_ids(widget: QListWidget):
        return [widget.item(i).data(ROLE_ID) for i in range(widget.count())
                if widget.item(i).checkState() == Qt.CheckState.Checked]

    @staticmethod
    def _fill_checklist(widget: QListWidget, options, id_attr: str, default_checked):
        checked = {widget.item(i).data(ROLE_ID) for i in range(widget.count())
                   if widget.item(i).checkState() == Qt.CheckState.Checked}
        if not widget.count():
            checked = set(default_checked)
        widget.clear()
        for option in options:
            item = QListWidgetItem(option.label)
            value = getattr(option, id_attr)
            item.setData(ROLE_ID, value)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if value in checked else Qt.CheckState.Unchecked)
            widget.addItem(item)

    def refresh(self) -> None:
        self.status_label.setText(self.vm.status_line())
        heroes = self.vm.heroes()
        self._fill_checklist(self.hero_list, heroes, "hero_id", [h.hero_id for h in heroes[:1]])
        self._fill_checklist(self.enemy_list, self.vm.enemy_templates(), "template_id", ["goblin", "slime"])

        current_action = self.action_combo.currentData()
        self.action_combo.blockSignals(True)
        self.action_combo.clear()
        for option in self.vm.actions():
            self.action_combo.addItem(option.label, option.action_id)
            index = self.action_combo.count() - 1
            if not option.ready:
                self.action_combo.model().item(index).setEnabled(False)
        position = self.action_combo.findData(current_action)
        self.action_combo.setCurrentIndex(position if position >= 0 else 0)
        self.action_combo.blockSignals(False)
        self.act_button.setEnabled(self.vm.is_active and self.action_combo.count() > 0)
        self.refresh_targets()

        selected = self.save_list.currentItem().data(ROLE_ID) if self.save_list.currentItem() else None
        self.save_list.clear()
        for row in self.vm.saves():
            item = QListWidgetItem(row.label)
            item.setData(ROLE_ID, row.slot)
            self.save_list.addItem(item)
            if row.slot == selected:
                self.save_list.setCurrentItem(item)

    def refresh_targets(self) -> None:
        self.target_combo.clear()
        action_id = self.action_combo.currentData()
        if action_id:
            for target in self.vm.targets_for(action_id):
                self.target_combo.addItem(target.label, target.uid)

    def on_command(self) -> None:
        command = self.command_input.text().strip()
        if command in ("create",):
            self.on_create()
        elif command:
            self.vm.execute(command)
        self.command_input.clear()

    def on_start(self) -> None:
        self.vm.start(self._checked_ids(self.hero_list), self._checked_ids(self.enemy_list))

    def on_act(self) -> None:
        action_id = self.action_combo.currentData()
        if action_id:
            self.vm.act(action_id, self.target_combo.currentData())

    def _selected_slot(self):
        item = self.save_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Збереження", "Спочатку оберіть збереження у списку.")
            return None
        return item.data(ROLE_ID)

    def on_load(self) -> None:
        slot = self._selected_slot()
        if slot:
            self.vm.load(slot)

    def on_save(self) -> None:
        slot, ok = QInputDialog.getText(self, "Зберегти гру", "Назва слоту (латиниця, цифри, _ або -):",
                                        text="slot1")
        if ok and slot.strip():
            self.vm.save(slot.strip())

    def on_delete(self) -> None:
        slot = self._selected_slot()
        if slot and QMessageBox.question(self, "Видалення", f"Видалити збереження «{slot}»?") == \
                QMessageBox.StandardButton.Yes:
            self.vm.delete_save(slot)

    def on_create(self) -> None:
        dialog = CreateCharacterDialog(self.vm.character_classes(), self)
        if dialog.exec():
            self.vm.create_character(**dialog.values())

    def on_import(self) -> None:
        name, ok = QInputDialog.getText(self, "Імпорт персонажа", "Ім'я з genshin.jmp.blue (напр. diluc):")
        if ok and name.strip():
            self.vm.import_character(name.strip())

    def closeEvent(self, event) -> None:
        if self.catalog_tab is not None:
            self.catalog_tab.shutdown()
        self.vm.shutdown()
        super().closeEvent(event)
