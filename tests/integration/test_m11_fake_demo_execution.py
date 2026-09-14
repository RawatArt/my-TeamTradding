"""Provider-free and broker-free M11 core acceptance flow."""

from ai_trading_team.replay.serialization import canonical_replay_bytes, content_digest
from ai_trading_team.schemas.enums import DemoExecutionState
from ai_trading_team.schemas.execution import DemoExecutionRecord
from tests.fakes.execution import execution_bundle


def _run_once() -> tuple[DemoExecutionRecord, int]:
    service, candidate, acceptance, policy, _, adapter = execution_bundle()
    record = service.execute(candidate, acceptance, policy, claim_owner="worker-m11")
    return record, adapter.submit_calls


def test_fake_adapter_end_to_end_demo_execution_is_exactly_once_and_deterministic() -> None:
    first, first_calls = _run_once()
    second, second_calls = _run_once()

    assert first.state is DemoExecutionState.CONFIRMED
    assert first_calls == second_calls == 1
    assert first == second
    assert content_digest(first) == content_digest(second)
    assert canonical_replay_bytes(first) == canonical_replay_bytes(second)
