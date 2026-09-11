"""Content-derived M8 identifiers."""

from ai_trading_team.replay.serialization import content_digest


def deterministic_id(prefix: str, payload: object) -> str:
    """Create a stable identifier from canonical content."""
    return f"{prefix}-v1:{content_digest(payload).removeprefix('sha256:')}"


def replay_id(configuration_digest: str) -> str:
    return deterministic_id("replay", {"configuration_digest": configuration_digest})


def frame_id(replay: str, symbol: str, timeframe: str, cutoff: object) -> str:
    return deterministic_id(
        "frame",
        {"replay_id": replay, "symbol": symbol, "timeframe": timeframe, "cutoff": cutoff},
    )


def cycle_id(frame: str) -> str:
    return deterministic_id("cycle", {"frame_id": frame})


def snapshot_id(frame: str) -> str:
    return deterministic_id("snapshot", {"frame_id": frame})


def outcome_id(frame: str, proposal_digest: str, policy_digest: str) -> str:
    return deterministic_id(
        "outcome",
        {
            "frame_id": frame,
            "proposal_digest": proposal_digest,
            "policy_digest": policy_digest,
        },
    )
