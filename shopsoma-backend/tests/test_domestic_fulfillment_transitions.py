from dataclasses import FrozenInstanceError

import pytest

from app.services.fulfillment.transitions import (
    ActorSource,
    PaymentAttemptState,
    QuoteState,
    StateMachine,
    TransitionContext,
    TransitionRejected,
    VendorPreparationState,
    iter_transition_edges,
    resolve_transition,
    validate_transition,
)


ALL_GUARDS = frozenset(
    {
        "quote_age_at_least_30m",
        "no_eligible_payment_attempt",
        "no_confirmed_payment_attempt",
        "first_valid_payment",
        "attempt_persisted_for_reconciliation",
        "before_quote_expiry_30m",
        "authenticated_gateway_response",
        "unique_provider_reference",
        "verified_exact_payment_success",
        "within_payment_grace_45m",
        "payment_grace_elapsed_45m",
        "after_payment_grace_45m",
        "order_and_stock_locks_held",
        "late_exact_payment_proved",
        "stock_reacquired",
        "stock_unavailable",
        "cancellation_approved",
        "provider_result_verified",
        "retries_exhausted",
        "finance_retry_authorized",
        "payment_confirmed",
        "unique_outbox_instruction",
        "vendor_preparation_checklist_complete",
        "remediation_approved",
        "refund_and_disposition_recorded",
    }
)
ALL_EVIDENCE = frozenset(
    {
        "timer_observation",
        "cancellation_record",
        "payment_confirmation",
        "persisted_attempt",
        "gateway_response",
        "gateway_failure",
        "replacement_attempt",
        "verified_payment",
        "late_payment_proof",
        "stock_reacquisition",
        "stock_unavailability",
        "cancellation_approval",
        "provider_refund_or_void_result",
        "reconciliation_exhaustion",
        "finance_retry_approval",
        "outbox_instruction",
        "vendor_acknowledgement",
        "preparation_checklist",
        "block_reason",
        "remediation_record",
        "refund_disposition",
    }
)


def context_for(rule, from_state=None, **changes):
    values = {
        "machine": rule.machine,
        "current_state": from_state or rule.from_states[0],
        "action": rule.action,
        "actor": next(iter(rule.authorized_sources)),
        "aggregate_version": 7,
        "expected_version": 7,
        "guards": ALL_GUARDS,
        "evidence": ALL_EVIDENCE,
        "idempotency_key": "event/order/7",
    }
    values.update(changes)
    return TransitionContext(**values)


EDGES = tuple(iter_transition_edges())


