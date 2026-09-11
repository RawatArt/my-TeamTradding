"""Deterministic composition of immutable M7 market features."""

from decimal import Context, Decimal, localcontext

from pydantic import ValidationError

from ai_trading_team.config.settings import FeatureEngineSettings
from ai_trading_team.features.definitions import (
    ADX_PERIOD,
    ATR_PERIOD,
    CANONICALIZATION_VERSION,
    DECIMAL_PRECISION,
    DECIMAL_ROUNDING,
    DEFINITION_VERSIONS,
    EMA_PERIODS,
    FEATURE_ENGINE_VERSION,
    FEATURE_SET_VERSION,
    INDEX_QUANTUM,
    RSI_PERIOD,
    adx_required_candles,
    atr_required_candles,
    confirmed_swing_required_candles,
    ema_required_candles,
    geometry_required_candles,
    recent_range_required_candles,
    rsi_required_candles,
)
from ai_trading_team.features.errors import FeatureEngineError
from ai_trading_team.features.geometry import candle_geometry
from ai_trading_team.features.indicators import adx_series, atr_series, ema_series, rsi_series
from ai_trading_team.features.serialization import configuration_digest, source_candle_digest
from ai_trading_team.features.structure import (
    latest_confirmed_swing_high,
    latest_confirmed_swing_low,
    recent_range,
)
from ai_trading_team.features.validation import revalidate_snapshot, validate_candles
from ai_trading_team.schemas.enums import (
    DataValidityState,
    FeatureAvailability,
    FeatureErrorCategory,
    FeatureUnit,
    FeatureWarningCode,
    FreshnessState,
    Timeframe,
)
from ai_trading_team.schemas.features import (
    CandleGeometryFeatures,
    DecimalFeatureValue,
    FeatureProvenance,
    FeatureWarning,
    MarketFeatureSet,
    MarketStructureFeatures,
    MomentumFeatures,
    SourceCandleDigests,
    SwingFeatureValue,
    SwingPoint,
    TimeframeFeatureCollection,
    TimeframeFeatureSet,
    TrendFeatures,
    TrendStrengthFeatures,
    VolatilityFeatures,
)
from ai_trading_team.schemas.market import MarketSnapshot
from ai_trading_team.schemas.mt5 import MT5Candle
from ai_trading_team.schemas.timeframes import timeframe_duration


