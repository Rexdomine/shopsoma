"""Pure transition policy for domestic quote, payment, and vendor preparation.

The policy describes allowed edges and the evidence required to take them.  It does
not mutate aggregates or perform side effects; callers remain responsible for
persisting the returned decision with optimistic concurrency and idempotency.
"""

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Iterator, Mapping


class StateMachine(str, Enum):
    QUOTE = "quote"
    PAYMENT_ATTEMPT = "payment_attempt"
    VENDOR_PREPARATION = "vendor_preparation"


class QuoteState(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    CONSUMED = "consumed"


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
    DHL_EVENT = "dhl_event"


TransitionState = QuoteState | PaymentAttemptState | VendorPreparationState


@dataclass(frozen=True, slots=True)
class TransitionRule:
    machine: StateMachine
    from_states: tuple[TransitionState, ...]
    action: str
    to_state: TransitionState
    authorized_sources: frozenset[ActorSource]
    required_guards: frozenset[str]
    evidence_requirement: frozenset[str]
    idempotency_required: bool = True
    compensation: str = "none_required"
    retry: str = "safe_with_same_idempotency_key"


@dataclass(frozen=True, slots=True)
class TransitionContext:
    machine: StateMachine
    current_state: TransitionState
    action: str
    actor: ActorSource
    aggregate_version: int | None
    expected_version: int | None
    guards: frozenset[str]
    evidence: frozenset[str]
    idempotency_key: str | None
    duplicate: bool = False


@dataclass(frozen=True, slots=True)
class TransitionDecision:
    allowed: bool
    rule: TransitionRule
    from_state: TransitionState
    to_state: TransitionState
    side_effect_required: bool
    idempotent_replay: bool
    replay_metadata: Mapping[str, object] | None = None


class TransitionRejected(ValueError):
    """Raised when a requested transition is not authorized by the policy."""


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
) -> TransitionRule:
    if not isinstance(from_states, tuple):
        from_states = (from_states,)
    if not isinstance(actors, tuple):
        actors = (actors,)
    return TransitionRule(
        machine=machine,
        from_states=from_states,
        action=action,
        to_state=to_state,
        authorized_sources=frozenset(actors),
        required_guards=frozenset(guards),
        evidence_requirement=frozenset(evidence),
        compensation=compensation,
        retry=retry,
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
        ("cancellation_approved",),
        ("cancellation_approval",),
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
        (ActorSource.VENDOR, ActorSource.OPERATIONS),
        ("payment_confirmed",),
        ("block_reason",),
    ),
    _rule(
        StateMachine.VENDOR_PREPARATION,
        VendorPreparationState.BLOCKED,
        "resume_preparing",
        VendorPreparationState.PREPARING,
        (ActorSource.VENDOR, ActorSource.OPERATIONS),
        ("remediation_approved",),
        ("remediation_record",),
    ),
    _rule(
        StateMachine.VENDOR_PREPARATION,
        VendorPreparationState.BLOCKED,
        "restore_ready",
        VendorPreparationState.READY_FOR_INBOUND,
        (ActorSource.VENDOR, ActorSource.OPERATIONS),
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

_TERMINAL_STATES = frozenset(
    {
        QuoteState.CANCELLED,
        QuoteState.CONSUMED,
        PaymentAttemptState.SUPERSEDED,
        PaymentAttemptState.REFUNDED,
        VendorPreparationState.CANCELLED,
    }
)


def iter_transition_edges() -> Iterator[tuple[TransitionRule, TransitionState]]:
    """Yield every concrete edge in deterministic policy order."""

    for rule in _POLICY:
        # Enum aliases express intent-specific names for a shared state; expose
        # the corresponding concrete edge once.
        for from_state in dict.fromkeys(rule.from_states):
            yield rule, from_state


def resolve_transition(context: TransitionContext) -> TransitionDecision:
    """Resolve and validate a requested transition, rejecting failures closed."""

    machine_rules = tuple(rule for rule in _POLICY if rule.machine == context.machine)
    if not any(rule.action == context.action for rule in machine_rules):
        raise TransitionRejected(
            f"unknown action {context.action!r} for {context.machine.value}"
        )
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
    if rule.idempotency_required and not context.idempotency_key:
        raise TransitionRejected("idempotency key is required")
    if context.aggregate_version is None:
        raise TransitionRejected("aggregate version is required")
    if context.expected_version is None:
        raise TransitionRejected("expected aggregate version is required")
    if context.aggregate_version != context.expected_version:
        raise TransitionRejected("stale aggregate version")

    replay_metadata: Mapping[str, object] | None = None
    if context.duplicate:
        replay_metadata = MappingProxyType(
            {
                "idempotency_key": context.idempotency_key,
                "aggregate_version": context.aggregate_version,
                "action": context.action,
            }
        )
    return TransitionDecision(
        allowed=True,
        rule=rule,
        from_state=context.current_state,
        to_state=rule.to_state,
        side_effect_required=not context.duplicate,
        idempotent_replay=context.duplicate,
        replay_metadata=replay_metadata,
    )


def validate_transition(context: TransitionContext) -> TransitionDecision:
    """Public validation alias retained for orchestration call sites."""

    return resolve_transition(context)


__all__ = [
    "ActorSource",
    "PaymentAttemptState",
    "QuoteState",
    "StateMachine",
    "TransitionContext",
    "TransitionDecision",
    "TransitionRejected",
    "TransitionRule",
    "VendorPreparationState",
    "iter_transition_edges",
    "resolve_transition",
    "validate_transition",
]
