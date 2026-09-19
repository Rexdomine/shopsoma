"""Pure transition policy for domestic fulfillment state machines.

The policy covers quote, payment, vendor preparation, inbound transfer, hub processing,
and DHL outbound lifecycles. It describes allowed edges and the evidence required to
take them. It does not mutate aggregates or perform side effects; callers remain
responsible for persisting the returned decision with optimistic concurrency and
idempotency.
"""

import math
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Iterator, Mapping


class StateMachine(str, Enum):
    QUOTE = "quote"
    PAYMENT_ATTEMPT = "payment_attempt"
    VENDOR_PREPARATION = "vendor_preparation"
    INBOUND = "inbound"
    HUB = "hub"
    OUTBOUND = "outbound"


class TransitionKind(str, Enum):
    COMMAND = "command"
    EXTERNAL_EVENT = "external_event"
    DERIVED = "derived"
    TIMER = "timer"


class QuoteState(str, Enum):
    ACTIVE = "quote_active"
    EXPIRED = "quote_expired"
    CANCELLED = "quote_cancelled"
    CONSUMED = "quote_consumed"


class PaymentAttemptState(str, Enum):
    ATTEMPT_CREATED = "attempt_created"
    INITIALIZING = "initializing"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    ATTEMPT_EXPIRED = "attempt_expired"
    LATE_REACQUIRE = "late_reacquire"
    VOID_PENDING = "void_pending"
    REFUND_PENDING = "refund_pending"
    REFUNDED = "refunded"
    RECONCILIATION_FAILED = "reconciliation_failed"


class VendorPreparationState(str, Enum):
    NOT_STARTED = "not_started"
    VENDOR_NOTIFIED = "vendor_notified"
    PREPARING = "preparing"
    READY_FOR_INBOUND = "ready_for_inbound"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class InboundState(str, Enum):
    NOT_REQUESTED = "not_requested"
    PLANNED = "planned"
    ACCEPTED_BY_PROVIDER = "accepted_by_provider"
    HANDED_OVER = "handed_over"
    IN_TRANSIT = "in_transit"
    RECEIVED_PARTIAL = "received_partial"
    RECEIVED_COMPLETE = "received_complete"
    DELAYED = "delayed"
    LOST = "lost"
    DAMAGED = "damaged"
    CANCELLED = "cancelled"


class HubState(str, Enum):
    AWAITING_RECEIPT = "awaiting_receipt"
    RECEIVED = "received"
    QC_PENDING = "qc_pending"
    QC_IN_PROGRESS = "qc_in_progress"
    QC_PASSED = "qc_passed"
    QC_FAILED = "qc_failed"
    REMEDIATION = "remediation"
    READY_TO_PACK = "ready_to_pack"
    PACKED = "packed"
    SEALED = "sealed"
    READY_FOR_DHL = "ready_for_dhl"
    UNSEALED = "unsealed"
    REPACKED = "repacked"
    CANCELLED = "cancelled"


class OutboundState(str, Enum):
    NOT_READY = "not_ready"
    INTENT_CREATED = "intent_created"
    BOOKED = "booked"
    LABEL_READY = "label_ready"
    AWAITING_COLLECTION = "awaiting_collection"
    COLLECTED = "collected"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    EXCEPTION = "exception"
    RETURNING = "returning"
    RETURNED = "returned"
    CANCELLED = "cancelled"


class CustomerMilestone(str, Enum):
    """Customer-facing progress derived from authoritative fulfillment states."""

    PAYMENT_CONFIRMED = "payment_confirmed"
    VENDOR_PREPARING = "vendor_preparing"
    MOVING_TO_SHOPSOMA = "moving_to_shopsoma"
    RECEIVED_BY_SHOPSOMA = "received_by_shopsoma"
    QUALITY_CHECK = "quality_check"
    PACKED_READY = "packed_ready"
    DHL_COLLECTED = "dhl_collected"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    EXCEPTION = "exception"


class ActorSource(str, Enum):
    CUSTOMER = "customer"
    CHECKOUT = "checkout"
    SYSTEM_TIMER = "system_timer"
    PAYMENT_GATEWAY = "payment_gateway"
    PAYMENT_WORKER = "payment_worker"
    FINANCE = "finance"
    ORDER_SERVICE = "order_service"
    VENDOR = "vendor"
    OPERATIONS = "operations"
    SLA_POLICY = "sla_policy"
    INBOUND_PROVIDER = "inbound_provider"
    HUB_OPERATOR = "hub_operator"
    HUB_SUPERVISOR = "hub_supervisor"
    QC_ADMIN = "qc_admin"
    HUB_SERVICE = "hub_service"
    SHIPPING_POLICY = "shipping_policy"
    SHIPMENT_INTENT_SERVICE = "shipment_intent_service"
    SHIPMENT_SERVICE = "shipment_service"
    DHL_ADAPTER = "dhl_adapter"
    DHL_EVENT = "dhl_event"


TransitionState = (
    QuoteState
    | PaymentAttemptState
    | VendorPreparationState
    | InboundState
    | HubState
    | OutboundState
)

_STATE_TYPE_BY_MACHINE = MappingProxyType(
    {
        StateMachine.QUOTE: QuoteState,
        StateMachine.PAYMENT_ATTEMPT: PaymentAttemptState,
        StateMachine.VENDOR_PREPARATION: VendorPreparationState,
        StateMachine.INBOUND: InboundState,
        StateMachine.HUB: HubState,
        StateMachine.OUTBOUND: OutboundState,
    }
)


@dataclass(frozen=True, slots=True)
class TransitionRule:
    machine: StateMachine
    from_states: tuple[TransitionState, ...]
    action: str
    to_state: TransitionState
    kind: TransitionKind
    authorized_sources: frozenset[ActorSource]
    required_guards: frozenset[str]
    evidence_requirement: frozenset[str]
    idempotency_required: bool = True
    compensation: str = "none_required"
    retry: str = "safe_with_same_idempotency_key"
    creates_machine: StateMachine | None = None
    creates_state: TransitionState | None = None


def _freeze_replay_value(value: object) -> object:
    """Copy replay metadata into recursively immutable JSON-like values."""

    if isinstance(value, Mapping):
        frozen = {}
        for key, nested_value in value.items():
            if type(key) is not str:
                raise TypeError("replay metadata keys must be strings")
            frozen[key] = _freeze_replay_value(nested_value)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_replay_value(item) for item in value)
    if type(value) in (str, int, bool) or value is None:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise TypeError("replay metadata values must be finite JSON-like values")


@dataclass(frozen=True, slots=True)
class PriorTransitionResult:
    """Durably persisted result used to authenticate an idempotent replay."""

    machine: StateMachine
    current_state: TransitionState
    action: str
    aggregate_id: str
    result_version: int
    external_source: str | None
    event_id: str | None
    idempotency_key: str
    to_state: TransitionState
    replay_metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        if not _is_sanitized_identifier(self.aggregate_id):
            raise TypeError("aggregate_id must be a sanitized identifier")
        if type(self.result_version) is not int or self.result_version < 1:
            raise TypeError("result_version must be a positive integer")
        if not isinstance(self.replay_metadata, Mapping):
            raise TypeError("replay_metadata must be a mapping")
        object.__setattr__(
            self,
            "replay_metadata",
            _freeze_replay_value(self.replay_metadata),
        )