def test_policy_contains_every_authoritative_quote_payment_vendor_edge() -> None:
    expected = {
        # Quote.
        (StateMachine.QUOTE, QuoteState.ACTIVE, "expire", QuoteState.EXPIRED),
        (StateMachine.QUOTE, QuoteState.ACTIVE, "cancel", QuoteState.CANCELLED),
        (StateMachine.QUOTE, QuoteState.ACTIVE, "consume", QuoteState.CONSUMED),
        # Payment attempt.
        (
            StateMachine.PAYMENT_ATTEMPT,
            PaymentAttemptState.ATTEMPT_CREATED,
            "initialize",
            PaymentAttemptState.INITIALIZING,
        ),
        (
            StateMachine.PAYMENT_ATTEMPT,
            PaymentAttemptState.INITIALIZING,
            "record_pending",
            PaymentAttemptState.PENDING,
        ),
        (
            StateMachine.PAYMENT_ATTEMPT,
            PaymentAttemptState.INITIALIZING,
            "record_initialization_failure",
            PaymentAttemptState.FAILED,
        ),
        (
            StateMachine.PAYMENT_ATTEMPT,
            PaymentAttemptState.FAILED,
            "supersede",
            PaymentAttemptState.SUPERSEDED,
        ),
        (
            StateMachine.PAYMENT_ATTEMPT,
            PaymentAttemptState.PENDING,
            "confirm",
            PaymentAttemptState.CONFIRMED,
        ),
        (
            StateMachine.PAYMENT_ATTEMPT,
            PaymentAttemptState.PENDING,
            "record_failure",
            PaymentAttemptState.FAILED,
        ),
        (
            StateMachine.PAYMENT_ATTEMPT,
            PaymentAttemptState.PENDING,
            "expire_attempt",
            PaymentAttemptState.ATTEMPT_EXPIRED,
        ),
        (
            StateMachine.PAYMENT_ATTEMPT,
            PaymentAttemptState.ATTEMPT_EXPIRED,
            "start_late_reacquire",
            PaymentAttemptState.LATE_REACQUIRE,
        ),
        (
            StateMachine.PAYMENT_ATTEMPT,
            PaymentAttemptState.LATE_REACQUIRE,
            "confirm_after_reacquire",
            PaymentAttemptState.CONFIRMED,
        ),
        (
            StateMachine.PAYMENT_ATTEMPT,
            PaymentAttemptState.LATE_REACQUIRE,
            "request_void",
            PaymentAttemptState.VOID_PENDING,
        ),
        (
            StateMachine.PAYMENT_ATTEMPT,
            PaymentAttemptState.CONFIRMED,
            "request_refund",
            PaymentAttemptState.REFUND_PENDING,
        ),
        *{
            (
                StateMachine.PAYMENT_ATTEMPT,
                state,
                "record_provider_refund",
                PaymentAttemptState.REFUNDED,
            )
            for state in (
                PaymentAttemptState.VOID_PENDING,
                PaymentAttemptState.REFUND_PENDING,
            )
        },
        *{
            (
                StateMachine.PAYMENT_ATTEMPT,
                state,
                "mark_reconciliation_failed",
                PaymentAttemptState.RECONCILIATION_FAILED,
            )
            for state in (
                PaymentAttemptState.VOID_PENDING,
                PaymentAttemptState.REFUND_PENDING,
            )
        },
        (
            StateMachine.PAYMENT_ATTEMPT,
            PaymentAttemptState.RECONCILIATION_FAILED,
            "retry_void",
            PaymentAttemptState.VOID_PENDING,
        ),
        (
            StateMachine.PAYMENT_ATTEMPT,
            PaymentAttemptState.RECONCILIATION_FAILED,
            "retry_refund",
            PaymentAttemptState.REFUND_PENDING,
        ),
        # Vendor preparation.
        (
            StateMachine.VENDOR_PREPARATION,
            VendorPreparationState.NOT_STARTED,
            "notify_vendor",
            VendorPreparationState.VENDOR_NOTIFIED,
        ),
        (
            StateMachine.VENDOR_PREPARATION,
            VendorPreparationState.VENDOR_NOTIFIED,
            "start_preparing",
            VendorPreparationState.PREPARING,
        ),
        (
            StateMachine.VENDOR_PREPARATION,
            VendorPreparationState.PREPARING,
            "mark_ready_for_inbound",
            VendorPreparationState.READY_FOR_INBOUND,
        ),
        *{
            (
                StateMachine.VENDOR_PREPARATION,
                state,
                "block",
                VendorPreparationState.BLOCKED,
            )
            for state in (
                VendorPreparationState.VENDOR_NOTIFIED,
                VendorPreparationState.PREPARING,
                VendorPreparationState.READY_FOR_INBOUND,
            )
        },
        (
            StateMachine.VENDOR_PREPARATION,
            VendorPreparationState.BLOCKED,
            "resume_preparing",
            VendorPreparationState.PREPARING,
        ),
        (
            StateMachine.VENDOR_PREPARATION,
            VendorPreparationState.BLOCKED,
            "restore_ready",
            VendorPreparationState.READY_FOR_INBOUND,
        ),
        *{
            (
                StateMachine.VENDOR_PREPARATION,
                state,
                "cancel",
                VendorPreparationState.CANCELLED,
            )
            for state in (
                VendorPreparationState.NOT_STARTED,
                VendorPreparationState.VENDOR_NOTIFIED,
                VendorPreparationState.PREPARING,
                VendorPreparationState.READY_FOR_INBOUND,
                VendorPreparationState.BLOCKED,
            )
        },
    }
    actual = {
        (rule.machine, state, rule.action, rule.to_state) for rule, state in EDGES
    }

    assert actual == expected
    assert len(actual) == 33