class MarketFeatureEngine:
    """Produce factual features from completed candles without strategy semantics."""

    def __init__(self, settings: FeatureEngineSettings | None = None) -> None:
        candidate = settings or FeatureEngineSettings()
        try:
            self._settings = FeatureEngineSettings.model_validate(
                candidate.model_dump(mode="python")
            )
        except (AttributeError, ValidationError) as exc:
            raise FeatureEngineError(
                FeatureErrorCategory.CONFIGURATION_INCOMPATIBLE,
                "feature configuration failed structural validation",
            ) from exc

    def calculate(self, snapshot: MarketSnapshot) -> MarketFeatureSet:
        """Calculate one reproducible feature set or fail on structural invalidity."""
        try:
            original_collections = self._collections(snapshot)
            for timeframe, candles in original_collections:
                validate_candles(snapshot, timeframe, candles)
            validated = revalidate_snapshot(snapshot)
            timeframes = tuple(
                self._calculate_timeframe(validated, timeframe, candles)
                for timeframe, candles in self._collections(validated)
            )
            collection = TimeframeFeatureCollection(
                m15=timeframes[0],
                h1=timeframes[1],
                h4=timeframes[2],
            )
            digests = SourceCandleDigests(
                m15=collection.m15.source_candle_digest,
                h1=collection.h1.source_candle_digest,
                h4=collection.h4.source_candle_digest,
            )
            warnings = tuple(
                warning
                for item in timeframes
                for warning in item.warnings
            )
            if validated.consistency.freshness.overall is FreshnessState.STALE:
                warnings += (
                    FeatureWarning(
                        code=FeatureWarningCode.STALE_SOURCE,
                        message="source snapshot is valid but contains stale observations",
                    ),
                )
            provenance = FeatureProvenance(
                canonicalization_version=CANONICALIZATION_VERSION,
                source_snapshot_schema_version=validated.schema_version,
                source_snapshot_completed_at=validated.snapshot_completed_at,
                feature_engine_version=FEATURE_ENGINE_VERSION,
                feature_set_version=FEATURE_SET_VERSION,
                configuration_version=self._settings.configuration_version,
                configuration_digest=configuration_digest(self._settings),
                source_candle_digests=digests,
                definition_versions=DEFINITION_VERSIONS,
                decimal_precision=DECIMAL_PRECISION,
            )
            return MarketFeatureSet(
                feature_set_version=FEATURE_SET_VERSION,
                feature_engine_version=FEATURE_ENGINE_VERSION,
                cycle_id=validated.cycle_id,
                snapshot_id=validated.snapshot_id,
                symbol=validated.symbol,
                primary_timeframe=validated.primary_timeframe,
                generated_at=validated.snapshot_completed_at,
                source_validity=DataValidityState.VALID,
                source_freshness=validated.consistency.freshness,
                timeframes=collection,
                warnings=warnings,
                provenance=provenance,
            )
        except FeatureEngineError:
            raise
        except Exception as exc:
            raise FeatureEngineError(
                FeatureErrorCategory.CALCULATION_FAILURE,
                "deterministic feature calculation failed",
            ) from exc

    @staticmethod
    def _collections(
        snapshot: MarketSnapshot,
    ) -> tuple[tuple[Timeframe, tuple[MT5Candle, ...]], ...]:
        try:
            return (
                (Timeframe.M15, snapshot.candles.m15),
                (Timeframe.H1, snapshot.candles.h1),
                (Timeframe.H4, snapshot.candles.h4),
            )
        except AttributeError as exc:
            raise FeatureEngineError(
                FeatureErrorCategory.INVALID_SNAPSHOT,
                "feature input does not expose the accepted snapshot candle contract",
            ) from exc

    def _calculate_timeframe(
        self,
        snapshot: MarketSnapshot,
        timeframe: Timeframe,
        candles: tuple[MT5Candle, ...],
    ) -> TimeframeFeatureSet:
        count = len(candles)
        digits = snapshot.symbol_info.digits
        closes = tuple(item.close for item in candles)
        latest_close = closes[-1]

        ema_features: list[DecimalFeatureValue] = []
        for period in EMA_PERIODS:
            required = ema_required_candles(period)
            series = ema_series(closes, period)
            ema_features.append(
                self._series_feature(
                    series[-1],
                    FeatureUnit.PRICE,
                    required,
                    count,
                    digits,
                )
            )
        ema_20, ema_50, ema_200 = ema_features
        trend = TrendFeatures(
            ema_20=ema_20,
            ema_50=ema_50,
            ema_200=ema_200,
            distance_from_ema_20=self._distance(latest_close, ema_20, digits),
            distance_from_ema_50=self._distance(latest_close, ema_50, digits),
            distance_from_ema_200=self._distance(latest_close, ema_200, digits),
        )
        momentum = MomentumFeatures(
            rsi_14=self._series_feature(
                rsi_series(closes, RSI_PERIOD)[-1],
                FeatureUnit.INDEX,
                rsi_required_candles(),
                count,
                digits,
            )
        )
        volatility = VolatilityFeatures(
            atr_14=self._series_feature(
                atr_series(candles, ATR_PERIOD)[-1],
                FeatureUnit.PRICE,
                atr_required_candles(),
                count,
                digits,
            )
        )
        trend_strength = TrendStrengthFeatures(
            adx_14=self._series_feature(
                adx_series(candles, ADX_PERIOD)[-1],
                FeatureUnit.INDEX,
                adx_required_candles(),
                count,
                digits,
            )
        )

        raw_geometry = candle_geometry(candles[-1])
        geometry_required = geometry_required_candles()
        geometry = CandleGeometryFeatures(
            candle_open_at=candles[-1].open_time,
            candle_range=self._valid(
                raw_geometry.candle_range, FeatureUnit.PRICE, geometry_required, count, digits
            ),
            real_body=self._valid(
                raw_geometry.real_body, FeatureUnit.PRICE, geometry_required, count, digits
            ),
            upper_wick=self._valid(
                raw_geometry.upper_wick, FeatureUnit.PRICE, geometry_required, count, digits
            ),
            lower_wick=self._valid(
                raw_geometry.lower_wick, FeatureUnit.PRICE, geometry_required, count, digits
            ),
            body_range_ratio=(
                self._unavailable(
                    FeatureUnit.RATIO,
                    geometry_required,
                    count,
                    "zero-range candle has no defined body/range ratio",
                )
                if raw_geometry.body_range_ratio is None
                else self._valid(
                    raw_geometry.body_range_ratio,
                    FeatureUnit.RATIO,
                    geometry_required,
                    count,
                    digits,
                )
            ),
        )

        structure = self._structure(timeframe, candles, latest_close, digits)
        all_features = (
            ema_20,
            ema_50,
            ema_200,
            trend.distance_from_ema_20,
            trend.distance_from_ema_50,
            trend.distance_from_ema_200,
            momentum.rsi_14,
            volatility.atr_14,
            trend_strength.adx_14,
            geometry.candle_range,
            geometry.real_body,
            geometry.upper_wick,
            geometry.lower_wick,
            geometry.body_range_ratio,
            structure.recent_range_high,
            structure.recent_range_low,
            structure.distance_from_recent_swing_high,
            structure.distance_from_recent_swing_low,
            structure.distance_from_recent_range_high,
            structure.distance_from_recent_range_low,
        )
        statuses = tuple(item.status for item in all_features) + (
            structure.recent_swing_high.status,
            structure.recent_swing_low.status,
        )
        availability = self._summary(statuses)
        warnings = self._warnings(timeframe, all_features, structure)
        return TimeframeFeatureSet(
            timeframe=timeframe,
            source_candle_count=count,
            source_first_candle_open_at=candles[0].open_time,
            source_last_candle_open_at=candles[-1].open_time,
            source_last_candle_close_at=(
                candles[-1].open_time + timeframe_duration(timeframe)
            ),
            evaluation_candle_open_at=candles[-1].open_time,
            source_candle_digest=source_candle_digest(snapshot.symbol, timeframe, candles),
            availability=availability,
            trend=trend,
            momentum=momentum,
            volatility=volatility,
            trend_strength=trend_strength,
            candle_geometry=geometry,
            market_structure=structure,
            warnings=warnings,
        )

    def _structure(
        self,
        timeframe: Timeframe,
        candles: tuple[MT5Candle, ...],
        latest_close: Decimal,
        digits: int,
    ) -> MarketStructureFeatures:
        count = len(candles)
        swing_required = confirmed_swing_required_candles(
            self._settings.swing_left_bars,
            self._settings.swing_right_bars,
        )
        swing_high = self._swing(
            latest_confirmed_swing_high(
                candles,
                timeframe,
                self._settings.swing_left_bars,
                self._settings.swing_right_bars,
            ),
            swing_required,
            count,
            digits,
        )
        swing_low = self._swing(
            latest_confirmed_swing_low(
                candles,
                timeframe,
                self._settings.swing_left_bars,
                self._settings.swing_right_bars,
            ),
            swing_required,
            count,
            digits,
        )
        range_required = recent_range_required_candles(
            self._settings.recent_range_lookback
        )
        raw_range = recent_range(candles, self._settings.recent_range_lookback)
        if raw_range is None:
            range_high = self._insufficient(FeatureUnit.PRICE, range_required, count)
            range_low = self._insufficient(FeatureUnit.PRICE, range_required, count)
        else:
            range_high = self._valid(
                raw_range[0], FeatureUnit.PRICE, range_required, count, digits
            )
            range_low = self._valid(
                raw_range[1], FeatureUnit.PRICE, range_required, count, digits
            )
        return MarketStructureFeatures(
            recent_swing_high=swing_high,
            recent_swing_low=swing_low,
            recent_range_high=range_high,
            recent_range_low=range_low,
            distance_from_recent_swing_high=self._swing_distance(
                latest_close, swing_high, digits
            ),
            distance_from_recent_swing_low=self._swing_distance(
                latest_close, swing_low, digits
            ),
            distance_from_recent_range_high=self._distance(
                latest_close, range_high, digits
            ),
            distance_from_recent_range_low=self._distance(latest_close, range_low, digits),
        )

    @staticmethod
    def _series_feature(
        value: Decimal | None,
        unit: FeatureUnit,
        required: int,
        available: int,
        digits: int,
    ) -> DecimalFeatureValue:
        if available < required:
            return MarketFeatureEngine._insufficient(unit, required, available)
        if value is None:
            raise FeatureEngineError(
                FeatureErrorCategory.CALCULATION_FAILURE,
                "indicator did not produce a value after its required history",
            )
        return MarketFeatureEngine._valid(value, unit, required, available, digits)

    @staticmethod
    def _valid(
        value: Decimal,
        unit: FeatureUnit,
        required: int,
        available: int,
        digits: int,
    ) -> DecimalFeatureValue:
        return DecimalFeatureValue(
            status=FeatureAvailability.VALID,
            unit=unit,
            value=_quantize(value, unit, digits),
            required_candles=required,
            available_candles=available,
        )

    @staticmethod
    def _insufficient(
        unit: FeatureUnit,
        required: int,
        available: int,
    ) -> DecimalFeatureValue:
        return DecimalFeatureValue(
            status=FeatureAvailability.INSUFFICIENT_HISTORY,
            unit=unit,
            required_candles=required,
            available_candles=available,
            reason="accepted completed-candle history is insufficient",
        )

    @staticmethod
    def _unavailable(
        unit: FeatureUnit,
        required: int,
        available: int,
        reason: str,
    ) -> DecimalFeatureValue:
        return DecimalFeatureValue(
            status=FeatureAvailability.UNAVAILABLE,
            unit=unit,
            required_candles=required,
            available_candles=available,
            reason=reason,
        )

    @staticmethod
    def _distance(
        latest_close: Decimal,
        reference: DecimalFeatureValue,
        digits: int,
    ) -> DecimalFeatureValue:
        if reference.status is FeatureAvailability.VALID:
            if reference.value is None:
                raise FeatureEngineError(
                    FeatureErrorCategory.CALCULATION_FAILURE,
                    "valid reference feature has no value",
                )
            with localcontext(Context(prec=DECIMAL_PRECISION, rounding=DECIMAL_ROUNDING)):
                difference = latest_close - reference.value
            return MarketFeatureEngine._valid(
                difference,
                FeatureUnit.PRICE,
                reference.required_candles,
                reference.available_candles,
                digits,
            )
        return DecimalFeatureValue(
            status=reference.status,
            unit=FeatureUnit.PRICE,
            required_candles=reference.required_candles,
            available_candles=reference.available_candles,
            reason=reference.reason,
        )

    @staticmethod
    def _swing(
        value: SwingPoint | None,
        required: int,
        available: int,
        digits: int,
    ) -> SwingFeatureValue:
        if available < required:
            return SwingFeatureValue(
                status=FeatureAvailability.INSUFFICIENT_HISTORY,
                required_candles=required,
                available_candles=available,
                reason="accepted completed-candle history is insufficient",
            )
        if value is None:
            return SwingFeatureValue(
                status=FeatureAvailability.UNAVAILABLE,
                required_candles=required,
                available_candles=available,
                reason="no strictly confirmed swing exists in the accepted history",
            )
        return SwingFeatureValue(
            status=FeatureAvailability.VALID,
            value=value.model_copy(
                update={"price": _quantize(value.price, FeatureUnit.PRICE, digits)}
            ),
            required_candles=required,
            available_candles=available,
        )

    @staticmethod
    def _swing_distance(
        latest_close: Decimal,
        reference: SwingFeatureValue,
        digits: int,
    ) -> DecimalFeatureValue:
        if reference.status is FeatureAvailability.VALID:
            if reference.value is None:
                raise FeatureEngineError(
                    FeatureErrorCategory.CALCULATION_FAILURE,
                    "valid swing reference has no point",
                )
            with localcontext(Context(prec=DECIMAL_PRECISION, rounding=DECIMAL_ROUNDING)):
                difference = latest_close - reference.value.price
            return MarketFeatureEngine._valid(
                difference,
                FeatureUnit.PRICE,
                reference.required_candles,
                reference.available_candles,
                digits,
            )
        return DecimalFeatureValue(
            status=reference.status,
            unit=FeatureUnit.PRICE,
            required_candles=reference.required_candles,
            available_candles=reference.available_candles,
            reason=reference.reason,
        )

    @staticmethod
    def _summary(statuses: tuple[FeatureAvailability, ...]) -> FeatureAvailability:
        if FeatureAvailability.INSUFFICIENT_HISTORY in statuses:
            return FeatureAvailability.INSUFFICIENT_HISTORY
        if FeatureAvailability.UNAVAILABLE in statuses:
            return FeatureAvailability.UNAVAILABLE
        return FeatureAvailability.VALID

    @staticmethod
    def _warnings(
        timeframe: Timeframe,
        numeric: tuple[DecimalFeatureValue, ...],
        structure: MarketStructureFeatures,
    ) -> tuple[FeatureWarning, ...]:
        statuses = tuple(item.status for item in numeric) + (
            structure.recent_swing_high.status,
            structure.recent_swing_low.status,
        )
        warnings: list[FeatureWarning] = []
        if FeatureAvailability.INSUFFICIENT_HISTORY in statuses:
            warnings.append(
                FeatureWarning(
                    code=FeatureWarningCode.INSUFFICIENT_HISTORY,
                    message="one or more features require additional completed candles",
                    timeframe=timeframe,
                )
            )
        if FeatureAvailability.UNAVAILABLE in statuses:
            warnings.append(
                FeatureWarning(
                    code=FeatureWarningCode.FEATURE_UNAVAILABLE,
                    message="one or more features are undefined for the accepted history",
                    timeframe=timeframe,
                )
            )
        return tuple(warnings)


def _quantize(value: Decimal, unit: FeatureUnit, digits: int) -> Decimal:
    quantum = Decimal(1).scaleb(-digits) if unit is FeatureUnit.PRICE else INDEX_QUANTUM
    with localcontext(Context(prec=DECIMAL_PRECISION, rounding=DECIMAL_ROUNDING)):
        return value.quantize(quantum)
