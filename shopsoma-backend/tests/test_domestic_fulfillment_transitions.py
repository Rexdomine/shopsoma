from dataclasses import FrozenInstanceError

import pytest

from app.services.fulfillment.transitions import (
    ActorSource,
    CustomerCohortProgress,
    CustomerMilestone,
    HubState,
    InboundState,
    OutboundState,
    PaymentAttemptState,
    PriorTransitionResult,
    QuoteState,
    StateMachine,
    TransitionContext,
    TransitionKind,
    TransitionRejected,
    VendorPreparationState,
    derive_customer_milestone,
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
        "guards": rule.required_guards,
        "evidence": rule.evidence_requirement,
        "idempotency_key": "event/order/7",
        "external_source": (
            "provider.test" if rule.kind is TransitionKind.EXTERNAL_EVENT else None
        ),
        "event_id": "evt-7" if rule.kind is TransitionKind.EXTERNAL_EVENT else None,
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
        (
            StateMachine.QUOTE,
            QuoteState.ACTIVE,
            "create_attempt",
            PaymentAttemptState.ATTEMPT_CREATED,
        ),
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
    legacy_machines = {
        StateMachine.QUOTE,
        StateMachine.PAYMENT_ATTEMPT,
        StateMachine.VENDOR_PREPARATION,
    }
    actual = {
        (rule.machine, state, rule.action, rule.to_state)
        for rule, state in EDGES
        if rule.machine in legacy_machines
    }

    assert actual == expected
    assert len(actual) == 34


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

    with pytest.raises(TransitionRejected, match="terminal state"):
        resolve_transition(context_for(rule, QuoteState.EXPIRED, action="expire"))


def test_terminal_states_reject_all_transitions() -> None:
    rule, _ = EDGES[0]

    with pytest.raises(TransitionRejected, match="terminal state"):
        resolve_transition(context_for(rule, QuoteState.CONSUMED, action="cancel"))

    with pytest.raises(TransitionRejected, match="terminal state"):
        resolve_transition(context_for(rule, QuoteState.EXPIRED, action="cancel"))


def test_duplicate_returns_replay_decision_without_another_side_effect() -> None:
    rule, from_state = next(edge for edge in EDGES if edge[0].action == "confirm")
    prior = PriorTransitionResult(
        machine=rule.machine,
        current_state=from_state,
        action=rule.action,
        external_source="provider.test",
        event_id="evt-7",
        idempotency_key="event/order/7",
        to_state=rule.to_state,
        replay_metadata={"provider_reference": "safe-ref"},
    )

    decision = validate_transition(
        context_for(rule, from_state, duplicate=True, prior_result=prior)
    )

    assert decision.allowed is True
    assert decision.idempotent_replay is True
    assert decision.side_effect_required is False
    assert decision.replay_metadata == {"provider_reference": "safe-ref"}


def test_quote_values_attempt_creation_and_refund_safety_are_authoritative() -> None:
    assert [state.value for state in QuoteState] == [
        "quote_active",
        "quote_expired",
        "quote_cancelled",
        "quote_consumed",
    ]
    create = _rule_for(StateMachine.QUOTE, "create_attempt")
    assert create.kind is TransitionKind.COMMAND
    assert create.from_states == (QuoteState.ACTIVE,)
    assert create.to_state is PaymentAttemptState.ATTEMPT_CREATED
    assert create.authorized_sources == frozenset({ActorSource.CHECKOUT})
    assert create.required_guards == frozenset(
        {
            "quote_owner_session_verified",
            "valid_unexpired_quote_version",
            "before_quote_expiry_30m",
            "reservations_held",
            "no_active_payment_attempt",
        }
    )
    assert create.evidence_requirement == frozenset({"persisted_attempt_request"})
    assert "quote_active" in create.compensation
    assert "same_idempotency_key" in create.retry

    refund = _rule_for(StateMachine.PAYMENT_ATTEMPT, "request_refund")
    assert refund.required_guards == frozenset(
        {
            "cancellation_authorized",
            "refund_items_calculated",
            "fulfillment_stopped",
            "item_disposition_recorded",
        }
    )
    assert refund.evidence_requirement == frozenset(
        {
            "cancellation_approval",
            "refund_item_calculation",
            "fulfillment_stop",
            "item_disposition",
        }
    )


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


NEW_RULES = (
    # Inbound transfer.
    (
        StateMachine.INBOUND,
        (InboundState.NOT_REQUESTED,),
        "plan_inbound",
        InboundState.PLANNED,
        TransitionKind.COMMAND,
        (ActorSource.OPERATIONS,),
    ),
    (
        StateMachine.INBOUND,
        (InboundState.PLANNED,),
        "provider_acceptance",
        InboundState.ACCEPTED_BY_PROVIDER,
        TransitionKind.EXTERNAL_EVENT,
        (ActorSource.INBOUND_PROVIDER,),
    ),
    (
        StateMachine.INBOUND,
        (InboundState.ACCEPTED_BY_PROVIDER,),
        "vendor_handoff",
        InboundState.HANDED_OVER,
        TransitionKind.EXTERNAL_EVENT,
        (ActorSource.INBOUND_PROVIDER,),
    ),
    (
        StateMachine.INBOUND,
        (InboundState.PLANNED,),
        "operations_attested_acceptance",
        InboundState.ACCEPTED_BY_PROVIDER,
        TransitionKind.COMMAND,
        (ActorSource.OPERATIONS,),
    ),
    (
        StateMachine.INBOUND,
        (InboundState.ACCEPTED_BY_PROVIDER,),
        "operations_attested_handoff",
        InboundState.HANDED_OVER,
        TransitionKind.COMMAND,
        (ActorSource.OPERATIONS,),
    ),
    (
        StateMachine.INBOUND,
        (
            InboundState.HANDED_OVER,
            InboundState.IN_TRANSIT,
            InboundState.RECEIVED_PARTIAL,
        ),
        "operations_attested_delay",
        InboundState.DELAYED,
        TransitionKind.COMMAND,
        (ActorSource.OPERATIONS,),
    ),
    (
        StateMachine.INBOUND,
        (
            InboundState.HANDED_OVER,
            InboundState.IN_TRANSIT,
            InboundState.RECEIVED_PARTIAL,
            InboundState.DELAYED,
        ),
        "operations_attested_loss",
        InboundState.LOST,
        TransitionKind.COMMAND,
        (ActorSource.OPERATIONS,),
    ),
    (
        StateMachine.INBOUND,
        (InboundState.HANDED_OVER,),
        "movement_confirmed",
        InboundState.IN_TRANSIT,
        TransitionKind.EXTERNAL_EVENT,
        (ActorSource.INBOUND_PROVIDER,),
    ),
    (
        StateMachine.INBOUND,
        (InboundState.IN_TRANSIT,),
        "partial_hub_receipt",
        InboundState.RECEIVED_PARTIAL,
        TransitionKind.COMMAND,
        (ActorSource.HUB_OPERATOR,),
    ),
    (
        StateMachine.INBOUND,
        (InboundState.IN_TRANSIT, InboundState.RECEIVED_PARTIAL),
        "complete_hub_receipt",
        InboundState.RECEIVED_COMPLETE,
        TransitionKind.COMMAND,
        (ActorSource.HUB_OPERATOR,),
    ),
    (
        StateMachine.INBOUND,
        (InboundState.PLANNED, InboundState.ACCEPTED_BY_PROVIDER),
        "cancel_before_handoff",
        InboundState.CANCELLED,
        TransitionKind.COMMAND,
        (ActorSource.OPERATIONS,),
    ),
    (
        StateMachine.INBOUND,
        (
            InboundState.HANDED_OVER,
            InboundState.IN_TRANSIT,
            InboundState.RECEIVED_PARTIAL,
        ),
        "delay_reported",
        InboundState.DELAYED,
        TransitionKind.EXTERNAL_EVENT,
        (ActorSource.INBOUND_PROVIDER,),
    ),
    (
        StateMachine.INBOUND,
        (InboundState.DELAYED,),
        "movement_resumed",
        InboundState.IN_TRANSIT,
        TransitionKind.EXTERNAL_EVENT,
        (ActorSource.INBOUND_PROVIDER,),
    ),
    (
        StateMachine.INBOUND,
        (
            InboundState.HANDED_OVER,
            InboundState.IN_TRANSIT,
            InboundState.RECEIVED_PARTIAL,
            InboundState.DELAYED,
        ),
        "loss_confirmed",
        InboundState.LOST,
        TransitionKind.EXTERNAL_EVENT,
        (ActorSource.INBOUND_PROVIDER,),
    ),
    (
        StateMachine.INBOUND,
        (
            InboundState.HANDED_OVER,
            InboundState.IN_TRANSIT,
            InboundState.RECEIVED_PARTIAL,
            InboundState.DELAYED,
        ),
        "damage_confirmed",
        InboundState.DAMAGED,
        TransitionKind.COMMAND,
        (ActorSource.HUB_OPERATOR, ActorSource.OPERATIONS),
    ),
    # Hub processing.
    (
        StateMachine.HUB,
        (HubState.AWAITING_RECEIPT,),
        "all_required_items_received",
        HubState.RECEIVED,
        TransitionKind.DERIVED,
        (ActorSource.HUB_SERVICE,),
    ),
    (
        StateMachine.HUB,
        (HubState.RECEIVED,),
        "queue_qc",
        HubState.QC_PENDING,
        TransitionKind.DERIVED,
        (ActorSource.HUB_SERVICE,),
    ),
    (
        StateMachine.HUB,
        (HubState.QC_PENDING,),
        "start_qc",
        HubState.QC_IN_PROGRESS,
        TransitionKind.COMMAND,
        (ActorSource.HUB_OPERATOR,),
    ),
    (
        StateMachine.HUB,
        (HubState.QC_IN_PROGRESS,),
        "all_items_pass",
        HubState.QC_PASSED,
        TransitionKind.COMMAND,
        (ActorSource.HUB_OPERATOR,),
    ),
    (
        StateMachine.HUB,
        (HubState.QC_IN_PROGRESS,),
        "any_item_fails",
        HubState.QC_FAILED,
        TransitionKind.COMMAND,
        (ActorSource.HUB_OPERATOR,),
    ),
    (
        StateMachine.HUB,
        (HubState.QC_FAILED,),
        "approve_remediation",
        HubState.REMEDIATION,
        TransitionKind.COMMAND,
        (ActorSource.QC_ADMIN,),
    ),
    (
        StateMachine.HUB,
        (HubState.REMEDIATION,),
        "remediation_completed",
        HubState.QC_PENDING,
        TransitionKind.COMMAND,
        (ActorSource.HUB_OPERATOR,),
    ),
    (
        StateMachine.HUB,
        (HubState.QC_PASSED,),
        "aggregate_ready_to_pack",
        HubState.READY_TO_PACK,
        TransitionKind.DERIVED,
        (ActorSource.HUB_SERVICE,),
    ),
    (
        StateMachine.HUB,
        (HubState.READY_TO_PACK,),
        "record_package_composition",
        HubState.PACKED,
        TransitionKind.COMMAND,
        (ActorSource.HUB_OPERATOR,),
    ),
    (
        StateMachine.HUB,
        (HubState.PACKED,),
        "apply_seal",
        HubState.SEALED,
        TransitionKind.COMMAND,
        (ActorSource.HUB_OPERATOR,),
    ),
    (
        StateMachine.HUB,
        (HubState.SEALED,),
        "outbound_checks_pass",
        HubState.READY_FOR_DHL,
        TransitionKind.DERIVED,
        (ActorSource.SHIPPING_POLICY,),
    ),
    (
        StateMachine.HUB,
        (HubState.SEALED, HubState.READY_FOR_DHL),
        "authorized_unseal",
        HubState.UNSEALED,
        TransitionKind.COMMAND,
        (ActorSource.HUB_SUPERVISOR,),
    ),
    (
        StateMachine.HUB,
        (HubState.UNSEALED,),
        "record_repack",
        HubState.REPACKED,
        TransitionKind.COMMAND,
        (ActorSource.HUB_OPERATOR,),
    ),
    (
        StateMachine.HUB,
        (HubState.REPACKED,),
        "apply_new_seal",
        HubState.SEALED,
        TransitionKind.COMMAND,
        (ActorSource.HUB_OPERATOR,),
    ),
    (
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
        TransitionKind.COMMAND,
        (ActorSource.OPERATIONS,),
    ),
    # DHL outbound.
    (
        StateMachine.OUTBOUND,
        (OutboundState.NOT_READY,),
        "package_ready",
        OutboundState.INTENT_CREATED,
        TransitionKind.DERIVED,
        (ActorSource.SHIPMENT_INTENT_SERVICE,),
    ),
    (
        StateMachine.OUTBOUND,
        (OutboundState.INTENT_CREATED,),
        "create_shipment",
        OutboundState.BOOKED,
        TransitionKind.COMMAND,
        (ActorSource.SHIPMENT_SERVICE,),
    ),
    (
        StateMachine.OUTBOUND,
        (OutboundState.BOOKED,),
        "label_received",
        OutboundState.LABEL_READY,
        TransitionKind.EXTERNAL_EVENT,
        (ActorSource.DHL_ADAPTER,),
    ),
    (
        StateMachine.OUTBOUND,
        (OutboundState.LABEL_READY,),
        "schedule_hub_collection",
        OutboundState.AWAITING_COLLECTION,
        TransitionKind.COMMAND,
        (ActorSource.OPERATIONS,),
    ),
    (
        StateMachine.OUTBOUND,
        (OutboundState.AWAITING_COLLECTION,),
        "dhl_acceptance_handoff",
        OutboundState.COLLECTED,
        TransitionKind.EXTERNAL_EVENT,
        (ActorSource.DHL_EVENT,),
    ),
    (
        StateMachine.OUTBOUND,
        (OutboundState.COLLECTED,),
        "carrier_in_transit",
        OutboundState.IN_TRANSIT,
        TransitionKind.EXTERNAL_EVENT,
        (ActorSource.DHL_EVENT,),
    ),
    (
        StateMachine.OUTBOUND,
        (OutboundState.IN_TRANSIT,),
        "carrier_out_for_delivery",
        OutboundState.OUT_FOR_DELIVERY,
        TransitionKind.EXTERNAL_EVENT,
        (ActorSource.DHL_EVENT,),
    ),
    (
        StateMachine.OUTBOUND,
        (OutboundState.OUT_FOR_DELIVERY, OutboundState.IN_TRANSIT),
        "carrier_delivered",
        OutboundState.DELIVERED,
        TransitionKind.EXTERNAL_EVENT,
        (ActorSource.DHL_EVENT,),
    ),
    (
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
        TransitionKind.EXTERNAL_EVENT,
        (ActorSource.DHL_EVENT,),
    ),
    (
        StateMachine.OUTBOUND,
        (OutboundState.EXCEPTION,),
        "carrier_resumed",
        OutboundState.IN_TRANSIT,
        TransitionKind.EXTERNAL_EVENT,
        (ActorSource.DHL_EVENT,),
    ),
    (
        StateMachine.OUTBOUND,
        (OutboundState.EXCEPTION,),
        "carrier_return_started",
        OutboundState.RETURNING,
        TransitionKind.EXTERNAL_EVENT,
        (ActorSource.DHL_EVENT,),
    ),
    (
        StateMachine.OUTBOUND,
        (OutboundState.RETURNING,),
        "carrier_return_completed",
        OutboundState.RETURNED,
        TransitionKind.COMMAND,
        (ActorSource.HUB_OPERATOR,),
    ),
    (
        StateMachine.OUTBOUND,
        (OutboundState.INTENT_CREATED,),
        "cancel_unbooked_intent",
        OutboundState.CANCELLED,
        TransitionKind.COMMAND,
        (ActorSource.OPERATIONS,),
    ),
    (
        StateMachine.OUTBOUND,
        (
            OutboundState.BOOKED,
            OutboundState.LABEL_READY,
            OutboundState.AWAITING_COLLECTION,
        ),
        "provider_cancellation_confirmed",
        OutboundState.CANCELLED,
        TransitionKind.EXTERNAL_EVENT,
        (ActorSource.DHL_ADAPTER,),
    ),
)


@pytest.mark.parametrize(
    ("machine", "from_states", "action", "to_state", "kind", "actors"), NEW_RULES
)
def test_every_authoritative_inbound_hub_outbound_rule_has_explicit_metadata(
    machine, from_states, action, to_state, kind, actors
) -> None:
    matches = [
        rule
        for rule, _ in iter_transition_edges()
        if rule.machine == machine and rule.action == action
    ]
    rule = matches[0]

    assert set(matches) == {rule}
    assert rule.from_states == from_states
    assert rule.to_state == to_state
    assert rule.kind is kind
    assert rule.authorized_sources == frozenset(actors)
    assert rule.required_guards
    assert rule.evidence_requirement


EXPECTED_NEW_EDGES = {
    (machine, state, action, to_state)
    for machine, states, action, to_state, _, _ in NEW_RULES
    for state in states
}


def test_policy_contains_exactly_every_new_authoritative_edge() -> None:
    actual = {
        (rule.machine, state, rule.action, rule.to_state)
        for rule, state in iter_transition_edges()
        if rule.machine
        in {StateMachine.INBOUND, StateMachine.HUB, StateMachine.OUTBOUND}
    }
    assert actual == EXPECTED_NEW_EDGES
    assert len(actual) == 75


def test_existing_rules_have_accurate_explicit_transition_kinds() -> None:
    kinds = {
        (rule.machine, rule.action): rule.kind for rule, _ in iter_transition_edges()
    }
    assert kinds[(StateMachine.QUOTE, "expire")] is TransitionKind.TIMER
    assert kinds[(StateMachine.QUOTE, "cancel")] is TransitionKind.COMMAND
    assert kinds[(StateMachine.QUOTE, "consume")] is TransitionKind.DERIVED
    for action in (
        "record_pending",
        "record_initialization_failure",
        "confirm",
        "record_failure",
        "record_provider_refund",
    ):
        assert (
            kinds[(StateMachine.PAYMENT_ATTEMPT, action)]
            is TransitionKind.EXTERNAL_EVENT
        )
    assert (
        kinds[(StateMachine.PAYMENT_ATTEMPT, "expire_attempt")] is TransitionKind.TIMER
    )
    assert (
        kinds[(StateMachine.VENDOR_PREPARATION, "notify_vendor")]
        is TransitionKind.DERIVED
    )
    for action in (
        "start_preparing",
        "mark_ready_for_inbound",
        "block",
        "resume_preparing",
        "restore_ready",
        "cancel",
    ):
        assert (
            kinds[(StateMachine.VENDOR_PREPARATION, action)] is TransitionKind.COMMAND
        )


def _rule_for(machine, action):
    return next(
        rule
        for rule, _ in iter_transition_edges()
        if rule.machine == machine and rule.action == action
    )


def prior_for(rule, from_state=None, **changes):
    values = {
        "machine": rule.machine,
        "current_state": from_state or rule.from_states[0],
        "action": rule.action,
        "external_source": (
            "provider.test" if rule.kind is TransitionKind.EXTERNAL_EVENT else None
        ),
        "event_id": "evt-7" if rule.kind is TransitionKind.EXTERNAL_EVENT else None,
        "idempotency_key": "event/order/7",
        "to_state": rule.to_state,
        "replay_metadata": {"persisted": "result"},
    }
    values.update(changes)
    return PriorTransitionResult(**values)


def test_every_external_event_requires_sanitized_source_and_event_identity() -> None:
    external_rules = {
        rule for rule, _ in EDGES if rule.kind is TransitionKind.EXTERNAL_EVENT
    }
    assert external_rules
    for rule in external_rules:
        with pytest.raises(TransitionRejected, match="external source"):
            resolve_transition(context_for(rule, external_source=None))
        with pytest.raises(TransitionRejected, match="event id"):
            resolve_transition(context_for(rule, event_id=None))
        with pytest.raises(TransitionRejected, match="sanitized"):
            resolve_transition(context_for(rule, external_source=" provider.test "))


def test_duplicate_requires_exact_durable_prior_identity_match() -> None:
    rule = _rule_for(StateMachine.OUTBOUND, "carrier_in_transit")
    context = context_for(rule, duplicate=True)
    with pytest.raises(TransitionRejected, match="durable prior transition result"):
        resolve_transition(context)

    mismatches = (
        {"machine": StateMachine.INBOUND},
        {"current_state": OutboundState.IN_TRANSIT},
        {"action": "carrier_delivered"},
        {"external_source": "other.provider"},
        {"event_id": "evt-other"},
        {"idempotency_key": "other-key"},
    )
    for mismatch in mismatches:
        with pytest.raises(TransitionRejected, match="does not match"):
            resolve_transition(
                context_for(
                    rule, duplicate=True, prior_result=prior_for(rule, **mismatch)
                )
            )

    replay = resolve_transition(
        context_for(rule, duplicate=True, prior_result=prior_for(rule))
    )
    assert replay.to_state is OutboundState.IN_TRANSIT
    assert replay.replay_metadata == {"persisted": "result"}
    assert replay.side_effect_required is False


def test_external_identity_pair_distinguishes_events_and_prior_result_is_immutable() -> (
    None
):
    rule = _rule_for(StateMachine.OUTBOUND, "carrier_in_transit")
    first = context_for(rule, external_source="dhl", event_id="movement-1")
    second = context_for(rule, external_source="dhl", event_id="movement-2")
    assert (first.external_source, first.event_id) != (
        second.external_source,
        second.event_id,
    )
    prior = prior_for(rule)
    with pytest.raises(FrozenInstanceError):
        prior.event_id = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        prior.replay_metadata["persisted"] = "changed"  # type: ignore[index]


def test_vendor_sla_and_provider_fallback_authority_is_separated() -> None:
    block = _rule_for(StateMachine.VENDOR_PREPARATION, "block")
    assert block.authorized_sources == frozenset(
        {ActorSource.OPERATIONS, ActorSource.SLA_POLICY}
    )
    for action in ("resume_preparing", "restore_ready"):
        assert _rule_for(
            StateMachine.VENDOR_PREPARATION, action
        ).authorized_sources == frozenset({ActorSource.OPERATIONS})

    for action in (
        "provider_acceptance",
        "vendor_handoff",
        "delay_reported",
        "loss_confirmed",
    ):
        assert _rule_for(StateMachine.INBOUND, action).authorized_sources == frozenset(
            {ActorSource.INBOUND_PROVIDER}
        )

    fallback = {
        "operations_attested_acceptance",
        "operations_attested_handoff",
        "operations_attested_delay",
        "operations_attested_loss",
    }
    required = {
        "attestation_source_recorded",
        "attestation_reason_recorded",
        "attestation_proof_verified",
        "second_authorization",
    }
    evidence = {
        "attestation_source",
        "attestation_reason",
        "attestation_proof",
        "second_authorization_evidence",
    }
    for action in fallback:
        rule = _rule_for(StateMachine.INBOUND, action)
        assert rule.kind is TransitionKind.COMMAND
        assert rule.authorized_sources == frozenset({ActorSource.OPERATIONS})
        assert required <= rule.required_guards
        assert evidence <= rule.evidence_requirement

    for action in ("loss_confirmed", "operations_attested_loss"):
        rule = _rule_for(StateMachine.INBOUND, action)
        assert "shopsoma_loss_investigation_complete" in rule.required_guards
        assert "shopsoma_loss_investigation" in rule.evidence_requirement


def test_hub_and_return_completion_authority_is_local_and_evidence_backed() -> None:
    remediation = _rule_for(StateMachine.HUB, "remediation_completed")
    assert remediation.authorized_sources == frozenset({ActorSource.HUB_OPERATOR})

    returned = _rule_for(StateMachine.OUTBOUND, "carrier_return_completed")
    assert returned.kind is TransitionKind.COMMAND
    assert returned.authorized_sources == frozenset({ActorSource.HUB_OPERATOR})
    assert returned.required_guards == frozenset(
        {"verified_dhl_return_event", "shopsoma_hub_receipt_complete"}
    )
    assert returned.evidence_requirement == frozenset(
        {"dhl_return_event", "hub_return_receipt"}
    )


@pytest.mark.parametrize(
    "action", ["carrier_in_transit", "carrier_out_for_delivery", "carrier_delivered"]
)
def test_operations_cannot_manually_assert_dhl_movement_or_delivery(action) -> None:
    rule = _rule_for(StateMachine.OUTBOUND, action)
    with pytest.raises(TransitionRejected, match="unauthorized actor"):
        resolve_transition(context_for(rule, actor=ActorSource.OPERATIONS))


@pytest.mark.parametrize(
    ("state", "action"),
    [
        (HubState.AWAITING_RECEIPT, "start_qc"),
        (HubState.RECEIVED, "record_package_composition"),
    ],
)
def test_hub_cannot_qc_before_receipt_or_pack_before_qc(state, action) -> None:
    rule = _rule_for(StateMachine.HUB, action)
    with pytest.raises(TransitionRejected, match="illegal transition"):
        resolve_transition(context_for(rule, from_state=state))


def test_outbound_intent_requires_server_hub_seal_package_and_idempotency_guards() -> (
    None
):
    rule = _rule_for(StateMachine.OUTBOUND, "package_ready")
    assert rule.required_guards == frozenset(
        {
            "hub_ready_for_dhl",
            "immutable_package_version",
            "active_seal",
            "server_hub_origin",
            "unique_shipment_intent",
        }
    )
    with pytest.raises(TransitionRejected, match="missing required guards"):
        resolve_transition(context_for(rule, guards=frozenset()))


@pytest.mark.parametrize(
    ("machine", "state", "action"),
    [
        (StateMachine.INBOUND, InboundState.RECEIVED_COMPLETE, "plan_inbound"),
        (StateMachine.INBOUND, InboundState.LOST, "movement_resumed"),
        (StateMachine.HUB, HubState.CANCELLED, "queue_qc"),
        (StateMachine.OUTBOUND, OutboundState.DELIVERED, "carrier_exception"),
        (StateMachine.OUTBOUND, OutboundState.RETURNED, "carrier_in_transit"),
    ],
)
def test_new_terminal_states_cannot_reopen(machine, state, action) -> None:
    rule = _rule_for(machine, action)
    with pytest.raises(TransitionRejected, match="terminal state"):
        resolve_transition(context_for(rule, from_state=state))


def test_new_transition_missing_proof_fails_closed_and_duplicate_is_replay_safe() -> (
    None
):
    rule = _rule_for(StateMachine.OUTBOUND, "dhl_acceptance_handoff")
    with pytest.raises(TransitionRejected, match="missing required evidence"):
        resolve_transition(context_for(rule, evidence=frozenset()))

    with pytest.raises(TransitionRejected, match="durable prior transition result"):
        resolve_transition(context_for(rule, duplicate=True))

    decision = resolve_transition(
        context_for(rule, duplicate=True, prior_result=prior_for(rule))
    )
    assert decision.idempotent_replay is True
    assert decision.side_effect_required is False


def customer_progress(**changes) -> CustomerCohortProgress:
    values = {
        "payment_state": PaymentAttemptState.CONFIRMED,
        "vendor_state": VendorPreparationState.NOT_STARTED,
        "inbound_state": InboundState.NOT_REQUESTED,
        "hub_state": HubState.AWAITING_RECEIPT,
        "outbound_state": OutboundState.NOT_READY,
    }
    values.update(changes)
    return CustomerCohortProgress(**values)


@pytest.mark.parametrize(
    ("changes", "milestone"),
    [
        ({}, CustomerMilestone.PAYMENT_CONFIRMED),
        (
            {"vendor_state": VendorPreparationState.PREPARING},
            CustomerMilestone.VENDOR_PREPARING,
        ),
        (
            {
                "vendor_state": VendorPreparationState.READY_FOR_INBOUND,
                "inbound_state": InboundState.IN_TRANSIT,
            },
            CustomerMilestone.MOVING_TO_SHOPSOMA,
        ),
        (
            {
                "vendor_state": VendorPreparationState.READY_FOR_INBOUND,
                "inbound_state": InboundState.RECEIVED_COMPLETE,
                "hub_state": HubState.RECEIVED,
            },
            CustomerMilestone.RECEIVED_BY_SHOPSOMA,
        ),
        (
            {
                "vendor_state": VendorPreparationState.READY_FOR_INBOUND,
                "inbound_state": InboundState.RECEIVED_COMPLETE,
                "hub_state": HubState.QC_IN_PROGRESS,
            },
            CustomerMilestone.QUALITY_CHECK,
        ),
        (
            {
                "vendor_state": VendorPreparationState.READY_FOR_INBOUND,
                "inbound_state": InboundState.RECEIVED_COMPLETE,
                "hub_state": HubState.READY_FOR_DHL,
                "outbound_state": OutboundState.AWAITING_COLLECTION,
            },
            CustomerMilestone.PACKED_READY,
        ),
        (
            {
                "vendor_state": VendorPreparationState.READY_FOR_INBOUND,
                "inbound_state": InboundState.RECEIVED_COMPLETE,
                "hub_state": HubState.READY_FOR_DHL,
                "outbound_state": OutboundState.COLLECTED,
            },
            CustomerMilestone.DHL_COLLECTED,
        ),
        (
            {
                "vendor_state": VendorPreparationState.READY_FOR_INBOUND,
                "inbound_state": InboundState.RECEIVED_COMPLETE,
                "hub_state": HubState.READY_FOR_DHL,
                "outbound_state": OutboundState.IN_TRANSIT,
            },
            CustomerMilestone.IN_TRANSIT,
        ),
        (
            {
                "vendor_state": VendorPreparationState.READY_FOR_INBOUND,
                "inbound_state": InboundState.RECEIVED_COMPLETE,
                "hub_state": HubState.READY_FOR_DHL,
                "outbound_state": OutboundState.OUT_FOR_DELIVERY,
            },
            CustomerMilestone.OUT_FOR_DELIVERY,
        ),
        (
            {
                "vendor_state": VendorPreparationState.READY_FOR_INBOUND,
                "inbound_state": InboundState.RECEIVED_COMPLETE,
                "hub_state": HubState.READY_FOR_DHL,
                "outbound_state": OutboundState.DELIVERED,
            },
            CustomerMilestone.DELIVERED,
        ),
    ],
)
def test_customer_snapshot_maps_to_honest_milestone(changes, milestone) -> None:
    assert derive_customer_milestone([customer_progress(**changes)]) is milestone


def test_inbound_movement_and_delay_never_illuminate_dhl_in_transit() -> None:
    for inbound_state in (InboundState.IN_TRANSIT, InboundState.DELAYED):
        progress = customer_progress(
            vendor_state=VendorPreparationState.READY_FOR_INBOUND,
            inbound_state=inbound_state,
        )
        assert (
            derive_customer_milestone([progress])
            is CustomerMilestone.MOVING_TO_SHOPSOMA
        )


def test_vendor_can_be_blocked_after_inbound_started_and_projects_exception() -> None:
    progress = customer_progress(
        vendor_state=VendorPreparationState.BLOCKED,
        inbound_state=InboundState.IN_TRANSIT,
    )
    assert derive_customer_milestone([progress]) is CustomerMilestone.EXCEPTION


def test_multiple_cohorts_use_the_slowest_non_cancelled_milestone() -> None:
    received = customer_progress(
        vendor_state=VendorPreparationState.READY_FOR_INBOUND,
        inbound_state=InboundState.RECEIVED_COMPLETE,
        hub_state=HubState.RECEIVED,
    )
    inbound = customer_progress(
        vendor_state=VendorPreparationState.READY_FOR_INBOUND,
        inbound_state=InboundState.IN_TRANSIT,
    )
    delivered = customer_progress(
        vendor_state=VendorPreparationState.READY_FOR_INBOUND,
        inbound_state=InboundState.RECEIVED_COMPLETE,
        hub_state=HubState.READY_FOR_DHL,
        outbound_state=OutboundState.DELIVERED,
    )
    outbound = customer_progress(
        vendor_state=VendorPreparationState.READY_FOR_INBOUND,
        inbound_state=InboundState.RECEIVED_COMPLETE,
        hub_state=HubState.READY_FOR_DHL,
        outbound_state=OutboundState.IN_TRANSIT,
    )

    assert (
        derive_customer_milestone([received, inbound])
        is CustomerMilestone.MOVING_TO_SHOPSOMA
    )
    assert (
        derive_customer_milestone([delivered, outbound]) is CustomerMilestone.IN_TRANSIT
    )


def test_partial_receipt_remains_inbound_and_exposes_immutable_counts() -> None:
    progress = customer_progress(
        vendor_state=VendorPreparationState.READY_FOR_INBOUND,
        inbound_state=InboundState.RECEIVED_PARTIAL,
        received_units=2,
        total_units=3,
    )
    assert derive_customer_milestone([progress]) is CustomerMilestone.MOVING_TO_SHOPSOMA
    assert (progress.received_units, progress.total_units) == (2, 3)
    with pytest.raises(FrozenInstanceError):
        progress.received_units = 3  # type: ignore[misc]


@pytest.mark.parametrize(
    "changes",
    [
        {"payment_state": PaymentAttemptState.REFUND_PENDING},
        {"payment_state": PaymentAttemptState.REFUNDED},
        {"payment_state": PaymentAttemptState.RECONCILIATION_FAILED},
        {"vendor_state": VendorPreparationState.BLOCKED},
        {
            "vendor_state": VendorPreparationState.READY_FOR_INBOUND,
            "inbound_state": InboundState.LOST,
        },
        {
            "vendor_state": VendorPreparationState.READY_FOR_INBOUND,
            "inbound_state": InboundState.DAMAGED,
        },
        {
            "vendor_state": VendorPreparationState.READY_FOR_INBOUND,
            "inbound_state": InboundState.RECEIVED_COMPLETE,
            "hub_state": HubState.QC_FAILED,
        },
        {
            "vendor_state": VendorPreparationState.READY_FOR_INBOUND,
            "inbound_state": InboundState.RECEIVED_COMPLETE,
            "hub_state": HubState.REMEDIATION,
        },
        {
            "vendor_state": VendorPreparationState.READY_FOR_INBOUND,
            "inbound_state": InboundState.RECEIVED_COMPLETE,
            "hub_state": HubState.READY_FOR_DHL,
            "outbound_state": OutboundState.EXCEPTION,
        },
        {
            "vendor_state": VendorPreparationState.READY_FOR_INBOUND,
            "inbound_state": InboundState.RECEIVED_COMPLETE,
            "hub_state": HubState.READY_FOR_DHL,
            "outbound_state": OutboundState.RETURNING,
        },
        {
            "vendor_state": VendorPreparationState.READY_FOR_INBOUND,
            "inbound_state": InboundState.RECEIVED_COMPLETE,
            "hub_state": HubState.READY_FOR_DHL,
            "outbound_state": OutboundState.RETURNED,
        },
    ],
)
def test_exception_states_override_success_milestones(changes) -> None:
    exception = customer_progress(**changes)
    delivered = customer_progress(
        vendor_state=VendorPreparationState.READY_FOR_INBOUND,
        inbound_state=InboundState.RECEIVED_COMPLETE,
        hub_state=HubState.READY_FOR_DHL,
        outbound_state=OutboundState.DELIVERED,
    )
    assert (
        derive_customer_milestone([exception, delivered]) is CustomerMilestone.EXCEPTION
    )


def test_cancelled_cohort_is_excluded_only_with_recorded_disposition() -> None:
    active = customer_progress(vendor_state=VendorPreparationState.PREPARING)
    cancelled = customer_progress(
        payment_state=PaymentAttemptState.REFUNDED,
        vendor_state=VendorPreparationState.CANCELLED,
        cancelled=True,
        cancellation_refund_disposition_recorded=True,
    )
    assert (
        derive_customer_milestone([active, cancelled])
        is CustomerMilestone.VENDOR_PREPARING
    )

    with pytest.raises(ValueError, match="cancellation refund and disposition"):
        derive_customer_milestone(
            [
                customer_progress(
                    vendor_state=VendorPreparationState.CANCELLED, cancelled=True
                )
            ]
        )


def test_customer_milestone_is_derived_and_cannot_be_mutated_or_transitioned() -> None:
    progress = customer_progress()
    with pytest.raises(FrozenInstanceError):
        progress.payment_state = PaymentAttemptState.FAILED  # type: ignore[misc]

    assert all(
        not isinstance(rule.to_state, CustomerMilestone)
        for rule, _ in iter_transition_edges()
    )
    assert "customer_milestone" not in {machine.value for machine in StateMachine}


@pytest.mark.parametrize(
    "progresses",
    [
        [],
        [
            customer_progress(
                payment_state=PaymentAttemptState.PENDING,
                vendor_state=VendorPreparationState.PREPARING,
            )
        ],
        [
            customer_progress(
                inbound_state=InboundState.NOT_REQUESTED, hub_state=HubState.RECEIVED
            )
        ],
        [
            customer_progress(
                vendor_state=VendorPreparationState.READY_FOR_INBOUND,
                inbound_state=InboundState.IN_TRANSIT,
                outbound_state=OutboundState.DELIVERED,
            )
        ],
    ],
)
def test_empty_unpaid_or_impossible_customer_snapshots_fail_closed(progresses) -> None:
    with pytest.raises(ValueError):
        derive_customer_milestone(progresses)