@dataclass(frozen=True, slots=True)
class TransitionContext:
    machine: StateMachine
    current_state: TransitionState
    action: str
    actor: ActorSource
    aggregate_id: str
    aggregate_version: int | None
    expected_version: int | None
    guards: frozenset[str]
    evidence: frozenset[str]
    idempotency_key: str | None
    external_source: str | None = None
    event_id: str | None = None
    duplicate: bool = False
    prior_result: PriorTransitionResult | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "guards", frozenset(self.guards))
        object.__setattr__(self, "evidence", frozenset(self.evidence))


@dataclass(frozen=True, slots=True)
class TransitionDecision:
    allowed: bool
    rule: TransitionRule
    from_state: TransitionState
    to_state: TransitionState
    side_effect_required: bool
    idempotent_replay: bool
    replay_metadata: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class CustomerCohortProgress:
    """Immutable aligned snapshot used only to derive customer-visible progress."""

    payment_state: PaymentAttemptState
    vendor_state: VendorPreparationState
    inbound_state: InboundState
    hub_state: HubState
    outbound_state: OutboundState
    cancelled: bool = False
    cancellation_refund_disposition_recorded: bool = False
    received_units: int | None = None
    total_units: int | None = None


class TransitionRejected(ValueError):
    """Raised when a requested transition is not authorized by the policy."""


_TRANSITION_KINDS: Mapping[tuple[StateMachine, str], TransitionKind] = MappingProxyType(
    {
        # Existing quote, payment and vendor preparation rules.
        (StateMachine.QUOTE, "expire"): TransitionKind.TIMER,
        (StateMachine.QUOTE, "cancel"): TransitionKind.COMMAND,
        (StateMachine.QUOTE, "consume"): TransitionKind.DERIVED,
        (StateMachine.QUOTE, "create_attempt"): TransitionKind.COMMAND,
        (StateMachine.PAYMENT_ATTEMPT, "initialize"): TransitionKind.COMMAND,
        (StateMachine.PAYMENT_ATTEMPT, "record_pending"): TransitionKind.EXTERNAL_EVENT,
        (
            StateMachine.PAYMENT_ATTEMPT,
            "record_initialization_failure",
        ): TransitionKind.EXTERNAL_EVENT,
        (StateMachine.PAYMENT_ATTEMPT, "supersede"): TransitionKind.COMMAND,
        (StateMachine.PAYMENT_ATTEMPT, "confirm"): TransitionKind.EXTERNAL_EVENT,
        (StateMachine.PAYMENT_ATTEMPT, "record_failure"): TransitionKind.EXTERNAL_EVENT,
        (StateMachine.PAYMENT_ATTEMPT, "expire_attempt"): TransitionKind.TIMER,
        (StateMachine.PAYMENT_ATTEMPT, "start_late_reacquire"): TransitionKind.DERIVED,
        (
            StateMachine.PAYMENT_ATTEMPT,
            "confirm_after_reacquire",
        ): TransitionKind.DERIVED,
        (StateMachine.PAYMENT_ATTEMPT, "request_void"): TransitionKind.COMMAND,
        (StateMachine.PAYMENT_ATTEMPT, "request_refund"): TransitionKind.COMMAND,
        (
            StateMachine.PAYMENT_ATTEMPT,
            "record_provider_refund",
        ): TransitionKind.EXTERNAL_EVENT,
        (
            StateMachine.PAYMENT_ATTEMPT,
            "mark_reconciliation_failed",
        ): TransitionKind.DERIVED,
        (StateMachine.PAYMENT_ATTEMPT, "retry_void"): TransitionKind.COMMAND,
        (StateMachine.PAYMENT_ATTEMPT, "retry_refund"): TransitionKind.COMMAND,
        (StateMachine.VENDOR_PREPARATION, "notify_vendor"): TransitionKind.DERIVED,
        (StateMachine.VENDOR_PREPARATION, "start_preparing"): TransitionKind.COMMAND,
        (
            StateMachine.VENDOR_PREPARATION,
            "mark_ready_for_inbound",
        ): TransitionKind.COMMAND,
        (StateMachine.VENDOR_PREPARATION, "block"): TransitionKind.COMMAND,
        (StateMachine.VENDOR_PREPARATION, "resume_preparing"): TransitionKind.COMMAND,
        (StateMachine.VENDOR_PREPARATION, "restore_ready"): TransitionKind.COMMAND,
        (StateMachine.VENDOR_PREPARATION, "cancel"): TransitionKind.COMMAND,
        # Inbound transfer rules.
        **{
            (StateMachine.INBOUND, action): kind
            for action, kind in {
                "plan_inbound": TransitionKind.COMMAND,
                "provider_acceptance": TransitionKind.EXTERNAL_EVENT,
                "vendor_handoff": TransitionKind.EXTERNAL_EVENT,
                "operations_attested_acceptance": TransitionKind.COMMAND,
                "operations_attested_handoff": TransitionKind.COMMAND,
                "operations_attested_delay": TransitionKind.COMMAND,
                "operations_attested_loss": TransitionKind.COMMAND,
                "movement_confirmed": TransitionKind.EXTERNAL_EVENT,
                "partial_hub_receipt": TransitionKind.COMMAND,
                "complete_hub_receipt": TransitionKind.COMMAND,
                "cancel_before_handoff": TransitionKind.COMMAND,
                "delay_reported": TransitionKind.EXTERNAL_EVENT,
                "movement_resumed": TransitionKind.EXTERNAL_EVENT,
                "loss_confirmed": TransitionKind.EXTERNAL_EVENT,
                "damage_confirmed": TransitionKind.COMMAND,
            }.items()
        },
        **{
            (StateMachine.HUB, action): kind
            for action, kind in {
                "all_required_items_received": TransitionKind.DERIVED,
                "queue_qc": TransitionKind.DERIVED,
                "start_qc": TransitionKind.COMMAND,
                "all_items_pass": TransitionKind.COMMAND,
                "any_item_fails": TransitionKind.COMMAND,
                "approve_remediation": TransitionKind.COMMAND,
                "remediation_completed": TransitionKind.COMMAND,
                "aggregate_ready_to_pack": TransitionKind.DERIVED,
                "record_package_composition": TransitionKind.COMMAND,
                "apply_seal": TransitionKind.COMMAND,
                "outbound_checks_pass": TransitionKind.DERIVED,
                "authorized_unseal": TransitionKind.COMMAND,
                "record_repack": TransitionKind.COMMAND,
                "apply_new_seal": TransitionKind.COMMAND,
                "approved_cancellation": TransitionKind.COMMAND,
            }.items()
        },
        **{
            (StateMachine.OUTBOUND, action): kind
            for action, kind in {
                "package_ready": TransitionKind.DERIVED,
                "create_shipment": TransitionKind.COMMAND,
                "label_received": TransitionKind.EXTERNAL_EVENT,
                "schedule_hub_collection": TransitionKind.COMMAND,
                "dhl_acceptance_handoff": TransitionKind.EXTERNAL_EVENT,
                "carrier_in_transit": TransitionKind.EXTERNAL_EVENT,
                "carrier_out_for_delivery": TransitionKind.EXTERNAL_EVENT,
                "carrier_delivered": TransitionKind.EXTERNAL_EVENT,
                "carrier_exception": TransitionKind.EXTERNAL_EVENT,
                "carrier_resumed": TransitionKind.EXTERNAL_EVENT,
                "carrier_return_started": TransitionKind.EXTERNAL_EVENT,
                "carrier_return_completed": TransitionKind.COMMAND,
                "cancel_unbooked_intent": TransitionKind.COMMAND,
                "provider_cancellation_confirmed": TransitionKind.EXTERNAL_EVENT,
            }.items()
        },
    }
)


