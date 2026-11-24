import shutil
import sys
import tempfile
import zipapp
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ["Core", "CLI", "Infra", "GUI"]
MODULES = ["main.py", "gui.py", "app.py", "version.py"]


def build(output: Path, entry: str = "main:main") -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "app"
        stage.mkdir()
        for package in PACKAGES:
            shutil.copytree(ROOT / package, stage / package,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for module in MODULES:
            shutil.copy2(ROOT / module, stage / module)
        zipapp.create_archive(stage, output, interpreter="/usr/bin/env python3", main=entry, compressed=True)
    return output


if __name__ == "__main__":
    dist = ROOT / "dist"
    print(build(dist / "textgame.pyz", "main:main"))
    print(build(dist / "textgame-gui.pyz", "gui:main"))
    sys.exit(0)
