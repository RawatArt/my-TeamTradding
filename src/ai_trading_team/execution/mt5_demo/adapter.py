"""Narrow protected-market-order adapter for an already accepted MT5 DEMO session."""

from collections.abc import Callable
from datetime import datetime, timedelta
from threading import RLock

from ai_trading_team.execution.errors import DemoExecutionError
from ai_trading_team.execution.identifiers import environment_fingerprint
from ai_trading_team.execution.mt5_demo.backend import MT5DemoBackend
from ai_trading_team.execution.mt5_demo.mappers import (
    map_execution_capabilities,
    map_order_check,
    map_submission_receipt,
)
from ai_trading_team.execution.vendor_boundary import build_vendor_boundary_audit
from ai_trading_team.mt5.mappers import (
    map_account_info,
    map_position,
    map_symbol_info,
    map_terminal_health,
    map_tick,
    records,
)
from ai_trading_team.risk.account import account_fingerprint
from ai_trading_team.schemas.enums import (
    BrokerAccountMode,
    BrokerPositionSide,
    DemoExecutionFailureCategory,
    DemoFillingMode,
    DemoOrderExecutionMode,
    TradeSide,
)
from ai_trading_team.schemas.execution import (
    CompositeBrokerEvidence,
    DemoOrderCheckResult,
    DemoOrderIntent,
    DemoSubmissionReceipt,
    DemoSymbolExecutionCapabilities,
    FinalDispatchObservation,
)
from ai_trading_team.schemas.execution_acceptance import VendorBoundaryAudit
from ai_trading_team.utils.time import utc_now