def _rule(
    machine: StateMachine,
    from_states: TransitionState | tuple[TransitionState, ...],
    action: str,
    to_state: TransitionState,
    actors: ActorSource | tuple[ActorSource, ...],
    guards: tuple[str, ...],
    evidence: tuple[str, ...],
    *,
    compensation: str = "none_required",
    retry: str = "safe_with_same_idempotency_key",
    creates_machine: StateMachine | None = None,
    creates_state: TransitionState | None = None,
) -> TransitionRule:
    if not isinstance(from_states, tuple):
        from_states = (from_states,)
    if not isinstance(actors, tuple):
        actors = (actors,)
    expected_state_type = _STATE_TYPE_BY_MACHINE[machine]
    if any(type(state) is not expected_state_type for state in from_states):
        raise TypeError(f"from_states must belong to {machine.value}")
    if type(to_state) is not expected_state_type:
        raise TypeError(f"to_state must belong to {machine.value}")
    if (creates_machine is None) != (creates_state is None):
        raise TypeError("creates_machine and creates_state must be provided together")
    if (
        creates_machine is not None
        and type(creates_state) is not _STATE_TYPE_BY_MACHINE[creates_machine]
    ):
        raise TypeError("creates_state must belong to creates_machine")
    return TransitionRule(
        machine=machine,
        from_states=from_states,
        action=action,
        to_state=to_state,
        kind=_TRANSITION_KINDS[(machine, action)],
        authorized_sources=frozenset(actors),
        required_guards=frozenset(guards),
        evidence_requirement=frozenset(evidence),
        compensation=compensation,
        retry=retry,
        creates_machine=creates_machine,
        creates_state=creates_state,
    )


_POLICY = (
    # Quote lifecycle.
    _rule(
        StateMachine.QUOTE,
        QuoteState.ACTIVE,
        "expire",
        QuoteState.EXPIRED,
        ActorSource.SYSTEM_TIMER,
        (
            "quote_age_at_least_30m",
            "no_eligible_payment_attempt",
            "no_confirmed_payment_attempt",
        ),
        ("timer_observation",),
    ),
    _rule(
        StateMachine.QUOTE,
        QuoteState.ACTIVE,
        "cancel",
        QuoteState.CANCELLED,
        (ActorSource.CUSTOMER, ActorSource.OPERATIONS),
        ("no_confirmed_payment_attempt",),
        ("cancellation_record",),
    ),
    _rule(
        StateMachine.QUOTE,
        QuoteState.ACTIVE,
        "consume",
        QuoteState.CONSUMED,
        ActorSource.PAYMENT_WORKER,
        ("first_valid_payment",),
        ("payment_confirmation",),
    ),
    _rule(
        StateMachine.QUOTE,
        QuoteState.ACTIVE,
        "create_attempt",
        QuoteState.ACTIVE,
        ActorSource.CHECKOUT,
        (
            "quote_owner_session_verified",
            "valid_unexpired_quote_version",
            "before_quote_expiry_30m",
            "reservations_held",
            "no_active_payment_attempt",
        ),
        ("persisted_attempt_request",),
        compensation="attempt_failure_preserves_quote_active",
        retry="safe_with_same_idempotency_key_while_quote_active",
        creates_machine=StateMachine.PAYMENT_ATTEMPT,
        creates_state=PaymentAttemptState.ATTEMPT_CREATED,
    ),
    # Payment attempt lifecycle.
    _rule(
        StateMachine.PAYMENT_ATTEMPT,
        PaymentAttemptState.ATTEMPT_CREATED,
        "initialize",
        PaymentAttemptState.INITIALIZING,
        ActorSource.CHECKOUT,
        ("attempt_persisted_for_reconciliation", "before_quote_expiry_30m"),
        ("persisted_attempt",),
    ),
    _rule(
        StateMachine.PAYMENT_ATTEMPT,
        PaymentAttemptState.INITIALIZING,
        "record_pending",
        PaymentAttemptState.PENDING,
        ActorSource.PAYMENT_GATEWAY,
        ("authenticated_gateway_response", "unique_provider_reference"),
        ("gateway_response",),
    ),
    _rule(
        StateMachine.PAYMENT_ATTEMPT,
        PaymentAttemptState.INITIALIZING,
        "record_initialization_failure",
        PaymentAttemptState.FAILED,
        ActorSource.PAYMENT_GATEWAY,
        ("authenticated_gateway_response",),
        ("gateway_failure",),
    ),
    _rule(
        StateMachine.PAYMENT_ATTEMPT,
        PaymentAttemptState.FAILED,
        "supersede",
        PaymentAttemptState.SUPERSEDED,
        ActorSource.CHECKOUT,
        ("no_confirmed_payment_attempt", "before_quote_expiry_30m"),
        ("replacement_attempt",),
    ),
    _rule(
        StateMachine.PAYMENT_ATTEMPT,
        PaymentAttemptState.PENDING,
        "confirm",
        PaymentAttemptState.CONFIRMED,
        (ActorSource.PAYMENT_GATEWAY, ActorSource.PAYMENT_WORKER),
        (
            "authenticated_gateway_response",
            "unique_provider_reference",
            "verified_exact_payment_success",
            "within_payment_grace_45m",
            "order_and_stock_locks_held",
        ),
        ("verified_payment",),
    ),
    _rule(
        StateMachine.PAYMENT_ATTEMPT,
        PaymentAttemptState.PENDING,
        "record_failure",
        PaymentAttemptState.FAILED,
        (ActorSource.PAYMENT_GATEWAY, ActorSource.PAYMENT_WORKER),
        ("authenticated_gateway_response",),
        ("gateway_failure",),
    ),
    _rule(
        StateMachine.PAYMENT_ATTEMPT,
        PaymentAttemptState.PENDING,
        "expire_attempt",
        PaymentAttemptState.ATTEMPT_EXPIRED,
        ActorSource.SYSTEM_TIMER,
        ("payment_grace_elapsed_45m", "no_confirmed_payment_attempt"),
        ("timer_observation",),
    ),
    _rule(
        StateMachine.PAYMENT_ATTEMPT,
        PaymentAttemptState.ATTEMPT_EXPIRED,
        "start_late_reacquire",
        PaymentAttemptState.LATE_REACQUIRE,
        ActorSource.PAYMENT_WORKER,
        (
            "after_payment_grace_45m",
            "order_and_stock_locks_held",
            "late_exact_payment_proved",
        ),
        ("late_payment_proof",),
    ),
    _rule(
        StateMachine.PAYMENT_ATTEMPT,
        PaymentAttemptState.LATE_REACQUIRE,
        "confirm_after_reacquire",
        PaymentAttemptState.CONFIRMED,
        ActorSource.PAYMENT_WORKER,
        ("stock_reacquired",),
        ("stock_reacquisition",),
    ),
    _rule(
        StateMachine.PAYMENT_ATTEMPT,
        PaymentAttemptState.LATE_REACQUIRE,
        "request_void",
        PaymentAttemptState.VOID_PENDING,
        ActorSource.PAYMENT_WORKER,
        ("stock_unavailable",),
        ("stock_unavailability",),
        compensation="verify_provider_void_or_refund",
    ),
    _rule(
        StateMachine.PAYMENT_ATTEMPT,
        PaymentAttemptState.CONFIRMED,
        "request_refund",
        PaymentAttemptState.REFUND_PENDING,
        (ActorSource.OPERATIONS, ActorSource.FINANCE),
        (
            "cancellation_authorized",
            "refund_items_calculated",
            "fulfillment_stopped",
            "item_disposition_recorded",
        ),
        (
            "cancellation_approval",
            "refund_item_calculation",
            "fulfillment_stop",
            "item_disposition",
        ),
        compensation="verify_provider_refund",
    ),
    _rule(
        StateMachine.PAYMENT_ATTEMPT,
        (
            PaymentAttemptState.VOID_PENDING,
            PaymentAttemptState.REFUND_PENDING,
        ),
        "record_provider_refund",
        PaymentAttemptState.REFUNDED,
        (ActorSource.PAYMENT_GATEWAY, ActorSource.PAYMENT_WORKER),
        ("provider_result_verified",),
        ("provider_refund_or_void_result",),
    ),
    _rule(
        StateMachine.PAYMENT_ATTEMPT,
        (
            PaymentAttemptState.VOID_PENDING,
            PaymentAttemptState.REFUND_PENDING,
        ),
        "mark_reconciliation_failed",
        PaymentAttemptState.RECONCILIATION_FAILED,
        ActorSource.PAYMENT_WORKER,
        ("retries_exhausted",),
        ("reconciliation_exhaustion",),
        compensation="finance_review",
    ),
    _rule(
        StateMachine.PAYMENT_ATTEMPT,
        PaymentAttemptState.RECONCILIATION_FAILED,
        "retry_void",
        PaymentAttemptState.VOID_PENDING,
        ActorSource.FINANCE,
        ("finance_retry_authorized",),
        ("finance_retry_approval",),
    ),
    _rule(
        StateMachine.PAYMENT_ATTEMPT,
        PaymentAttemptState.RECONCILIATION_FAILED,
        "retry_refund",
        PaymentAttemptState.REFUND_PENDING,
        ActorSource.FINANCE,
        ("finance_retry_authorized",),
        ("finance_retry_approval",),
    ),
    # Vendor preparation lifecycle.
    _rule(
        StateMachine.VENDOR_PREPARATION,
        VendorPreparationState.NOT_STARTED,
        "notify_vendor",
        VendorPreparationState.VENDOR_NOTIFIED,
        ActorSource.ORDER_SERVICE,
        ("payment_confirmed", "unique_outbox_instruction"),
        ("outbox_instruction",),
    ),
    _rule(
        StateMachine.VENDOR_PREPARATION,
        VendorPreparationState.VENDOR_NOTIFIED,
        "start_preparing",
        VendorPreparationState.PREPARING,
        ActorSource.VENDOR,
        ("payment_confirmed",),
        ("vendor_acknowledgement",),
    ),
    _rule(
        StateMachine.VENDOR_PREPARATION,
        VendorPreparationState.PREPARING,
        "mark_ready_for_inbound",
        VendorPreparationState.READY_FOR_INBOUND,
        ActorSource.VENDOR,
        ("vendor_preparation_checklist_complete",),
        ("preparation_checklist",),
    ),
    _rule(
        StateMachine.VENDOR_PREPARATION,
        (
            VendorPreparationState.VENDOR_NOTIFIED,
            VendorPreparationState.PREPARING,
            VendorPreparationState.READY_FOR_INBOUND,
        ),
        "block",
        VendorPreparationState.BLOCKED,
        (ActorSource.OPERATIONS, ActorSource.SLA_POLICY),
        ("payment_confirmed",),
        ("block_reason",),
    ),
    _rule(
        StateMachine.VENDOR_PREPARATION,
        VendorPreparationState.BLOCKED,
        "resume_preparing",
        VendorPreparationState.PREPARING,
        ActorSource.OPERATIONS,
        ("remediation_approved",),
        ("remediation_record",),
    ),
    _rule(
        StateMachine.VENDOR_PREPARATION,
        VendorPreparationState.BLOCKED,
        "restore_ready",
        VendorPreparationState.READY_FOR_INBOUND,
        ActorSource.OPERATIONS,
        ("remediation_approved", "vendor_preparation_checklist_complete"),
        ("remediation_record", "preparation_checklist"),
    ),
    _rule(
        StateMachine.VENDOR_PREPARATION,
        (
            VendorPreparationState.NOT_STARTED,
            VendorPreparationState.VENDOR_NOTIFIED,
            VendorPreparationState.PREPARING,
            VendorPreparationState.READY_FOR_INBOUND,
            VendorPreparationState.BLOCKED,
        ),
        "cancel",
        VendorPreparationState.CANCELLED,
        ActorSource.OPERATIONS,
        ("cancellation_approved", "refund_and_disposition_recorded"),
        ("cancellation_approval", "refund_disposition"),
        compensation="preserve_refund_and_stock_disposition",
    ),
)

