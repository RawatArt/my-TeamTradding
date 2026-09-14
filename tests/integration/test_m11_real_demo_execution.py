"""Separately gated real-broker acceptance placeholder for M11.

Core M11 acceptance never requires or triggers a real DEMO order. A reviewed operator run must
provide the exact sealed qualification, environment, approval, and policy artifacts before this
module is extended/enabled for a specific accepted terminal.
"""

import os

import pytest


@pytest.mark.mt5_demo_execution
def test_real_demo_execution_acceptance_is_explicitly_pending() -> None:
    if os.getenv("RUN_M11_DEMO_EXECUTION", "false").casefold() != "true":
        pytest.skip("real M11 DEMO broker acceptance is not explicitly enabled")
    pytest.skip(
        "no reviewed M11 DEMO environment/approval artifact is configured; core acceptance "
        "must not place a real order merely to pass"
    )
