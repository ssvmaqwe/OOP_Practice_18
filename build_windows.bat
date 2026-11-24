@echo off
chcp 65001 > nul
setlocal
cd /d "%~dp0"

echo === 1/4 Встановлення залежностей ===
python -m pip install --upgrade pip || goto :error
python -m pip install -r requirements-dev.txt || goto :error

echo === 2/4 Тести ===
python -m pytest -q || goto :error

echo === 3/4 Збирання exe (release) ===
python -m PyInstaller --noconfirm --clean --onefile --windowed --optimize 2 --paths . --name TextGame gui.py || goto :error
python -m PyInstaller --noconfirm --clean --onefile --console --optimize 2 --paths . --exclude-module PyQt6 --name TextGameConsole main.py || goto :error

echo === 4/4 Архів для користувача ===
copy /y README.md dist\README.md > nul
powershell -NoProfile -Command "Compress-Archive -Force -Path dist\TextGame.exe,dist\TextGameConsole.exe,dist\README.md -DestinationPath dist\TextGame-windows.zip" || goto :error

echo.
echo Готово: dist\TextGame.exe, dist\TextGameConsole.exe, dist\TextGame-windows.zip
exit /b 0

:error
echo.
echo Збирання не вдалося. Дивіться повідомлення вище.
exit /b 1
