"""Provider-free full M8 replay and evaluation acceptance."""

from ai_trading_team.evaluation import OutcomeEvaluator, summarize_performance
from ai_trading_team.replay.serialization import canonical_replay_bytes, content_digest
from ai_trading_team.storage.replay import InMemoryReplayRepository
from tests.fakes.replay import PARTITION_ID, frozen_decision, replay_build


def _run_pipeline() -> tuple[tuple[object, ...], bytes, str]:
    dataset, source, configuration, result = replay_build()
    frozen = frozen_decision(result)
    view = source.outcome_view(
        frozen,
        PARTITION_ID,
        configuration.outcome_timeframe,
        configuration.outcome_horizon,
    )
    outcome = OutcomeEvaluator().evaluate(result.frame, frozen, view, configuration)
    summary = summarize_performance((outcome,))
    repository = InMemoryReplayRepository()
    repository.append_configuration(result.frame.replay_id, PARTITION_ID, configuration)
    repository.append_frame(result.frame)
    repository.append_decision(PARTITION_ID, frozen)
    repository.append_outcome(outcome)
    repository.append_summary(summary)
    artifacts = (dataset.dataset_digest, result, frozen, outcome, summary)
    return artifacts, canonical_replay_bytes(artifacts), content_digest(artifacts)


def test_full_pipeline_repeats_with_equal_models_digests_and_bytes() -> None:
    first, first_bytes, first_digest = _run_pipeline()
    second, second_bytes, second_digest = _run_pipeline()
    assert first == second
    assert first_digest == second_digest
    assert first_bytes == second_bytes