@pytest.mark.parametrize("rule,from_state", EDGES)
def test_every_policy_edge_resolves_with_complete_context(rule, from_state) -> None:
    decision = resolve_transition(context_for(rule, from_state))

    assert decision.allowed is True
    assert decision.rule is rule
    assert decision.from_state == from_state
    assert decision.to_state == rule.to_state
    assert decision.side_effect_required is True
    assert decision.idempotent_replay is False


def test_policy_metadata_is_explicit_and_immutable() -> None:
    for rule, _ in EDGES:
        assert rule.authorized_sources
        assert rule.evidence_requirement
        assert rule.idempotency_required is True
        assert rule.compensation is not None
        assert rule.retry is not None

    with pytest.raises(FrozenInstanceError):
        EDGES[0][0].action = "mutate"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"actor": ActorSource.DHL_EVENT}, "unauthorized actor"),
        ({"guards": frozenset()}, "missing required guards"),
        ({"evidence": frozenset()}, "missing required evidence"),
        ({"idempotency_key": None}, "idempotency key"),
        ({"aggregate_version": None}, "aggregate version is required"),
        ({"expected_version": None}, "expected aggregate version is required"),
        ({"aggregate_version": 6}, "stale aggregate version"),
    ],
)
def test_resolution_fails_closed_when_context_is_incomplete_or_stale(
    change, message
) -> None:
    rule, from_state = next(
        edge for edge in EDGES if edge[0].action == "record_pending"
    )

    with pytest.raises(TransitionRejected, match=message):
        resolve_transition(context_for(rule, from_state, **change))


def test_unknown_action_and_illegal_state_transition_are_rejected() -> None:
    rule, from_state = EDGES[0]

    with pytest.raises(TransitionRejected, match="unknown action"):
        resolve_transition(context_for(rule, from_state, action="does_not_exist"))

    with pytest.raises(TransitionRejected, match="illegal transition"):
        resolve_transition(context_for(rule, QuoteState.EXPIRED, action="expire"))


def test_terminal_states_reject_all_transitions() -> None:
    rule, _ = EDGES[0]

    with pytest.raises(TransitionRejected, match="terminal state"):
        resolve_transition(context_for(rule, QuoteState.CONSUMED, action="cancel"))


def test_duplicate_returns_replay_decision_without_another_side_effect() -> None:
    rule, from_state = next(edge for edge in EDGES if edge[0].action == "confirm")

    decision = validate_transition(context_for(rule, from_state, duplicate=True))

    assert decision.allowed is True
    assert decision.idempotent_replay is True
    assert decision.side_effect_required is False
    assert decision.replay_metadata == {
        "idempotency_key": "event/order/7",
        "aggregate_version": 7,
        "action": "confirm",
    }


def test_payment_void_and_refund_states_are_distinct() -> None:
    assert PaymentAttemptState.VOID_PENDING is not PaymentAttemptState.REFUND_PENDING
    assert PaymentAttemptState.VOID_PENDING.value == "void_pending"
    assert PaymentAttemptState.REFUND_PENDING.value == "refund_pending"


def test_payment_timing_and_lock_guards_match_authoritative_policy() -> None:
    by_action = {rule.action: rule for rule, _ in EDGES}

    assert by_action["supersede"].required_guards == frozenset(
        {"no_confirmed_payment_attempt", "before_quote_expiry_30m"}
    )
    assert by_action["confirm"].required_guards == frozenset(
        {
            "authenticated_gateway_response",
            "unique_provider_reference",
            "verified_exact_payment_success",
            "within_payment_grace_45m",
            "order_and_stock_locks_held",
        }
    )
    assert by_action["expire_attempt"].required_guards == frozenset(
        {"payment_grace_elapsed_45m", "no_confirmed_payment_attempt"}
    )
    assert by_action["start_late_reacquire"].required_guards == frozenset(
        {
            "after_payment_grace_45m",
            "order_and_stock_locks_held",
            "late_exact_payment_proved",
        }
    )
    assert by_action["request_void"].required_guards == frozenset({"stock_unavailable"})
