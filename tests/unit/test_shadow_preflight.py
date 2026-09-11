from datetime import timedelta

import pytest
from tests.fakes.risk import EVALUATED_AT, account_context, risk_snapshot

from ai_trading_team.orchestration.preflight import ShadowPreflightError, validate_shadow_inputs


def test_compatible_snapshot_and_account_context_pass_preflight() -> None:
    snapshot = risk_snapshot()
    validate_shadow_inputs(snapshot, account_context(snapshot), EVALUATED_AT)


@pytest.mark.parametrize("field", ["cycle_id", "snapshot_id", "account_ref"])
def test_identity_mismatch_aborts_preflight(field: str) -> None:
    snapshot = risk_snapshot()
    replacements = {
        "cycle_id": "different-cycle",
        "snapshot_id": "different-snapshot",
        "account_ref": "acct-v1:" + "0" * 64,
    }
    context = account_context(snapshot).model_copy(update={field: replacements[field]})

    with pytest.raises(ShadowPreflightError):
        validate_shadow_inputs(snapshot, context, EVALUATED_AT)


def test_future_dated_context_aborts_preflight() -> None:
    snapshot = risk_snapshot()
    context = account_context(
        snapshot, context_as_of=EVALUATED_AT + timedelta(seconds=1)
    )
    with pytest.raises(ShadowPreflightError, match="later than preflight"):
        validate_shadow_inputs(snapshot, context, EVALUATED_AT)
