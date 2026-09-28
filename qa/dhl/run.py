"""CI-only supervisor. Never use this to start unmanaged Paperclip host services."""

import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from containment import verify
from sanitize import sanitize_reports

EVIDENCE = Path("/evidence")
REPORTS = Path("/tmp/dhl-reports")
BACKEND = Path("/target/shopsoma-backend")
FRONTEND = Path("/target/shopsoma-frontend")
results = {}
children = []


def command(name, args, cwd=BACKEND, timeout=300):
    # Logs stay inside the disposable container; upload only status and redacted reports.
    with open(f"/tmp/{name}.log", "w") as log:
        process = subprocess.Popen(
            args, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
        )
        children.append(process)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            code = process.wait(timeout=10)
            results[name] = {"exit": code, "timeout": True}
            raise RuntimeError(f"{name} exceeded its bound")
    results[name] = {"exit": code}
    if code and name in ("initdb", "postgres-start", "database"):
        # Bootstrap precedes application data and credentials. These logs hold
        # only init/start diagnostics for this disposable cluster.
        diagnostics = Path(f"/tmp/{name}.log").read_text()
        if name == "postgres-start" and Path("/tmp/postgres.log").exists():
            diagnostics += Path("/tmp/postgres.log").read_text()
        (EVIDENCE / "bootstrap-error.txt").write_text(diagnostics)
    (EVIDENCE / "checks.json").write_text(json.dumps(results, indent=2))
    return code == 0


def stop(_signum, _frame):
    raise SystemExit(143)


def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGALRM, stop)
    signal.alarm(1200)
    REPORTS.mkdir()
    # Before database creation, frontend build, importing application, or feature tests.
    (EVIDENCE / "containment.json").write_text(json.dumps(verify(), indent=2))
    os.environ["SECRET_KEY"] = secrets.token_hex(32)
    os.environ["DATABASE_URL"] = (
        "postgresql+asyncpg://qa:synthetic-ci-only@127.0.0.1:5432/shopsoma_test"
    )
    # Unique owned cluster; nothing is mounted from the runner or shared infrastructure.
    cluster = tempfile.TemporaryDirectory(prefix="rex70-pg-")
    started = False
    try:
        assert command(
            "initdb", ["initdb", "-D", cluster.name, "-A", "trust", "-U", "qa"]
        )
        assert command(
            "postgres-start",
            [
                "pg_ctl",
                "-D",
                cluster.name,
                "-l",
                "/tmp/postgres.log",
                "-o",
                f"-h 127.0.0.1 -p 5432 -k {cluster.name}",
                "-w",
                "start",
            ],
        )
        started = True
        assert command(
            "database", ["createdb", "-h", "127.0.0.1", "-U", "qa", "shopsoma_test"]
        )
        checks = [
            command(
                "frontend-tests",
                [
                    "npm",
                    "test",
                    "--",
                    "src/services/__tests__/adminDhlOperations.test.ts",
                    "src/pages/admin/AdminOrderDetail.test.tsx",
                    "--maxWorkers=1",
                    "--minWorkers=1",
                    "--reporter=junit",
                    "--outputFile=/tmp/dhl-reports/frontend.xml",
                ],
                FRONTEND,
            )
        ]
        checks.append(command("frontend-lint", ["npm", "run", "lint"], FRONTEND))
        built = command("frontend-build", ["npm", "run", "build"], FRONTEND)
        checks.append(built)
        checks.append(
            command(
                "backend-tests",
                [
                    "python",
                    "-m",
                    "pytest",
                    "tests/test_admin_orders.py",
                    "tests/test_dhl_operations.py",
                    "tests/test_dhl_phase4_booking.py",
                    "tests/test_dhl_phase4_static_contracts.py",
                    "--junitxml=/tmp/dhl-reports/backend.xml",
                    "--tb=short",
                ],
                timeout=480,
            )
        )
        if built:
            log = open("/tmp/frontend-server.log", "w")
            server = subprocess.Popen(
                [
                    "node",
                    "node_modules/vite/bin/vite.js",
                    "preview",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "5173",
                    "--strictPort",
                ],
                cwd=FRONTEND,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            children.append(server)
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError("Frontend terminated during startup")
                try:
                    with urlopen("http://127.0.0.1:5173", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Frontend startup deadline exceeded")
            checks.append(
                command(
                    "browser-tests",
                    [
                        "python",
                        "-m",
                        "pytest",
                        "-c",
                        "/harness/pytest.ini",
                        "/harness/test_browser.py",
                        "--junitxml=/tmp/dhl-reports/browser.xml",
                    ],
                    timeout=480,
                )
            )
        return 0 if all(checks) else 1
    finally:
        stopped = True
        for process in reversed(children):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                    stopped = False
        if started:
            stopped = (
                command(
                    "postgres-stop",
                    ["pg_ctl", "-D", cluster.name, "-m", "fast", "-w", "stop"],
                )
                and stopped
            )
        cluster.cleanup()
        (EVIDENCE / "teardown.json").write_text(
            json.dumps(
                {
                    "supervised_processes_stopped": stopped,
                    "owned_cluster_removed": not Path(cluster.name).exists(),
                    "worker_or_beat_started": False,
                }
            )
        )
        # Raw reports never enter the upload directory, even after a crash or
        # interrupted teardown. Publish only after successful sanitization.
        sanitize_reports(REPORTS)
        for report in REPORTS.glob("*.xml"):
            shutil.copyfile(report, EVIDENCE / report.name)
        if not stopped:
            raise RuntimeError("Teardown required forced termination")


if __name__ == "__main__":
    sys.exit(main())
