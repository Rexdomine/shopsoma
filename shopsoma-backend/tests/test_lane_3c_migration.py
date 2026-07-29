"""Migration graph, source contract, and real cycle for Lane 2A-3C persistence."""

import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REVISION = "a4e6c8f1b3d5"
PARENT = "9d3e5f7a1b2c"


def _scripts() -> ScriptDirectory:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(config)


def test_lane_3c_has_linear_lane_3d_and_phase_2b_descendants() -> None:
    scripts = _scripts()
    assert scripts.get_heads() == ["e8c0a2d4f6b8"]
    assert scripts.get_revision("e8c0a2d4f6b8").down_revision == "d7b9f1c3e5a8"
    assert scripts.get_revision(REVISION).down_revision == PARENT
    assert scripts.get_revision("b5f7d9a2c4e6").down_revision == REVISION
    assert scripts.get_revision("c6a8e0f2b4d7").down_revision == "b5f7d9a2c4e6"
    assert scripts.get_revision("d7b9f1c3e5a8").down_revision == "c6a8e0f2b4d7"


def test_lane_3c_migration_is_additive_symmetric_private_and_narrow() -> None:
    revision = _scripts().get_revision(REVISION)
    assert revision is not None
    source = Path(revision.path).read_text()
    tables = (
        "hub_receipt_sessions",
        "hub_receipt_items",
        "hub_discrepancies",
        "hub_qc_sessions",
        "hub_qc_inspections",
        "hub_evidence",
        "hub_evidence_retention_events",
        "hub_remediations",
    )
    assert source.count("op.create_table(") == len(tables)
    for table in tables:
        assert f'"{table}"' in source
        assert f'op.drop_table("{table}")' in source
    assert '"uq_inbound_transfers_hub_identity"' in source
    assert "FOR UPDATE" in source
    assert "CREATE TRIGGER" in source
    assert "DROP TRIGGER IF EXISTS" in source
    assert "validate_hub_evidence_retention_event" in source
    assert "validate_hub_evidence_insert" in source
    assert "validate_hub_evidence_update" in source
    assert "pg_trigger_depth()" in source
    for required in (
        "receipt session identity is immutable",
        "approved remediation terms and audit are immutable",
        "illegal remediation state transition",
        "retention event previous state is stale",
        "evidence policy changes require a retention event",
        "hub_evidence_retention_events_update_restricted",
        "tr_{table}_delete_restricted",
        "retention_policy_updated_at",
        "approval timestamp must follow creation and not be future-dated",
        "completion timestamp must follow approval and not be future-dated",
        "event timestamp must follow evidence creation and not be future-dated",
        "evidence timestamps cannot be future-dated",
        "evidence cannot predate its subject",
        "retention event timestamps must strictly increase",
        "receipt sessions must start incomplete",
        "receipt completion requires receipt items",
        "receipt completion requires every transfer allocation to be reconciled",
        "CREATE OR REPLACE FUNCTION validate_inbound_transfer_item_quantity()",
        "inbound transfer allocations are frozen after receipt completion",
        "PERFORM 1 FROM inbound_transfers",
        "QC sessions must start incomplete",
        "BEFORE INSERT OR UPDATE ON hub_receipt_sessions",
        "BEFORE INSERT OR UPDATE ON hub_qc_sessions",
        "received quantity cannot drop below inspected quantity",
        "NEW.scan_identity IS DISTINCT FROM OLD.scan_identity",
        "remediated inspections are immutable",
        "validate_hub_discrepancy_insert",
        "tr_hub_discrepancies_receipt_open",
        "QC completion requires evidence for every inspection",
        "remediation completion requires evidence",
        "inspections require QC in progress",
        "receipt completion timestamp cannot be future-dated",
        "QC completion timestamp cannot be future-dated",
        "state <> 'completed' AND completed_at IS NULL",
        "remediations must start pending",
        "remediation approval must follow QC completion",
        "reinspection must start after remediation completion",
        "PERFORM 1 FROM hub_remediations",
        "remediation.failed_inspection_id = inspection.id",
        "every failed inspection requires completed remediation before reinspection",
        "NEW.started_at IS DISTINCT FROM OLD.started_at",
        'sa.Column("source_command", sa.String(length=100), nullable=False)',
        'sa.Column("idempotency_key", sa.String(length=200), nullable=False)',
        "ck_hub_qc_sessions_command_identity_canonical",
        "uq_hub_qc_sessions_idempotency",
        "NEW.source_command IS DISTINCT FROM OLD.source_command",
        "NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key",
        "illegal QC state transition",
        "terminal QC state requires completion",
        "QC sessions must start pending or in progress",
        "QC sessions require a completed receipt session",
        "QC start must follow receipt completion",
        "item.received_quantity > 0",
        'sa.Column("started_at", sa.DateTime(timezone=True), nullable=False)',
        "QC completion must follow receipt completion",
        "QC completion requires inspection timestamps within the session",
        "inspection timestamp must fall within the active QC session",
        "state IN ('qc_pending', 'qc_in_progress', 'qc_passed', 'qc_failed')",
        "receipt quantity is frozen after discrepancy",
        "WHERE id = NEW.receipt_item_id AND receipt_session_id = NEW.receipt_session_id",
        "QC completion requires a terminal state",
        "QC completion requires a completed receipt session",
        "passed QC completion requires all receipt items to pass",
        "failed QC completion requires a failed or rejected inspection",
        "remediation approval requires a completed failed QC session",
    ):
        assert required in source
    lowered = source.lower()
    for forbidden in (
        "dhl",
        "credential",
        "public_url",
        "upload_url",
        "signed_url",
        "file_data",
        "package_composition",
        "seal_number",
        "custody_event",
    ):
        assert forbidden not in lowered