_POLICY += (
    # Inbound transfer lifecycle.
    _rule(
        StateMachine.INBOUND,
        InboundState.NOT_REQUESTED,
        "plan_inbound",
        InboundState.PLANNED,
        ActorSource.OPERATIONS,
        (
            "payment_confirmed",
            "vendor_ready",
            "active_target_hub",
            "route_provider_selected",
            "unique_cohort_transfer",
        ),
        ("inbound_planning",),
    ),
    _rule(
        StateMachine.INBOUND,
        InboundState.PLANNED,
        "provider_acceptance",
        InboundState.ACCEPTED_BY_PROVIDER,
        ActorSource.INBOUND_PROVIDER,
        ("provider_acceptance_verified",),
        ("sanitized_provider_reference", "provider_acceptance"),
    ),
    _rule(
        StateMachine.INBOUND,
        InboundState.ACCEPTED_BY_PROVIDER,
        "vendor_handoff",
        InboundState.HANDED_OVER,
        ActorSource.INBOUND_PROVIDER,
        ("handoff_parties_time_location_verified",),
        ("handoff_receipt",),
    ),
    _rule(
        StateMachine.INBOUND,
        InboundState.PLANNED,
        "operations_attested_acceptance",
        InboundState.ACCEPTED_BY_PROVIDER,
        ActorSource.OPERATIONS,
        (
            "attestation_source_recorded",
            "attestation_reason_recorded",
            "attestation_proof_verified",
            "second_authorization",
        ),
        (
            "attestation_source",
            "attestation_reason",
            "attestation_proof",
            "second_authorization_evidence",
        ),
    ),
    _rule(
        StateMachine.INBOUND,
        InboundState.ACCEPTED_BY_PROVIDER,
        "operations_attested_handoff",
        InboundState.HANDED_OVER,
        ActorSource.OPERATIONS,
        (
            "attestation_source_recorded",
            "attestation_reason_recorded",
            "attestation_proof_verified",
            "second_authorization",
        ),
        (
            "attestation_source",
            "attestation_reason",
            "attestation_proof",
            "second_authorization_evidence",
        ),
    ),
    _rule(
        StateMachine.INBOUND,
        InboundState.HANDED_OVER,
        "movement_confirmed",
        InboundState.IN_TRANSIT,
        ActorSource.INBOUND_PROVIDER,
        ("provider_movement_verified",),
        ("movement_event",),
    ),
    _rule(
        StateMachine.INBOUND,
        (InboundState.IN_TRANSIT, InboundState.DELAYED),
        "partial_hub_receipt",
        InboundState.RECEIVED_PARTIAL,
        ActorSource.HUB_OPERATOR,
        ("duplicate_safe_receipt",),
        ("item_quantity_receipt_evidence",),
    ),
    _rule(
        StateMachine.INBOUND,
        (
            InboundState.IN_TRANSIT,
            InboundState.RECEIVED_PARTIAL,
            InboundState.DELAYED,
        ),
        "complete_hub_receipt",
        InboundState.RECEIVED_COMPLETE,
        ActorSource.HUB_OPERATOR,
        ("all_noncancelled_quantities_received",),
        ("complete_receipt_reconciliation",),
    ),
    _rule(
        StateMachine.INBOUND,
        (InboundState.PLANNED, InboundState.ACCEPTED_BY_PROVIDER),
        "cancel_before_handoff",
        InboundState.CANCELLED,
        ActorSource.OPERATIONS,
        ("no_handoff", "provider_cancelled_if_accepted"),
        ("provider_cancellation_proof",),
    ),
    _rule(
        StateMachine.INBOUND,
        (
            InboundState.HANDED_OVER,
            InboundState.IN_TRANSIT,
            InboundState.RECEIVED_PARTIAL,
        ),
        "delay_reported",
        InboundState.DELAYED,
        ActorSource.INBOUND_PROVIDER,
        ("delay_attested",),
        ("delay_reason", "expected_recovery", "delay_owner"),
    ),
    _rule(
        StateMachine.INBOUND,
        (
            InboundState.HANDED_OVER,
            InboundState.IN_TRANSIT,
            InboundState.RECEIVED_PARTIAL,
        ),
        "operations_attested_delay",
        InboundState.DELAYED,
        ActorSource.OPERATIONS,
        (
            "attestation_source_recorded",
            "attestation_reason_recorded",
            "attestation_proof_verified",
            "second_authorization",
        ),
        (
            "attestation_source",
            "attestation_reason",
            "attestation_proof",
            "second_authorization_evidence",
        ),
    ),
    _rule(
        StateMachine.INBOUND,
        InboundState.DELAYED,
        "movement_resumed",
        InboundState.IN_TRANSIT,
        ActorSource.INBOUND_PROVIDER,
        ("provider_movement_verified",),
        ("movement_resumption_event",),
    ),
    _rule(
        StateMachine.INBOUND,
        (
            InboundState.HANDED_OVER,
            InboundState.IN_TRANSIT,
            InboundState.RECEIVED_PARTIAL,
            InboundState.DELAYED,
        ),
        "loss_confirmed",
        InboundState.LOST,
        ActorSource.INBOUND_PROVIDER,
        ("shopsoma_loss_investigation_complete",),
        ("shopsoma_loss_investigation",),
    ),
    _rule(
        StateMachine.INBOUND,
        (
            InboundState.HANDED_OVER,
            InboundState.IN_TRANSIT,
            InboundState.RECEIVED_PARTIAL,
            InboundState.DELAYED,
        ),
        "operations_attested_loss",
        InboundState.LOST,
        ActorSource.OPERATIONS,
        (
            "attestation_source_recorded",
            "attestation_reason_recorded",
            "attestation_proof_verified",
            "second_authorization",
            "shopsoma_loss_investigation_complete",
        ),
        (
            "attestation_source",
            "attestation_reason",
            "attestation_proof",
            "second_authorization_evidence",
            "shopsoma_loss_investigation",
        ),
    ),
    _rule(
        StateMachine.INBOUND,
        (
            InboundState.HANDED_OVER,
            InboundState.IN_TRANSIT,
            InboundState.RECEIVED_PARTIAL,
            InboundState.DELAYED,
        ),
        "damage_confirmed",
        InboundState.DAMAGED,
        (ActorSource.HUB_OPERATOR, ActorSource.OPERATIONS),
        ("damaged_items_quarantined",),
        ("condition_evidence", "quarantine_evidence"),
    ),
    # Hub processing lifecycle.
    _rule(
        StateMachine.HUB,
        HubState.AWAITING_RECEIPT,
        "all_required_items_received",
        HubState.RECEIVED,
        ActorSource.HUB_SERVICE,
        ("all_noncancelled_items_reconciled",),
        ("receipt_reconciliation",),
    ),
    _rule(
        StateMachine.HUB,
        HubState.RECEIVED,
        "queue_qc",
        HubState.QC_PENDING,
        ActorSource.HUB_SERVICE,
        ("receipt_complete",),
        ("qc_queue_record",),
    ),
    _rule(
        StateMachine.HUB,
        HubState.QC_PENDING,
        "start_qc",
        HubState.QC_IN_PROGRESS,
        ActorSource.HUB_OPERATOR,
        ("qc_assignment_active",),
        ("qc_assignment",),
    ),
    _rule(
        StateMachine.HUB,
        HubState.QC_IN_PROGRESS,
        "all_items_pass",
        HubState.QC_PASSED,
        ActorSource.HUB_OPERATOR,
        ("all_item_decisions_pass",),
        ("qc_decisions", "qc_evidence"),
    ),
    _rule(
        StateMachine.HUB,
        HubState.QC_IN_PROGRESS,
        "any_item_fails",
        HubState.QC_FAILED,
        ActorSource.HUB_OPERATOR,
        ("at_least_one_item_failed", "failed_items_quarantined"),
        ("qc_failure_reason", "qc_evidence"),
    ),
    _rule(
        StateMachine.HUB,
        HubState.QC_FAILED,
        "approve_remediation",
        HubState.REMEDIATION,
        ActorSource.QC_ADMIN,
        ("remediation_disposition_approved",),
        ("remediation_owner", "remediation_action", "remediation_disposition"),
    ),
    _rule(
        StateMachine.HUB,
        HubState.REMEDIATION,
        "remediation_completed",
        HubState.QC_PENDING,
        ActorSource.HUB_OPERATOR,
        ("new_qc_version",),
        ("replacement_or_rework_proof",),
    ),
    _rule(
        StateMachine.HUB,
        HubState.QC_PASSED,
        "aggregate_ready_to_pack",
        HubState.READY_TO_PACK,
        ActorSource.HUB_SERVICE,
        ("all_cohorts_qc_passed",),
        ("cohort_qc_aggregation",),
    ),
    _rule(
        StateMachine.HUB,
        HubState.READY_TO_PACK,
        "record_package_composition",
        HubState.PACKED,
        ActorSource.HUB_OPERATOR,
        ("approved_items_only", "positive_final_metrics", "new_package_version"),
        ("package_composition", "package_metrics"),
    ),
    _rule(
        StateMachine.HUB,
        HubState.PACKED,
        "apply_seal",
        HubState.SEALED,
        ActorSource.HUB_OPERATOR,
        ("unique_active_seal",),
        ("seal_evidence",),
    ),
    _rule(
        StateMachine.HUB,
        HubState.SEALED,
        "outbound_checks_pass",
        HubState.READY_FOR_DHL,
        ActorSource.SHIPPING_POLICY,
        ("destination_valid", "package_valid", "rate_valid", "no_shipping_exception"),
        ("outbound_check_result",),
    ),
    _rule(
        StateMachine.HUB,
        (HubState.SEALED, HubState.READY_FOR_DHL),
        "authorized_unseal",
        HubState.UNSEALED,
        ActorSource.HUB_SUPERVISOR,
        ("before_dhl_handoff", "shipment_intent_invalidated", "seal_retired"),
        ("unseal_reason", "unseal_evidence"),
    ),
    _rule(
        StateMachine.HUB,
        HubState.UNSEALED,
        "record_repack",
        HubState.REPACKED,
        ActorSource.HUB_OPERATOR,
        ("revised_package_version",),
        ("revised_composition", "revised_metrics", "repack_audit"),
    ),
    _rule(
        StateMachine.HUB,
        HubState.REPACKED,
        "apply_new_seal",
        HubState.SEALED,
        ActorSource.HUB_OPERATOR,
        ("new_package_version", "new_unique_seal"),
        ("new_seal_evidence",),
    ),
    _rule(
        StateMachine.HUB,
        (
            HubState.AWAITING_RECEIPT,
            HubState.RECEIVED,
            HubState.QC_PENDING,
            HubState.QC_IN_PROGRESS,
            HubState.QC_FAILED,
            HubState.REMEDIATION,
            HubState.QC_PASSED,
            HubState.READY_TO_PACK,
        ),
        "approved_cancellation",
        HubState.CANCELLED,
        ActorSource.OPERATIONS,
        ("cancellation_approved", "refund_and_disposition_recorded"),
        ("cancellation_approval", "refund_disposition"),
        compensation="preserve_refund_and_stock_disposition",
    ),
    # DHL outbound lifecycle.
    _rule(
        StateMachine.OUTBOUND,
        OutboundState.NOT_READY,
        "package_ready",
        OutboundState.INTENT_CREATED,
        ActorSource.SHIPMENT_INTENT_SERVICE,
        (
            "hub_ready_for_dhl",
            "immutable_package_version",
            "active_seal",
            "server_hub_origin",
            "unique_shipment_intent",
        ),
        ("shipment_intent",),
    ),
    _rule(
        StateMachine.OUTBOUND,
        OutboundState.INTENT_CREATED,
        "create_shipment",
        OutboundState.BOOKED,
        ActorSource.SHIPMENT_SERVICE,
        ("provider_gate_passed", "exact_package_version", "unique_provider_request"),
        ("sanitized_provider_success",),
    ),
    _rule(
        StateMachine.OUTBOUND,
        OutboundState.BOOKED,
        "label_received",
        OutboundState.LABEL_READY,
        ActorSource.DHL_ADAPTER,
        ("matching_shipment",),
        ("private_label_metadata",),
    ),
    _rule(
        StateMachine.OUTBOUND,
        OutboundState.LABEL_READY,
        "schedule_hub_collection",
        OutboundState.AWAITING_COLLECTION,
        ActorSource.OPERATIONS,
        ("dhl_collection_accepted",),
        ("dhl_acceptance_proof",),
    ),
    _rule(
        StateMachine.OUTBOUND,
        OutboundState.AWAITING_COLLECTION,
        "dhl_acceptance_handoff",
        OutboundState.COLLECTED,
        ActorSource.DHL_EVENT,
        ("matching_shipment_package_seal",),
        ("signed_handoff_or_dhl_event",),
    ),
    _rule(
        StateMachine.OUTBOUND,
        OutboundState.COLLECTED,
        "carrier_in_transit",
        OutboundState.IN_TRANSIT,
        ActorSource.DHL_EVENT,
        ("matching_dhl_shipment",),
        ("dhl_movement_event",),
    ),
    _rule(
        StateMachine.OUTBOUND,
        OutboundState.IN_TRANSIT,
        "carrier_out_for_delivery",
        OutboundState.OUT_FOR_DELIVERY,
        ActorSource.DHL_EVENT,
        ("matching_dhl_shipment",),
        ("dhl_out_for_delivery_event",),
    ),
    _rule(
        StateMachine.OUTBOUND,
        (OutboundState.OUT_FOR_DELIVERY, OutboundState.IN_TRANSIT),
        "carrier_delivered",
        OutboundState.DELIVERED,
        ActorSource.DHL_EVENT,
        ("matching_dhl_shipment",),
        ("dhl_delivery_event",),
    ),
    _rule(
        StateMachine.OUTBOUND,
        (
            OutboundState.BOOKED,
            OutboundState.LABEL_READY,
            OutboundState.AWAITING_COLLECTION,
            OutboundState.COLLECTED,
            OutboundState.IN_TRANSIT,
            OutboundState.OUT_FOR_DELIVERY,
        ),
        "carrier_exception",
        OutboundState.EXCEPTION,
        ActorSource.DHL_EVENT,
        ("matching_dhl_shipment",),
        (
            "carrier_exception_code",
            "exception_owner",
            "retryability",
            "customer_safe_detail",
        ),
    ),
    _rule(
        StateMachine.OUTBOUND,
        OutboundState.EXCEPTION,
        "carrier_resumed",
        OutboundState.IN_TRANSIT,
        ActorSource.DHL_EVENT,
        ("exception_retryable",),
        ("dhl_resumption_event",),
    ),
    _rule(
        StateMachine.OUTBOUND,
        OutboundState.EXCEPTION,
        "carrier_return_started",
        OutboundState.RETURNING,
        ActorSource.DHL_EVENT,
        ("matching_dhl_shipment",),
        ("dhl_return_start_event",),
    ),
    _rule(
        StateMachine.OUTBOUND,
        OutboundState.RETURNING,
        "carrier_return_completed",
        OutboundState.RETURNED,
        ActorSource.HUB_OPERATOR,
        ("verified_dhl_return_event", "shopsoma_hub_receipt_complete"),
        ("dhl_return_event", "hub_return_receipt"),
    ),
    _rule(
        StateMachine.OUTBOUND,
        OutboundState.INTENT_CREATED,
        "cancel_unbooked_intent",
        OutboundState.CANCELLED,
        ActorSource.OPERATIONS,
        ("shipment_not_booked",),
        ("intent_cancellation",),
    ),
    _rule(
        StateMachine.OUTBOUND,
        (
            OutboundState.BOOKED,
            OutboundState.LABEL_READY,
            OutboundState.AWAITING_COLLECTION,
        ),
        "provider_cancellation_confirmed",
        OutboundState.CANCELLED,
        ActorSource.DHL_ADAPTER,
        ("not_collected",),
        ("provider_cancellation_proof",),
    ),
)

