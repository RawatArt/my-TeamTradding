"""Canonical mapping between each M4 role and its input/body/output schemas."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from pydantic import TypeAdapter

from ai_trading_team.schemas.agents import (
    ChiefTraderOutput,
    ChiefTraderResult,
    EntryAnalysisOutput,
    EntryAnalysisResult,
    MarketContextOutput,
    MarketContextResult,
    PerformanceReviewOutput,
    PerformanceReviewResult,
    PriceActionOutput,
    PriceActionResult,
    QuantDeveloperOutput,
    QuantDeveloperReview,
    QuantResearchOutput,
    QuantResearchResult,
    SkepticOutput,
    SkepticReview,
    TrendAnalysisOutput,
    TrendAnalysisResult,
)
from ai_trading_team.schemas.common import CoreModel
from ai_trading_team.schemas.enums import AgentRole
from ai_trading_team.schemas.orchestration import (
    ChiefTraderInput,
    EntryAnalysisInput,
    MarketContextInput,
    PerformanceReviewInput,
    PriceActionInput,
    QuantDeveloperInput,
    QuantResearchInput,
    SkepticInput,
    TrendAnalysisInput,
)
from ai_trading_team.schemas.runtime import ModelGeneratedAgentBody, SchemaReference


@dataclass(frozen=True, slots=True)
class RoleContract:
    """Runtime schema types for one agent role."""

    input_type: type[CoreModel]
    payload_type: type[CoreModel]
    output_type: type[CoreModel]
    body_adapter: TypeAdapter[Any]


def _contract(
    input_type: type[CoreModel],
    payload_type: type[CoreModel],
    output_type: type[CoreModel],
) -> RoleContract:
    return RoleContract(
        input_type=input_type,
        payload_type=payload_type,
        output_type=output_type,
        body_adapter=TypeAdapter(ModelGeneratedAgentBody[payload_type]),  # type: ignore[valid-type]
    )


ROLE_CONTRACTS = {
    AgentRole.MARKET_CONTEXT: _contract(
        MarketContextInput, MarketContextResult, MarketContextOutput
    ),
    AgentRole.TREND_ANALYST: _contract(
        TrendAnalysisInput, TrendAnalysisResult, TrendAnalysisOutput
    ),
    AgentRole.PRICE_ACTION_ANALYST: _contract(
        PriceActionInput, PriceActionResult, PriceActionOutput
    ),
    AgentRole.ENTRY_ANALYST: _contract(
        EntryAnalysisInput, EntryAnalysisResult, EntryAnalysisOutput
    ),
    AgentRole.QUANT_RESEARCHER: _contract(
        QuantResearchInput, QuantResearchResult, QuantResearchOutput
    ),
    AgentRole.SENIOR_QUANT_DEVELOPER: _contract(
        QuantDeveloperInput, QuantDeveloperReview, QuantDeveloperOutput
    ),
    AgentRole.SKEPTIC: _contract(SkepticInput, SkepticReview, SkepticOutput),
    AgentRole.CHIEF_TRADER: _contract(
        ChiefTraderInput, ChiefTraderResult, ChiefTraderOutput
    ),
    AgentRole.PERFORMANCE_REVIEWER: _contract(
        PerformanceReviewInput, PerformanceReviewResult, PerformanceReviewOutput
    ),
}


def contract_for_role(role: AgentRole) -> RoleContract:
    return ROLE_CONTRACTS[role]


def canonical_schema_json(schema: dict[str, Any]) -> str:
    return json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def schema_reference(subject: type[CoreModel] | TypeAdapter[Any]) -> SchemaReference:
    if isinstance(subject, TypeAdapter):
        schema = subject.json_schema(mode="validation")
        schema_id = schema.get("title", "model-generated-agent-body")
    else:
        schema = subject.model_json_schema(mode="validation")
        schema_id = subject.__name__
    encoded = canonical_schema_json(schema).encode("utf-8")
    return SchemaReference(
        schema_id=str(schema_id),
        schema_version="1.0.0",
        schema_digest=f"sha256:{hashlib.sha256(encoded).hexdigest()}",
    )
