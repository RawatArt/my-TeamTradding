import sys

import pytest

from ai_trading_team.mt5.backend import MetaTrader5Backend


@pytest.mark.skipif(sys.platform != "win32", reason="MetaTrader5 ships Windows wheels only")
def test_pinned_metatrader5_dependency_loads_on_supported_windows_python() -> None:
    backend = MetaTrader5Backend.load()

    assert backend.package_version == "5.0.6180"
