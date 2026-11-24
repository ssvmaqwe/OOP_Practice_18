import subprocess
import sys
import zipfile
from pathlib import Path
import pytest
from app import parse_launch_options, build_app
from version import __version__

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import make_pyz  # noqa: E402


def test_launch_options():
    opts = parse_launch_options(["--debug", "--data-dir=~/x", "list", "--version"])
    assert opts.debug and opts.show_version
    assert opts.data_dir.name == "x" and opts.rest == ["list"]


def test_version_is_semver():
    parts = __version__.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts)


def broken_command(ctx):
    from CLI.presenter import BaseCommandStrategy, Command

    class Broken(BaseCommandStrategy):
        def __init__(self):
            super().__init__()
            self.register_command(Command("boom", "", self._boom))

        def _boom(self, args):
            raise RuntimeError("тестова помилка")

    ctx.cli.use_strategy(Broken())


def test_release_mode_hides_internal_errors(tmp_path, capsys):
    ctx = build_app(tmp_path, legacy_file=None, online=False, debug=False)
    broken_command(ctx)
    assert ctx.cli.exec_command("boom") is False
    assert "Внутрішня помилка" in capsys.readouterr().out


def test_debug_mode_raises(tmp_path):
    ctx = build_app(tmp_path, legacy_file=None, online=False, debug=True)
    broken_command(ctx)
    with pytest.raises(RuntimeError):
        ctx.cli.exec_command("boom")


def test_pyz_builds_and_runs(tmp_path):
    pyz = make_pyz.build(tmp_path / "textgame.pyz")
    names = zipfile.ZipFile(pyz).namelist()
    assert "__main__.py" in names and "Core/game.py" in names
    assert not any("__pycache__" in n for n in names)
    run = subprocess.run([sys.executable, str(pyz), "--version"], capture_output=True)
    assert run.returncode == 0
    assert __version__ in run.stdout.decode("utf-8")
    run = subprocess.run([sys.executable, str(pyz), f"--data-dir={tmp_path / 'data'}", "enemies"],
                         capture_output=True)
    assert "goblin" in run.stdout.decode("utf-8")
    assert (tmp_path / "data" / "textgame.log").exists()
