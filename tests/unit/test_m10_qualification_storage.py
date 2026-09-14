"""M10 append-only SQLite persistence tests."""

from pathlib import Path

import pytest
from tests.fakes.qualification import EVALUATED_AT, qualification_bundle

from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.schemas.enums import QualificationEvidenceLifecycle
from ai_trading_team.storage.qualification import SQLiteQualificationRepository


def test_sqlite_round_trip_preserves_evaluated_artifacts(tmp_path: Path) -> None:
    path = tmp_path / "qualification.db"
    repository = SQLiteQualificationRepository(path)
    _, service, sealed, manifest, policy, run = qualification_bundle(
        repository=repository
    )
    evaluation, evaluated, _ = service.evaluate(
        run, sealed, manifest, policy, evaluated_at=EVALUATED_AT
    )
    repository.close()

    restored = SQLiteQualificationRepository(path)
    assert restored.latest_evidence(evaluated.dataset_id) == evaluated
    assert restored.get_run(run.qualification_run_id) == run
    assert restored.get_evaluation(evaluation.evaluation_id) == evaluation
    assert restored.latest_validity(run.qualification_run_id) is not None
    restored.close()


def test_sqlite_rejects_duplicate_run_and_terminal_evidence_mutation(
    tmp_path: Path,
) -> None:
    repository = SQLiteQualificationRepository(tmp_path / "qualification.db")
    _, service, sealed, manifest, policy, run = qualification_bundle(
        repository=repository
    )
    _, evaluated, _ = service.evaluate(
        run, sealed, manifest, policy, evaluated_at=EVALUATED_AT
    )

    with pytest.raises(ValueError, match="already exists"):
        repository.append_run(run)
    assert evaluated.lifecycle is QualificationEvidenceLifecycle.EVALUATED
    with pytest.raises(ValueError, match="terminal"):
        repository.append_evidence_revision(
            evaluated.model_copy(
                update={
                    "revision": evaluated.revision + 1,
                    "previous_revision_digest": content_digest(evaluated),
                }
            )
        )
    repository.close()
