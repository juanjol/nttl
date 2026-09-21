from typer.testing import CliRunner

from nttl import __version__
from nttl.cli import app

runner = CliRunner(env={"COLUMNS": "200", "TERM": "dumb", "NO_COLOR": "1"})


def test_version_flag_reports_package_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_lists_no_unexpected_failure():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