_TERMINAL_STATES = frozenset(
    {
        QuoteState.EXPIRED,
        QuoteState.CANCELLED,
        QuoteState.CONSUMED,
        PaymentAttemptState.SUPERSEDED,
        PaymentAttemptState.REFUNDED,
        VendorPreparationState.CANCELLED,
        InboundState.RECEIVED_COMPLETE,
        InboundState.CANCELLED,
        InboundState.LOST,
        InboundState.DAMAGED,
        HubState.CANCELLED,
        OutboundState.DELIVERED,
        OutboundState.RETURNED,
        OutboundState.CANCELLED,
    }
)

_CUSTOMER_MILESTONE_ORDER = (
    CustomerMilestone.PAYMENT_CONFIRMED,
    CustomerMilestone.VENDOR_PREPARING,
    CustomerMilestone.MOVING_TO_SHOPSOMA,
    CustomerMilestone.RECEIVED_BY_SHOPSOMA,
    CustomerMilestone.QUALITY_CHECK,
    CustomerMilestone.PACKED_READY,
    CustomerMilestone.DHL_COLLECTED,
    CustomerMilestone.IN_TRANSIT,
    CustomerMilestone.OUT_FOR_DELIVERY,
    CustomerMilestone.DELIVERED,
)
_CUSTOMER_EXCEPTION_PAYMENT_STATES = frozenset(
    {
        PaymentAttemptState.VOID_PENDING,
        PaymentAttemptState.REFUND_PENDING,
        PaymentAttemptState.REFUNDED,
        PaymentAttemptState.RECONCILIATION_FAILED,
    }
)
_CUSTOMER_EXCEPTION_VENDOR_STATES = frozenset({VendorPreparationState.BLOCKED})
_CUSTOMER_EXCEPTION_INBOUND_STATES = frozenset(
    {InboundState.LOST, InboundState.DAMAGED}
)
_CUSTOMER_EXCEPTION_HUB_STATES = frozenset({HubState.QC_FAILED, HubState.REMEDIATION})
_CUSTOMER_EXCEPTION_OUTBOUND_STATES = frozenset(
    {OutboundState.EXCEPTION, OutboundState.RETURNING, OutboundState.RETURNED}
)
_CANCELLED_MACHINE_STATES = frozenset(
    {
        VendorPreparationState.CANCELLED,
        InboundState.CANCELLED,
        HubState.CANCELLED,
        OutboundState.CANCELLED,
    }
)


