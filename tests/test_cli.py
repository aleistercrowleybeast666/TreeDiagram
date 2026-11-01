"""Explicit controller timing at the product CLI persistence boundary."""
import pytest

from treediagram.cli import Cli_Main
from treediagram.design import Design_Decode
from treediagram.io import Json_Read


@pytest.mark.parametrize("controller", ["pid", "lqr"])
def test_cli_research_period_is_explicit(tmp_path, controller):
    target = tmp_path / "design.json"
    assert Cli_Main(["example", str(target), "--controller", controller]) == 0
    assert Design_Decode(Json_Read(target)).control.period_us == 20000
    assert Cli_Main(["example", str(target), "--controller", controller,
                     "--control-period-us", "10000"]) == 0
    design = Design_Decode(Json_Read(target))
    assert design.control.controller == controller
    assert design.control.period_us == 10000


@pytest.mark.parametrize("period", ["0", "-10000", "1000001"])
def test_cli_invalid_period_preserves_existing_file(tmp_path, period):
    target = tmp_path / "design.json"
    assert Cli_Main(["example", str(target)]) == 0
    original = target.read_bytes()
    assert Cli_Main(["example", str(target), "--controller", "pid",
                     "--control-period-us", period]) == 2
    assert target.read_bytes() == original
