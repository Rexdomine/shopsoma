"""Deterministic, bounded PostgreSQL order-workflow classification."""

from dataclasses import dataclass
import hashlib
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Engine


class ClassificationConflict(RuntimeError):
    """An immutable prior classification differs from the rerun candidate."""


class ClassificationIncomplete(RuntimeError):
    """The exact order/classification/owner reconciliation is not complete."""


@dataclass(frozen=True)
class ClassificationRunIdentity:
    compatibility_writer_release_id: str
    migration_revision: str
    deployment_identity: str


@dataclass(frozen=True)
class ClassificationEvidence:
    compatibility_release_id: str | None = None
    deployment_identity: str | None = None
    bridge_evidence_reference: str | None = None
    original_owner_reference: str | None = None


@dataclass(frozen=True)
class ClassificationCandidate:
    order_id: str
    cohort: str
    policy_version: str
    access_mode: str
    evidence_kind: str
    evidence_reference: str
    notes_hash: str


def classify_historical_order(
    order_id: str, evidence: ClassificationEvidence
) -> ClassificationCandidate:
    """Classify from positive evidence; ambiguity is explicitly quarantined."""

    positive_reference = evidence.bridge_evidence_reference
    evidence_kind = "positive_release_or_bridge_evidence"
    if (
        not positive_reference
        and evidence.compatibility_release_id
        and evidence.deployment_identity
    ):
        positive_reference = (
            f"{evidence.compatibility_release_id}:{evidence.deployment_identity}"
        )
    if not positive_reference and evidence.original_owner_reference:
        positive_reference = evidence.original_owner_reference
        evidence_kind = "positive_original_owner_evidence"
    if positive_reference:
        values = (
            "legacy_pre_bridge",
            "legacy_pre_bridge_v1",
            "authenticated",
            evidence_kind,
            positive_reference,
        )
    else:
        values = (
            "legacy_ambiguous_quarantined",
            "legacy_quarantine_v1",
            "legacy_quarantined",
            "migration_ambiguity_quarantine",
            "historical-evidence-unresolved",
        )
    notes_hash = hashlib.sha256("|".join((str(order_id), *values)).encode()).hexdigest()
    return ClassificationCandidate(str(order_id), *values, notes_hash)


def reconcile_candidate(
    existing: ClassificationCandidate, candidate: ClassificationCandidate
) -> ClassificationCandidate:
    """Permit exact replay and abort any changed immutable candidate."""

    if existing != candidate:
        raise ClassificationConflict("changed workflow classification candidate")
    return existing


def start_workflow_classification_run(
    engine: Engine, identity: ClassificationRunIdentity
) -> uuid.UUID:
    """Create one stable run and atomically freeze its database-observed watermark."""

    parameters = {
        "release": identity.compatibility_writer_release_id,
        "revision": identity.migration_revision,
        "deployment": identity.deployment_identity,
    }
    with engine.begin() as connection:
        # INSERT takes ROW EXCLUSIVE. This lock closes the pre-writer INSERT race while
        # the run row becomes visible and its immutable watermark is captured.
        connection.execute(text("LOCK TABLE orders IN SHARE ROW EXCLUSIVE MODE"))
        connection.execute(
            text(
                "LOCK TABLE order_workflow_migration_runs "
                "IN SHARE ROW EXCLUSIVE MODE"
            )
        )
        existing = connection.execute(
            text(
                "SELECT id,high_watermark_created_at,high_watermark_order_id "
                "FROM order_workflow_migration_runs "
                "WHERE compatibility_writer_release_id=:release "
                "AND migration_revision=:revision "
                "AND deployment_identity=:deployment FOR UPDATE"
            ),
            parameters,
        ).one_or_none()
        if existing is not None:
            if existing.high_watermark_created_at is None:
                raise ClassificationConflict(
                    "classification run has no frozen watermark"
                )
            return existing.id
        if connection.scalar(
            text("SELECT EXISTS(SELECT 1 FROM order_workflow_migration_runs)")
        ):
            raise ClassificationConflict(
                "a different workflow classification run exists"
            )

        watermark = connection.execute(
            text(
                "SELECT created_at,id FROM orders "
                "ORDER BY created_at DESC,id DESC LIMIT 1"
            )
        ).one_or_none()
        run_id = uuid.uuid4()
        connection.execute(
            text(
                "INSERT INTO order_workflow_migration_runs "
                "(id,compatibility_writer_release_id,compatibility_writer_started_at,"
                "migration_revision,deployment_identity,high_watermark_created_at,"
                "high_watermark_order_id) VALUES "
                "(:id,:release,statement_timestamp(),:revision,:deployment,"
                "COALESCE(:watermark_created_at,'-infinity'::timestamptz),"
                "COALESCE(:watermark_order_id,'00000000-0000-0000-0000-000000000000'::uuid))"
            ),
            {
                **parameters,
                "id": run_id,
                "watermark_created_at": watermark.created_at if watermark else None,
                "watermark_order_id": watermark.id if watermark else None,
            },
        )
        return run_id