def _validate_customer_progress(progress: CustomerCohortProgress) -> None:
    expected_types = (
        (progress.payment_state, PaymentAttemptState),
        (progress.vendor_state, VendorPreparationState),
        (progress.inbound_state, InboundState),
        (progress.hub_state, HubState),
        (progress.outbound_state, OutboundState),
    )
    if any(not isinstance(value, enum_type) for value, enum_type in expected_types):
        raise ValueError("customer progress must use authoritative state enums")
    if (
        type(progress.cancelled) is not bool
        or type(progress.cancellation_refund_disposition_recorded) is not bool
    ):
        raise ValueError("cancellation flags must be booleans")

    counts = (progress.received_units, progress.total_units)
    if (counts[0] is None) != (counts[1] is None):
        raise ValueError("received and total unit counts must be supplied together")
    if counts[0] is not None:
        received_units, total_units = counts
        if (
            isinstance(received_units, bool)
            or isinstance(total_units, bool)
            or not isinstance(received_units, int)
            or not isinstance(total_units, int)
            or received_units < 0
            or total_units <= 0
            or received_units > total_units
        ):
            raise ValueError("invalid partial receipt unit counts")
    if progress.inbound_state is InboundState.RECEIVED_PARTIAL:
        received_units = progress.received_units
        total_units = progress.total_units
        if (
            received_units is None
            or total_units is None
            or not 0 < received_units < total_units
        ):
            raise ValueError("partial receipt requires incomplete positive unit counts")
    if progress.inbound_state is InboundState.RECEIVED_COMPLETE and (
        counts[0] is not None and counts[0] != counts[1]
    ):
        raise ValueError("complete receipt unit counts must reconcile")

    machine_cancelled = any(
        state in _CANCELLED_MACHINE_STATES
        for state in (
            progress.vendor_state,
            progress.inbound_state,
            progress.hub_state,
            progress.outbound_state,
        )
    )
    cancellation_represented = machine_cancelled or (
        progress.payment_state is PaymentAttemptState.REFUNDED
    )
    if machine_cancelled and not progress.cancelled:
        raise ValueError("cancelled machine state requires cancellation representation")
    if progress.cancelled:
        if not progress.cancellation_refund_disposition_recorded:
            raise ValueError("cancellation refund and disposition must be recorded")
        if not cancellation_represented:
            raise ValueError("cancelled progress requires cancellation or refund state")
    elif progress.cancellation_refund_disposition_recorded:
        raise ValueError(
            "cancellation refund and disposition cannot exist for active progress"
        )

    # Cancelled cohorts are excluded from customer milestone derivation. Once their
    # cancellation/refund disposition is internally consistent, active-flow
    # prerequisites no longer apply to their terminal snapshots.
    if progress.cancelled:
        return

    payment_is_exception = progress.payment_state in _CUSTOMER_EXCEPTION_PAYMENT_STATES
    if (
        progress.payment_state is not PaymentAttemptState.CONFIRMED
        and not payment_is_exception
    ):
        raise ValueError("customer progress requires confirmed payment")

    if (
        progress.inbound_state is not InboundState.NOT_REQUESTED
        and progress.vendor_state
        not in {
            VendorPreparationState.READY_FOR_INBOUND,
            VendorPreparationState.BLOCKED,
        }
    ):
        raise ValueError("inbound progress requires a ready vendor cohort")
    if (
        progress.hub_state is not HubState.AWAITING_RECEIPT
        and progress.inbound_state is not InboundState.RECEIVED_COMPLETE
    ):
        raise ValueError("hub progress requires complete inbound receipt")
    if (
        progress.outbound_state is not OutboundState.NOT_READY
        and progress.hub_state is not HubState.READY_FOR_DHL
    ):
        raise ValueError("outbound progress requires a DHL-ready package")


