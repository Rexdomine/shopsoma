from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import uuid


ROOT = Path(__file__).parents[1]
SCRIPT_PATH = ROOT / "run_checkout_prerequisite_deploy.py"


def _load_module():
    spec = spec_from_file_location("checkout_prerequisite_deploy", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deploy_entrypoint_runs_staged_upgrade_then_classification_then_heads(monkeypatch):
    module = _load_module()
    calls = []
    run_id = uuid.uuid4()

    class Engine:
        def dispose(self):
            calls.append(("dispose",))

    engine = Engine()
    expected_engine_url = module._sync_database_url(
        "postgresql+asyncpg://user:pass@localhost/db"
    )

    class LockContext:
        def __enter__(self):
            calls.append(("lock_enter",))
            return "LOCKED-CONNECTION"
        def __exit__(self, exc_type, exc, tb):
            calls.append(("lock_exit",))

    monkeypatch.setattr(module.command, "upgrade", lambda config, revision: calls.append(("upgrade", revision, config.attributes.get("connection"))))
    monkeypatch.setattr(module, "create_engine", lambda url: calls.append(("create_engine", url)) or engine)
    monkeypatch.setattr(module, "_cutover_already_complete", lambda _engine: False)
    monkeypatch.setattr(module, "_hold_cutover_validation_lock", lambda _engine: LockContext())
    monkeypatch.setattr(module, "start_workflow_classification_run", lambda _engine, identity: calls.append(("start", identity.migration_revision)) or run_id)

    batches = iter([2, 1, 0])
    monkeypatch.setattr(module, "classify_workflow_batch", lambda _engine, seen_run_id, batch_size: calls.append(("batch", seen_run_id, batch_size)) or next(batches))
    monkeypatch.setattr(module, "finalize_workflow_classification", lambda _engine, seen_run_id: calls.append(("finalize", seen_run_id)) or 3)

    module.run(database_url="postgresql+asyncpg://user:pass@localhost/db", batch_size=250)

    assert calls == [
        ("upgrade", module.PREPARE_REVISION, None),
        ("create_engine", expected_engine_url),
        ("start", module.VALIDATE_REVISION),
        ("batch", run_id, 250),
        ("batch", run_id, 250),
        ("batch", run_id, 250),
        ("lock_enter",),
        ("finalize", run_id),
        ("upgrade", "heads", "LOCKED-CONNECTION"),
        ("lock_exit",),
        ("dispose",),
    ]


def test_deploy_entrypoint_skips_classification_after_recorded_cutover(monkeypatch):
    module = _load_module()
    calls = []

    class Engine:
        def dispose(self):
            calls.append(("dispose",))

    engine = Engine()
    expected_engine_url = module._sync_database_url(
        "postgresql+asyncpg://user:pass@localhost/db"
    )

    monkeypatch.setattr(module.command, "upgrade", lambda config, revision: calls.append(("upgrade", revision, config.attributes.get("connection"))))
    monkeypatch.setattr(module, "create_engine", lambda url: calls.append(("create_engine", url)) or engine)
    monkeypatch.setattr(module, "_cutover_already_complete", lambda _engine: True)
    monkeypatch.setattr(module, "start_workflow_classification_run", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("classification must be skipped after cutover")))
    monkeypatch.setattr(module, "classify_workflow_batch", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("classification batches must be skipped after cutover")))
    monkeypatch.setattr(module, "finalize_workflow_classification", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("finalize must be skipped after cutover")))

    module.run(database_url="postgresql+asyncpg://user:pass@localhost/db", batch_size=250)

    assert calls == [
        ("upgrade", module.PREPARE_REVISION, None),
        ("create_engine", expected_engine_url),
        ("dispose",),
        ("upgrade", "heads", None),
    ]