class MT5DemoExecutionAdapter:
    """Expose one protected DEMO submission and read-only reconciliation only."""

    adapter_version = "1.0.0"

    def __init__(
        self,
        backend: MT5DemoBackend,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._backend = backend
        self._clock = clock
        self._last_guard_observation: dict[str, FinalDispatchObservation] = {}
        self._vendor_audits: dict[str, VendorBoundaryAudit] = {}
        self._lock = RLock()

    def get_execution_capabilities(self, symbol: str) -> DemoSymbolExecutionCapabilities:
        with self._lock:
            raw = self._required(self._backend.symbol_info(symbol), "symbol metadata")
            observed_at = self._clock()
            info = map_symbol_info(raw, observed_at)
            return map_execution_capabilities(raw, info, self._backend, observed_at)

    def order_check(self, intent: DemoOrderIntent) -> DemoOrderCheckResult:
        """Perform a non-submitting broker check; success has no lifecycle meaning."""
        with self._lock:
            raw = self._required(
                self._backend.order_check_request(self._request(intent)),
                "order check result",
            )
            return map_order_check(raw, intent, self._clock())

    def observe_final_dispatch(self, intent: DemoOrderIntent) -> FinalDispatchObservation:
        """Capture the mutable terminal state immediately before the service dispatch claim."""
        with self._lock:
            terminal_raw = self._required(self._backend.terminal_info(), "terminal information")
            account_raw = self._required(self._backend.account_info(), "account information")
            symbol_raw = self._required(
                self._backend.symbol_info(intent.symbol),
                "symbol information",
            )
            tick_raw = self._required(
                self._backend.symbol_info_tick(intent.symbol),
                "current tick",
            )
            position_raw = self._required(self._backend.positions_get(None), "open positions")
            observed_at = self._clock()
            account = map_account_info(account_raw, observed_at)
            health = map_terminal_health(
                terminal_raw,
                account_raw,
                self._backend.version(),
                self._backend.package_version,
                observed_at,
            )
            symbol_info = map_symbol_info(symbol_raw, observed_at)
            capabilities = map_execution_capabilities(
                symbol_raw,
                symbol_info,
                self._backend,
                observed_at,
            )
            observation = FinalDispatchObservation(
                observed_at=observed_at,
                account_ref=account_fingerprint(account.account_id, account.server),
                environment_ref=environment_fingerprint(account, health),
                health=health,
                account=account,
                symbol_info=symbol_info,
                capabilities=capabilities,
                tick=map_tick(tick_raw, intent.symbol, observed_at),
                positions=tuple(
                    map_position(item, observed_at)
                    for item in records(position_raw, "final_dispatch_positions")
                ),
            )
            self._last_guard_observation[intent.execution_intent_id] = observation
            return observation

    def submit_demo_market_intent(self, intent: DemoOrderIntent) -> DemoSubmissionReceipt:
        """Make exactly one vendor mutation call for the sealed protected intent."""
        with self._lock:
            observation = self._last_guard_observation.get(intent.execution_intent_id)
            if observation is None:
                raise self._error("final dispatch observation is missing")
            if (
                observation.account.trade_mode is not BrokerAccountMode.DEMO
                or observation.account_ref != intent.account_ref
                or observation.environment_ref != intent.environment_ref
            ):
                raise self._error("accepted DEMO environment changed before dispatch")
            dispatch_started_at = self._clock()
            if dispatch_started_at >= intent.expires_at:
                raise self._error("sealed DEMO intent expired before broker dispatch")
            audit = build_vendor_boundary_audit(
                intent,
                observation.symbol_info,
                audited_at=dispatch_started_at,
            )
            self._vendor_audits[intent.execution_intent_id] = audit
            raw = self._backend.submit_protected_market_request(self._request(intent))
            dispatch_completed_at = self._clock()
            return map_submission_receipt(
                raw,
                intent,
                self._backend,
                dispatch_started_at=dispatch_started_at,
                dispatch_completed_at=dispatch_completed_at,
                account_ref=observation.account_ref,
                environment_ref=observation.environment_ref,
            )

    def get_vendor_boundary_audit(
        self, execution_intent_id: str
    ) -> VendorBoundaryAudit | None:
        with self._lock:
            return self._vendor_audits.get(execution_intent_id)

    def find_broker_evidence(
        self,
        intent: DemoOrderIntent,
        receipt: DemoSubmissionReceipt,
    ) -> tuple[CompositeBrokerEvidence, ...]:
        """Join result identifiers to the resulting position using composite facts."""
        with self._lock:
            observation = self.observe_final_dispatch(intent)
            receipt_evidence = receipt.evidence
            if receipt_evidence is None:
                return ()
            expected_side = (
                BrokerPositionSide.BUY if intent.side is TradeSide.BUY else BrokerPositionSide.SELL
            )
            matches = tuple(
                position
                for position in observation.positions
                if position.symbol == intent.symbol
                and position.side is expected_side
                and position.volume == intent.volume
                # MT5 position timestamps may have whole-second precision. Keep the
                # correlation window narrow without requiring broker comment identity.
                and position.open_time
                >= receipt.dispatch_started_at - timedelta(seconds=2)
            )
            return tuple(
                CompositeBrokerEvidence(
                    account_ref=observation.account_ref,
                    environment_ref=observation.environment_ref,
                    symbol=position.symbol,
                    side=intent.side,
                    volume=position.volume,
                    dispatch_started_at=receipt.dispatch_started_at,
                    dispatch_completed_at=receipt.dispatch_completed_at,
                    observed_at=observation.observed_at,
                    client_trade_reference=(
                        intent.client_trade_id
                        if intent.client_trade_id[-16:] in position.comment
                        else None
                    ),
                    broker_order_id=receipt_evidence.broker_order_id,
                    broker_deal_id=receipt_evidence.broker_deal_id,
                    resulting_position_id=position.ticket,
                    fill_price=position.price_open,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                    magic=position.magic,
                    comment=position.comment,
                )
                for position in matches
            )

    def shutdown(self) -> None:
        with self._lock:
            self._backend.shutdown()
            self._last_guard_observation.clear()
            self._vendor_audits.clear()

    def _request(self, intent: DemoOrderIntent) -> dict[str, object]:
        request: dict[str, object] = {
            "action": self._backend.constant("TRADE_ACTION_DEAL"),
            "symbol": intent.symbol,
            "volume": float(intent.volume),
            "type": self._backend.constant(
                "ORDER_TYPE_BUY" if intent.side is TradeSide.BUY else "ORDER_TYPE_SELL"
            ),
            "sl": float(intent.stop_loss),
            "tp": float(intent.take_profit),
            "deviation": intent.maximum_deviation_points,
            "magic": intent.magic,
            "comment": intent.comment,
            "type_time": self._backend.constant("ORDER_TIME_GTC"),
            "type_filling": self._backend.constant(_filling_constant(intent.filling_mode)),
        }
        if intent.execution_mode is not DemoOrderExecutionMode.MARKET:
            request["price"] = float(intent.reference_price)
        return request

    @staticmethod
    def _required(value: object | None, name: str) -> object:
        if value is None:
            raise DemoExecutionError(
                DemoExecutionFailureCategory.ADAPTER_FAILURE,
                f"{name} is unavailable",
            )
        return value

    @staticmethod
    def _error(message: str) -> DemoExecutionError:
        return DemoExecutionError(
            DemoExecutionFailureCategory.ADAPTER_FAILURE,
            message,
        )


def _filling_constant(mode: DemoFillingMode) -> str:
    return {
        DemoFillingMode.FOK: "ORDER_FILLING_FOK",
        DemoFillingMode.IOC: "ORDER_FILLING_IOC",
        DemoFillingMode.RETURN: "ORDER_FILLING_RETURN",
    }[mode]