def _derive_cohort_milestone(progress: CustomerCohortProgress) -> CustomerMilestone:
    if (
        progress.payment_state in _CUSTOMER_EXCEPTION_PAYMENT_STATES
        or progress.vendor_state in _CUSTOMER_EXCEPTION_VENDOR_STATES
        or progress.inbound_state in _CUSTOMER_EXCEPTION_INBOUND_STATES
        or progress.hub_state in _CUSTOMER_EXCEPTION_HUB_STATES
        or progress.outbound_state in _CUSTOMER_EXCEPTION_OUTBOUND_STATES
    ):
        return CustomerMilestone.EXCEPTION

    outbound_milestones = {
        OutboundState.COLLECTED: CustomerMilestone.DHL_COLLECTED,
        OutboundState.IN_TRANSIT: CustomerMilestone.IN_TRANSIT,
        OutboundState.OUT_FOR_DELIVERY: CustomerMilestone.OUT_FOR_DELIVERY,
        OutboundState.DELIVERED: CustomerMilestone.DELIVERED,
    }
    if progress.outbound_state in outbound_milestones:
        return outbound_milestones[progress.outbound_state]
    if progress.outbound_state is not OutboundState.NOT_READY:
        return CustomerMilestone.PACKED_READY

    if progress.hub_state in {
        HubState.PACKED,
        HubState.SEALED,
        HubState.READY_FOR_DHL,
    }:
        return CustomerMilestone.PACKED_READY
    if progress.hub_state in {
        HubState.QC_PENDING,
        HubState.QC_IN_PROGRESS,
        HubState.QC_PASSED,
        HubState.READY_TO_PACK,
        HubState.UNSEALED,
        HubState.REPACKED,
    }:
        return CustomerMilestone.QUALITY_CHECK
    if progress.hub_state is HubState.RECEIVED:
        return CustomerMilestone.RECEIVED_BY_SHOPSOMA
    if progress.inbound_state is InboundState.RECEIVED_COMPLETE:
        return CustomerMilestone.RECEIVED_BY_SHOPSOMA
    if progress.inbound_state is not InboundState.NOT_REQUESTED:
        return CustomerMilestone.MOVING_TO_SHOPSOMA
    if progress.vendor_state is not VendorPreparationState.NOT_STARTED:
        return CustomerMilestone.VENDOR_PREPARING
    return CustomerMilestone.PAYMENT_CONFIRMED


def derive_customer_milestone(
    progresses: Iterable[CustomerCohortProgress],
) -> CustomerMilestone:
    """Derive the slowest active cohort milestone, with exceptions overriding success."""

    snapshots = tuple(progresses)
    if not snapshots:
        raise ValueError("customer progress cannot be empty")

    active_milestones = []
    for progress in snapshots:
        if not isinstance(progress, CustomerCohortProgress):
            raise ValueError("invalid customer cohort progress snapshot")
        _validate_customer_progress(progress)
        if not progress.cancelled:
            active_milestones.append(_derive_cohort_milestone(progress))

    if not active_milestones:
        raise ValueError("customer progress has no active cohorts")
    if CustomerMilestone.EXCEPTION in active_milestones:
        return CustomerMilestone.EXCEPTION
    order = {
        milestone: index for index, milestone in enumerate(_CUSTOMER_MILESTONE_ORDER)
    }
    return min(active_milestones, key=order.__getitem__)


def iter_transition_edges() -> Iterator[tuple[TransitionRule, TransitionState]]:
    """Yield every concrete edge in deterministic policy order."""

    for rule in _POLICY:
        # Enum aliases express intent-specific names for a shared state; expose
        # the corresponding concrete edge once.
        for from_state in dict.fromkeys(rule.from_states):
            yield rule, from_state


