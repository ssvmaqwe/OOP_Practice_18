#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "=== 1/4 Тести ==="
python3 -m pytest -q

echo "=== 2/4 Пакет Python (wheel) ==="
rm -rf build dist/*.whl dist/*.tar.gz ./*.egg-info
python3 -m pip wheel . --no-deps --no-build-isolation -w dist

echo "=== 3/4 Архіви .pyz (запуск одним файлом через Python) ==="
python3 tools/make_pyz.py

echo "=== 4/4 Виконувані файли (якщо встановлено PyInstaller) ==="
if python3 -c "import PyInstaller" 2>/dev/null; then
    python3 -m PyInstaller --noconfirm --clean --onefile --windowed --optimize 2 --paths . --name TextGame gui.py
    python3 -m PyInstaller --noconfirm --clean --onefile --console --optimize 2 --paths . \
        --exclude-module PyQt6 --name TextGameConsole main.py
else
    echo "PyInstaller не встановлено: пропускаю. Встановіть: pip install -r requirements-dev.txt"
fi

echo
echo "Готово. Результати в папці dist/:"
ls -1 dist
