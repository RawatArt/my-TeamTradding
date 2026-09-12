"""Read-only completed-candle discovery without scheduling or terminal mutation."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from ai_trading_team.config.settings import ContinuousShadowSettings
from ai_trading_team.observation.errors import ObservationRuntimeError
from ai_trading_team.observation.identifiers import (
    cycle_id_for_decision,
    decision_candle_content_digest,
    decision_key,
)
from ai_trading_team.observation.protocols import CompletedCandleSource
from ai_trading_team.schemas.common import Symbol
from ai_trading_team.schemas.enums import ObservationFailureCategory, Timeframe
from ai_trading_team.schemas.observation import CompletedDecisionCandle
from ai_trading_team.schemas.timeframes import timeframe_duration
from ai_trading_team.utils.time import utc_now


class CompletedCandleDiscovery:
    """Discover a bounded window of completed M15 candles from an accepted read source."""

    def __init__(
        self,
        source: CompletedCandleSource,
        settings: ContinuousShadowSettings,
        symbol: Symbol,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._source = source
        self._settings = settings
        self._symbol = symbol
        self._clock = clock

    def poll(self) -> tuple[CompletedDecisionCandle, ...]:
        observed_at = self._now()
        try:
            candles = self._source.get_candles(
                self._symbol,
                Timeframe.M15,
                self._settings.discovery_lookback,
                include_incomplete=False,
            )
        except Exception as exc:
            raise ObservationRuntimeError(
                ObservationFailureCategory.MT5_UNAVAILABLE,
                "completed-candle discovery source is unavailable",
            ) from exc
        if not candles:
            return ()
        if tuple(sorted(candles, key=lambda item: item.open_time)) != candles:
            raise self._invalid("completed candles must be strictly ordered")
        if len({item.open_time for item in candles}) != len(candles):
            raise self._invalid("completed candle timestamps must be unique")

        result: list[CompletedDecisionCandle] = []
        duration = timeframe_duration(Timeframe.M15)
        for candle in candles:
            close_at = candle.open_time + duration
            if candle.symbol != self._symbol or candle.timeframe is not Timeframe.M15:
                raise self._invalid("completed candle does not match runtime symbol/timeframe")
            if candle.open_time.tzinfo is None or candle.open_time.utcoffset() is None:
                raise self._invalid("completed candle time must be timezone-aware")
            if close_at > observed_at:
                raise self._invalid("incomplete candle entered completed-candle discovery")
            key = decision_key(self._symbol, Timeframe.M15, candle.open_time, close_at)
            result.append(
                CompletedDecisionCandle(
                    decision_key=key,
                    cycle_id=cycle_id_for_decision(key),
                    symbol=self._symbol,
                    candle_open_at=candle.open_time,
                    candle_close_at=close_at,
                    candle_digest=decision_candle_content_digest(candle),
                    observed_at=observed_at,
                )
            )
        return tuple(result)

    def is_timely(self, candle: CompletedDecisionCandle) -> bool:
        return candle.observed_at - candle.candle_close_at <= timedelta(
            seconds=self._settings.maximum_decision_age_seconds
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise self._invalid("discovery clock must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _invalid(message: str) -> ObservationRuntimeError:
        return ObservationRuntimeError(ObservationFailureCategory.INVALID_COMPLETED_CANDLE, message)