def _is_sanitized_identifier(value: str | None) -> bool:
    return bool(
        isinstance(value, str)
        and 1 <= len(value) <= 200
        and value.isascii()
        and value == value.strip()
        and all(character.isalnum() or character in "._:-/" for character in value)
    )


def _is_sanitized_external_identity(value: str | None) -> bool:
    return _is_sanitized_identifier(value)


def _resolve_duplicate(
    context: TransitionContext,
    machine_rules: tuple[TransitionRule, ...],
) -> TransitionDecision:
    """Authenticate a durable replay before validating the aggregate's advanced state."""

    prior = context.prior_result
    if prior is None:
        raise TransitionRejected("durable prior transition result is required")
    if type(prior) is not PriorTransitionResult:
        raise TransitionRejected("prior result must be a PriorTransitionResult")
    if prior.aggregate_id != context.aggregate_id:
        raise TransitionRejected("durable prior result does not match aggregate")
    if type(context.aggregate_version) is not int or context.aggregate_version < 0:
        raise TransitionRejected("aggregate version is required")
    if context.aggregate_version < prior.result_version:
        raise TransitionRejected(
            "durable prior result does not match request: "
            "aggregate has not reached persisted result"
        )
    if (
        context.aggregate_version == prior.result_version
        and context.current_state != prior.to_state
    ):
        raise TransitionRejected(
            "durable prior result does not match request: "
            "aggregate has not reached persisted result"
        )

    expected_state_type = _STATE_TYPE_BY_MACHINE[context.machine]
    if (
        type(prior.machine) is not StateMachine
        or prior.machine != context.machine
        or type(prior.current_state) is not expected_state_type
        or type(prior.to_state) is not expected_state_type
    ):
        raise TransitionRejected(
            "durable prior transition result does not match request"
        )

    rule = next(
        (
            candidate
            for candidate in machine_rules
            if candidate.action == context.action
            and prior.current_state in candidate.from_states
            and candidate.to_state == prior.to_state
        ),
        None,
    )
    identity = (
        context.machine,
        context.action,
        context.external_source,
        context.event_id,
        context.idempotency_key,
    )
    prior_identity = (
        prior.machine,
        prior.action,
        prior.external_source,
        prior.event_id,
        prior.idempotency_key,
    )
    if rule is None or identity != prior_identity:
        raise TransitionRejected(
            "durable prior transition result does not match request"
        )
    if context.actor not in rule.authorized_sources:
        raise TransitionRejected(f"unauthorized actor {context.actor.value!r}")
    if rule.kind is TransitionKind.EXTERNAL_EVENT:
        if context.external_source is None:
            raise TransitionRejected("external source is required")
        if context.event_id is None:
            raise TransitionRejected("external event id is required")
        if not _is_sanitized_external_identity(context.external_source):
            raise TransitionRejected("external source must be sanitized")
        if not _is_sanitized_external_identity(context.event_id):
            raise TransitionRejected("external event id must be sanitized")
    if rule.idempotency_required and not _is_sanitized_identifier(
        context.idempotency_key
    ):
        raise TransitionRejected(
            "idempotency key must be non-empty, bounded, and sanitized"
        )

    return TransitionDecision(
        allowed=True,
        rule=rule,
        from_state=prior.current_state,
        to_state=prior.to_state,
        side_effect_required=False,
        idempotent_replay=True,
        replay_metadata=prior.replay_metadata,
    )


def resolve_transition(context: TransitionContext) -> TransitionDecision:
    """Resolve and validate a requested transition, rejecting failures closed."""

    if type(context) is not TransitionContext:
        raise TransitionRejected("context must be a TransitionContext")
    if type(context.machine) is not StateMachine:
        raise TransitionRejected("machine must be a StateMachine")
    if type(context.actor) is not ActorSource:
        raise TransitionRejected("actor must be an ActorSource")
    if type(context.duplicate) is not bool:
        raise TransitionRejected("duplicate must be a boolean")
    if not _is_sanitized_identifier(context.aggregate_id):
        raise TransitionRejected(
            "aggregate id must be non-empty, bounded, and sanitized"
        )

    machine_rules = tuple(rule for rule in _POLICY if rule.machine == context.machine)
    if not any(rule.action == context.action for rule in machine_rules):
        raise TransitionRejected(
            f"unknown action {context.action!r} for {context.machine.value}"
        )
    expected_state_type = _STATE_TYPE_BY_MACHINE[context.machine]
    if type(context.current_state) is not expected_state_type:
        raise TransitionRejected(
            f"state {context.current_state!r} does not belong to "
            f"machine {context.machine.value!r}"
        )
    if context.duplicate:
        return _resolve_duplicate(context, machine_rules)
    if context.current_state in _TERMINAL_STATES:
        raise TransitionRejected(f"terminal state {context.current_state.value!r}")

    rule = next(
        (
            candidate
            for candidate in machine_rules
            if candidate.action == context.action
            and context.current_state in candidate.from_states
        ),
        None,
    )
    if rule is None:
        raise TransitionRejected(
            f"illegal transition from {context.current_state.value!r} "
            f"using {context.action!r}"
        )
    if context.actor not in rule.authorized_sources:
        raise TransitionRejected(f"unauthorized actor {context.actor.value!r}")

    if rule.kind is TransitionKind.EXTERNAL_EVENT:
        if context.external_source is None:
            raise TransitionRejected("external source is required")
        if context.event_id is None:
            raise TransitionRejected("external event id is required")
        if not _is_sanitized_external_identity(context.external_source):
            raise TransitionRejected("external source must be sanitized")
        if not _is_sanitized_external_identity(context.event_id):
            raise TransitionRejected("external event id must be sanitized")

    missing_guards = rule.required_guards - context.guards
    if missing_guards:
        raise TransitionRejected(
            f"missing required guards: {', '.join(sorted(missing_guards))}"
        )
    missing_evidence = rule.evidence_requirement - context.evidence
    if missing_evidence:
        raise TransitionRejected(
            f"missing required evidence: {', '.join(sorted(missing_evidence))}"
        )
    if rule.idempotency_required and not _is_sanitized_identifier(
        context.idempotency_key
    ):
        raise TransitionRejected(
            "idempotency key must be non-empty, bounded, and sanitized"
        )
    if type(context.aggregate_version) is not int or context.aggregate_version < 0:
        raise TransitionRejected("aggregate version is required")
    if type(context.expected_version) is not int or context.expected_version < 0:
        raise TransitionRejected("expected aggregate version is required")
    if context.aggregate_version != context.expected_version:
        raise TransitionRejected("stale aggregate version")

    return TransitionDecision(
        allowed=True,
        rule=rule,
        from_state=context.current_state,
        to_state=rule.to_state,
        side_effect_required=True,
        idempotent_replay=False,
        replay_metadata=None,
    )


def validate_transition(context: TransitionContext) -> TransitionDecision:
    """Public validation alias retained for orchestration call sites."""

    return resolve_transition(context)


__all__ = [
    "ActorSource",
    "CustomerCohortProgress",
    "CustomerMilestone",
    "HubState",
    "InboundState",
    "OutboundState",
    "PaymentAttemptState",
    "PriorTransitionResult",
    "QuoteState",
    "StateMachine",
    "TransitionContext",
    "TransitionDecision",
    "TransitionKind",
    "TransitionRejected",
    "TransitionRule",
    "VendorPreparationState",
    "derive_customer_milestone",
    "iter_transition_edges",
    "resolve_transition",
    "validate_transition",
]
