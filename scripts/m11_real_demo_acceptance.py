"""Explicit two-phase M11 real-DEMO operator command.

The readiness-only mode cannot claim or dispatch. The execute-once mode is separately gated and
must never be used without a reviewed post-readiness approval.
"""

from __future__ import annotations

import argparse
import json
import os
import tomllib
from importlib import import_module
from pathlib import Path
from typing import Any

from ai_trading_team.config import AppSettings
from ai_trading_team.config.startup import validate_m11_startup
from ai_trading_team.execution.mt5_demo import MetaTrader5DemoBackend, MT5DemoExecutionAdapter
from ai_trading_team.execution.observation import M11ExecutionObservationSource
from ai_trading_team.execution.real_demo_acceptance import RealDemoAcceptanceCoordinator
from ai_trading_team.execution.service import DemoExecutionService
from ai_trading_team.market import MarketDataService
from ai_trading_team.mt5 import MT5ReadOnlyClient
from ai_trading_team.mt5.backend import MetaTrader5Backend
from ai_trading_team.observation.risk_context import AccountRiskContextProvider
from ai_trading_team.risk import RiskEngine
from ai_trading_team.schemas.enums import ApplicationMode
from ai_trading_team.schemas.execution import (
    DemoExecutionEnvironmentAcceptance,
    DemoExecutionPolicy,
    QualifiedDemoExecutionCandidate,
)
from ai_trading_team.schemas.execution_acceptance import (
    RealDemoMutationApproval,
    RealDemoReadinessRecord,
)
from ai_trading_team.storage.execution import SQLiteDemoExecutionRepository
from ai_trading_team.storage.execution_acceptance import SQLiteRealDemoAcceptanceRepository
from ai_trading_team.storage.observation import SQLiteObservationRepository


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    phase = parser.add_mutually_exclusive_group(required=True)
    phase.add_argument("--readiness-only", action="store_true")
    phase.add_argument("--execute-once", action="store_true")
    args = parser.parse_args()

    config_path = args.config.resolve(strict=True)
    config = _load_toml(config_path)
    settings = AppSettings()
    validate_m11_startup(settings)
    if args.execute_once:
        _require_explicit_mutation_gate(settings)
    operator = _mapping(config, "operator")
    paths = _mapping(config, "paths")
    candidate = _load_model(
        _path(config_path, paths, "candidate"), QualifiedDemoExecutionCandidate
    )
    acceptance = _load_model(
        _path(config_path, paths, "environment_acceptance"),
        DemoExecutionEnvironmentAcceptance,
    )
    policy = _load_model(_path(config_path, paths, "execution_policy"), DemoExecutionPolicy)

    module = import_module("MetaTrader5")
    read_backend = MetaTrader5Backend(module)
    demo_backend = MetaTrader5DemoBackend(module)
    mt5 = MT5ReadOnlyClient(settings.mt5, backend=read_backend)
    execution_repository = SQLiteDemoExecutionRepository(
        _path(config_path, paths, "execution_repository")
    )
    observation_repository = SQLiteObservationRepository(
        _path(config_path, paths, "observation_repository")
    )
    acceptance_repository = SQLiteRealDemoAcceptanceRepository(
        _path(config_path, paths, "acceptance_repository")
    )
    try:
        mt5.initialize()
        adapter = MT5DemoExecutionAdapter(demo_backend)
        market_data = MarketDataService(
            mt5,
            settings.market_data,
            settings.trading_symbol,
        )
        account_context = AccountRiskContextProvider(mt5, observation_repository)
        source = M11ExecutionObservationSource(market_data, account_context, mt5, adapter)
        service = DemoExecutionService(
            source=source,
            adapter=adapter,
            repository=execution_repository,
            risk_engine=RiskEngine(settings.risk),
            risk_engine_version=candidate.dependency_manifest.risk_engine_version,
            risk_policy_digest=candidate.dependency_manifest.risk_policy_digest,
        )
        coordinator = RealDemoAcceptanceCoordinator(
            source=source,
            adapter=adapter,
            execution_repository=execution_repository,
            acceptance_repository=acceptance_repository,
            execution_service=service,
        )
        if args.readiness_only:
            readiness = coordinator.readiness_only(
                candidate,
                acceptance,
                policy,
                acceptance_run_id=str(operator["acceptance_run_id"]),
                readiness_generation_id=str(operator["readiness_generation_id"]),
                ttl_seconds=int(operator.get("readiness_ttl_seconds", 300)),
            )
            output = _path(config_path, paths, "readiness_output")
            _exclusive_write(output, readiness.model_dump_json(indent=2))
            print(
                json.dumps(
                    {
                        "phase": "READINESS_ONLY",
                        "acceptance_run_id": readiness.acceptance_run_id,
                        "readiness_generation_id": readiness.readiness_generation_id,
                        "readiness_digest": readiness.readiness_digest,
                        "readiness_expires_at": readiness.readiness_expires_at.isoformat(),
                        "claim_count": 0,
                        "order_check_count": 0,
                        "submission_count": 0,
                    },
                    sort_keys=True,
                )
            )
            return 0

        readiness = _load_model(
            _path(config_path, paths, "readiness_input"), RealDemoReadinessRecord
        )
        approval = _load_model(
            _path(config_path, paths, "mutation_approval"), RealDemoMutationApproval
        )
        result = coordinator.execute_once(
            candidate,
            acceptance,
            policy,
            readiness,
            approval,
            claim_owner=str(operator["claim_owner"]),
        )
        _exclusive_write(
            _path(config_path, paths, "acceptance_output"),
            result.model_dump_json(indent=2),
        )
        print(result.model_dump_json(include={"acceptance_run_id", "status", "record_digest"}))
        return 0
    finally:
        mt5.shutdown()
        acceptance_repository.close()
        observation_repository.close()
        execution_repository.close()


def _require_explicit_mutation_gate(settings: AppSettings) -> None:
    if (
        settings.app_mode is not ApplicationMode.DEMO
        or not settings.demo_execution.enabled
    ):
        raise RuntimeError("execute-once requires explicit DEMO mode and enablement")
    if os.getenv("RUN_M11_REAL_DEMO_EXECUTION", "false").casefold() != "true":
        raise RuntimeError("execute-once requires RUN_M11_REAL_DEMO_EXECUTION=true")


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _mapping(value: dict[str, Any], key: str) -> dict[str, Any]:
    result = value.get(key)
    if not isinstance(result, dict):
        raise ValueError(f"configuration section {key!r} is required")
    return result


def _path(config_path: Path, values: dict[str, Any], key: str) -> Path:
    raw = values.get(key)
    if not isinstance(raw, str) or not raw:
        raise ValueError(f"configuration path {key!r} is required")
    path = Path(raw)
    return path if path.is_absolute() else (config_path.parent / path).resolve()


def _load_model(path: Path, model_type: type[Any]) -> Any:
    return model_type.model_validate_json(path.read_text(encoding="utf-8"))


def _exclusive_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
        handle.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
