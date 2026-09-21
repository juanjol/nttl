import subprocess
import sys

import pytest

PACKAGES = [
    "nttl",
    "nttl.capture",
    "nttl.config",
    "nttl.darks",
    "nttl.hal",
    "nttl.imaging",
    "nttl.scheduler",
    "nttl.video",
]


@pytest.mark.parametrize("name", PACKAGES)
def test_package_imports_standalone(name):
    result = subprocess.run(
        [sys.executable, "-c", f"import {name}"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