def _candidate_from_row(row) -> ClassificationCandidate:
    bridge_reference = (
        f"payment_attempt:{row.bridge_attempt_id}" if row.bridge_attempt_id else None
    )
    owner_reference = (
        f"original_owner:{row.customer_id}" if row.pre_writer_owner else None
    )
    return classify_historical_order(
        str(row.id),
        ClassificationEvidence(
            bridge_evidence_reference=bridge_reference,
            original_owner_reference=owner_reference,
        ),
    )


def classify_workflow_batch(
    engine: Engine, run_id: uuid.UUID, *, batch_size: int
) -> int:
    """Commit one ordered, bounded, lock-skipping historical batch."""

    if not 1 <= batch_size <= 10_000:
        raise ValueError("batch_size must be between 1 and 10000")
    with engine.begin() as connection:
        run = connection.execute(
            text(
                "SELECT id,compatibility_writer_started_at,high_watermark_created_at,"
                "high_watermark_order_id,classification_cutover_at "
                "FROM order_workflow_migration_runs WHERE id=:run"
            ),
            {"run": run_id},
        ).one_or_none()
        if run is None or run.high_watermark_created_at is None:
            raise ClassificationConflict("classification run is missing or unfrozen")
        if run.classification_cutover_at is not None:
            return 0
        if connection.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM orders WHERE "
                "(created_at,id)<=(:created_at,:order_id) AND "
                "((workflow_cohort IS NULL)::int+"
                "(workflow_policy_version IS NULL)::int+"
                "(checkout_access_mode IS NULL)::int) IN (1,2))"
            ),
            {
                "created_at": run.high_watermark_created_at,
                "order_id": run.high_watermark_order_id,
            },
        ):
            raise ClassificationConflict("partial workflow classification candidate")

        rows = connection.execute(
            text(
                "SELECT o.id,o.customer_id,"
                "(owner.order_id IS NOT NULL AND "
                " owner.created_at<:writer_started_at) AS pre_writer_owner,"
                "(SELECT pa.id FROM payment_attempts pa WHERE pa.order_id=o.id "
                " ORDER BY pa.created_at,pa.id LIMIT 1) AS bridge_attempt_id "
                "FROM orders o "
                "LEFT JOIN order_current_owners owner ON owner.order_id=o.id "
                "WHERE (o.created_at,o.id)<=(:created_at,:order_id) "
                "AND o.workflow_cohort IS NULL "
                "AND o.workflow_policy_version IS NULL "
                "AND o.checkout_access_mode IS NULL "
                "ORDER BY o.created_at,o.id LIMIT :batch_size "
                "FOR UPDATE OF o SKIP LOCKED"
            ),
            {
                "writer_started_at": run.compatibility_writer_started_at,
                "created_at": run.high_watermark_created_at,
                "order_id": run.high_watermark_order_id,
                "batch_size": batch_size,
            },
        ).all()
        for row in rows:
            candidate = _candidate_from_row(row)
            connection.execute(
                text(
                    "INSERT INTO order_workflow_classifications "
                    "(order_id,cohort,policy_version,access_mode,evidence_kind,"
                    "evidence_reference,migration_run_id,classified_by,notes_hash) VALUES "
                    "(:order_id,:cohort,:policy_version,:access_mode,:evidence_kind,"
                    ":evidence_reference,:run,'milestone_2_backfill',:notes_hash) "
                    "ON CONFLICT(order_id) DO NOTHING"
                ),
                {**candidate.__dict__, "run": run_id},
            )
            existing_row = connection.execute(
                text(
                    "SELECT order_id,cohort,policy_version,access_mode,evidence_kind,"
                    "evidence_reference,notes_hash FROM order_workflow_classifications "
                    "WHERE order_id=:order_id"
                ),
                {"order_id": row.id},
            ).one()
            existing = ClassificationCandidate(
                str(existing_row.order_id),
                existing_row.cohort,
                existing_row.policy_version,
                existing_row.access_mode,
                existing_row.evidence_kind,
                existing_row.evidence_reference,
                existing_row.notes_hash,
            )
            reconcile_candidate(existing, candidate)
            connection.execute(
                text(
                    "UPDATE orders SET workflow_cohort=:cohort,"
                    "workflow_policy_version=:policy_version,"
                    "checkout_access_mode=:access_mode WHERE id=:order_id"
                ),
                candidate.__dict__,
            )
            connection.execute(
                text(
                    "INSERT INTO order_current_owners(order_id,original_customer_id) "
                    "VALUES (:order_id,:customer_id) ON CONFLICT(order_id) DO NOTHING"
                ),
                {"order_id": row.id, "customer_id": row.customer_id},
            )
            projected_customer = connection.scalar(
                text(
                    "SELECT original_customer_id FROM order_current_owners "
                    "WHERE order_id=:order_id"
                ),
                {"order_id": row.id},
            )
            if projected_customer != row.customer_id:
                raise ClassificationConflict("changed original owner projection")
        return len(rows)