def test_hub_timestamp_triggers_have_exact_model_migration_parity() -> None:
    revision = _scripts().get_revision(REVISION)
    assert revision is not None
    migration_source = Path(revision.path).read_text()
    model_source = (BACKEND_ROOT / "app/models/hub_quality.py").read_text()
    functions = (
        "reject_completed_hub_receipt_update",
        "reject_completed_hub_qc_update",
        "validate_hub_discrepancy_insert",
        "validate_hub_remediation_invariants",
        "validate_hub_qc_reinspection_lineage",
        "validate_hub_evidence_insert",
    )

    def trigger_tokens(source: str, function: str) -> list[str]:
        markers = (
            f"CREATE FUNCTION {function}() RETURNS trigger AS $$",
            f"CREATE OR REPLACE FUNCTION {function}() RETURNS trigger AS $$",
        )
        marker = next(candidate for candidate in markers if candidate in source)
        body = source.split(marker, 1)[1].split("END; $$ LANGUAGE plpgsql", 1)[0]
        return re.findall(
            r"'[^']*'|[A-Za-z_][A-Za-z0-9_]*|<>|<=|>=|:=|[(),.;=<>]",
            body,
        )

    for function in functions:
        assert trigger_tokens(model_source, function) == trigger_tokens(
            migration_source, function
        )


def test_hub_timestamp_defaults_have_exact_model_migration_parity() -> None:
    revision = _scripts().get_revision(REVISION)
    assert revision is not None
    migration_source = Path(revision.path).read_text()
    from app.models.hub_quality import (
        HubDiscrepancy,
        HubEvidence,
        HubQCInspection,
        HubQCSession,
        HubReceiptItem,
        HubReceiptSession,
        HubRemediation,
    )

    surfaces = {
        "hub_receipt_sessions": (HubReceiptSession, ("created_at", "updated_at")),
        "hub_receipt_items": (HubReceiptItem, ("created_at", "updated_at")),
        "hub_discrepancies": (HubDiscrepancy, ("recorded_at",)),
        "hub_qc_sessions": (HubQCSession, ("created_at", "updated_at")),
        "hub_qc_inspections": (
            HubQCInspection,
            ("inspected_at", "created_at", "updated_at"),
        ),
        "hub_evidence": (
            HubEvidence,
            ("retention_policy_updated_at", "created_at"),
        ),
        "hub_remediations": (HubRemediation, ("created_at", "updated_at")),
    }
    for table, (model, columns) in surfaces.items():
        table_source = migration_source.split(
            f'op.create_table(\n        "{table}"', 1
        )[1]
        table_source = table_source.split("\n    )", 1)[0]
        for column in columns:
            assert (
                str(model.__table__.c[column].server_default.arg)
                == "statement_timestamp()"
            )
            column_pattern = re.compile(
                rf'sa\.Column\(\s*"{column}".*?'
                r'server_default=sa\.text\("statement_timestamp\(\)"\).*?\),',
                re.DOTALL,
            )
            assert column_pattern.search(table_source), (table, column)


def test_lane_3c_real_hermetic_postgresql_migration_cycle() -> None:
    """Exercise both directions on a fresh database that is always destroyed."""
    config_spec = importlib.util.spec_from_file_location(
        "lane3c_test_config", BACKEND_ROOT / "tests/conftest.py"
    )
    assert config_spec is not None and config_spec.loader is not None
    test_config = importlib.util.module_from_spec(config_spec)
    config_spec.loader.exec_module(test_config)

    base_url = make_url(test_config.TEST_DATABASE_URL)
    sync_driver = base_url.drivername.split("+", 1)[0]
    admin_url = base_url.set(drivername=sync_driver, database="postgres")
    database = f"lane3c_cycle_{uuid.uuid4().hex}"
    database_url = base_url.set(
        drivername=sync_driver, database=database
    ).render_as_string(hide_password=False)
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database}"'))
        env = os.environ.copy()
        env.update(DATABASE_URL=database_url, SECRET_KEY="lane3c-migration-test-secret")

        def migrate(command: str, revision: str) -> None:
            result = subprocess.run(
                [sys.executable, "-m", "alembic", command, revision],
                cwd=BACKEND_ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            target = create_engine(database_url)
            try:
                with target.connect() as connection:
                    current = connection.scalar(
                        text("SELECT version_num FROM alembic_version")
                    )
                assert current == revision
            finally:
                target.dispose()

        migrate("upgrade", PARENT)
        sentinel_id = uuid.uuid4()
        sentinel_key = f"lane3c-existing-{uuid.uuid4().hex}"
        target = create_engine(database_url)
        try:
            with target.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO app_settings (id, key, value) "
                        "VALUES (:id, :key, :value)"
                    ),
                    {"id": sentinel_id, "key": sentinel_key, "value": "preexisting"},
                )
        finally:
            target.dispose()

        def assert_preexisting_snapshot_readable() -> None:
            target = create_engine(database_url)
            try:
                with target.connect() as connection:
                    value = connection.scalar(
                        text("SELECT value FROM app_settings WHERE id = :id"),
                        {"id": sentinel_id},
                    )
                assert value == "preexisting"
            finally:
                target.dispose()

        migrate("upgrade", REVISION)
        assert_preexisting_snapshot_readable()
        migrate("downgrade", PARENT)
        assert_preexisting_snapshot_readable()
        migrate("upgrade", REVISION)
        assert_preexisting_snapshot_readable()
    finally:
        try:
            with admin.connect() as connection:
                connection.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :database AND pid <> pg_backend_pid()"
                    ),
                    {"database": database},
                )
                connection.execute(text(f'DROP DATABASE IF EXISTS "{database}"'))
        finally:
            admin.dispose()
