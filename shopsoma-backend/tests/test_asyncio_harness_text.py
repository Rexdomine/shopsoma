from pathlib import Path


ROOT = Path(__file__).parents[1]
PYTEST_INI = ROOT / "pytest.ini"
CONFTEST = ROOT / "tests" / "conftest.py"


def test_pytest_asyncio_auto_mode_has_no_custom_event_loop_fixture() -> None:
    pytest_source = " ".join(PYTEST_INI.read_text().split())
    conftest_source = CONFTEST.read_text()

    assert "asyncio_mode = auto" in pytest_source
    assert "asyncio_default_fixture_loop_scope = function" in pytest_source
    assert "def event_loop(" not in conftest_source