def finalize_workflow_classification(engine: Engine, run_id: uuid.UUID) -> int:
    """Reconcile exact totals and record cutover, or fail without mutation."""

    with engine.begin() as connection:
        run = connection.execute(
            text(
                "SELECT id,high_watermark_created_at,high_watermark_order_id,"
                "classification_cutover_at,classified_row_count "
                "FROM order_workflow_migration_runs WHERE id=:run FOR UPDATE"
            ),
            {"run": run_id},
        ).one_or_none()
        if run is None or run.high_watermark_created_at is None:
            raise ClassificationConflict("classification run is missing or unfrozen")
        totals = connection.execute(
            text(
                "SELECT "
                "(SELECT count(*) FROM orders) AS orders_count,"
                "(SELECT count(*) FROM order_workflow_classifications) AS evidence_count,"
                "(SELECT count(*) FROM orders o LEFT JOIN order_workflow_classifications c "
                " ON c.order_id=o.id WHERE c.order_id IS NULL OR "
                " o.workflow_cohort IS DISTINCT FROM c.cohort OR "
                " o.workflow_policy_version IS DISTINCT FROM c.policy_version OR "
                " o.checkout_access_mode IS DISTINCT FROM c.access_mode) AS truth_mismatch,"
                "(SELECT count(*) FROM order_workflow_classifications c LEFT JOIN orders o "
                " ON o.id=c.order_id WHERE o.id IS NULL) AS extra_evidence,"
                "(SELECT count(*) FROM orders o LEFT JOIN order_current_owners owner "
                " ON owner.order_id=o.id WHERE owner.order_id IS NULL OR "
                " owner.original_customer_id IS DISTINCT FROM o.customer_id) AS owner_mismatch,"
                "(SELECT count(*) FROM orders o LEFT JOIN order_workflow_classifications c "
                " ON c.order_id=o.id WHERE (o.created_at,o.id)<=(:created_at,:order_id) "
                " AND c.order_id IS NULL) AS watermark_missing"
            ),
            {
                "created_at": run.high_watermark_created_at,
                "order_id": run.high_watermark_order_id,
            },
        ).one()
        if (
            totals.orders_count != totals.evidence_count
            or totals.truth_mismatch
            or totals.extra_evidence
            or totals.owner_mismatch
            or totals.watermark_missing
        ):
            raise ClassificationIncomplete(
                "workflow classification reconciliation incomplete"
            )
        if run.classification_cutover_at is not None:
            if run.classified_row_count != totals.evidence_count:
                raise ClassificationConflict("recorded classification total changed")
            return totals.evidence_count
        connection.execute(
            text(
                "UPDATE order_workflow_migration_runs SET "
                "classification_cutover_at=statement_timestamp(),"
                "classified_row_count=:count,"
                "validated_constraints='exact order/classification/owner reconciliation' "
                "WHERE id=:run"
            ),
            {"run": run_id, "count": totals.evidence_count},
        )
        return totals.evidence_count
