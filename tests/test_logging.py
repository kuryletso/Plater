"""The session log: one file beside the database, the previous session kept beside it,
and ids, counts and codes only — a log is what a user sends when something breaks."""

import logging
import sys

import pytest

@pytest.fixture
def restore_logging():
    """configure() adds a handler to the root logger and replaces sys.excepthook."""

    root = logging.getLogger()
    handlers, level, hook = list(root.handlers), root.level, sys.excepthook
    yield
    for handler in [h for h in root.handlers if h not in handlers]:
        root.removeHandler(handler)
        handler.close()
    root.setLevel(level)
    sys.excepthook = hook


def plater_records(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name.startswith("plater")]


# --- the file ----------------------------------------------------------------

def test_a_session_starts_a_fresh_log_and_keeps_the_previous_one(tmp_path, restore_logging):
    """Rewritten each session, but a crash must survive the restart that follows it."""
    from app.core.log import configure

    path = tmp_path / "plater.log"
    path.write_text("the session that crashed\n", encoding="utf-8")

    configure(path)
    logging.getLogger("plater").info("a new session")

    current = path.read_text(encoding="utf-8")
    assert "the session that crashed" in (tmp_path / "plater.prev.log").read_text(encoding="utf-8")
    assert "a new session" in current
    assert "the session that crashed" not in current


def test_configuring_twice_writes_each_line_once(tmp_path, restore_logging):
    from app.core.log import configure

    path = tmp_path / "plater.log"
    configure(path)
    configure(path)
    logging.getLogger("plater").info("only once")

    assert path.read_text(encoding="utf-8").count("only once") == 1


def test_the_log_lives_beside_the_database_unless_plater_log_says_otherwise(monkeypatch, tmp_path):
    from app.paths import log_path, user_data_dir

    monkeypatch.delenv("PLATER_LOG", raising=False)
    assert log_path() == user_data_dir() / "plater.log"

    monkeypatch.setenv("PLATER_LOG", str(tmp_path / "elsewhere.log"))
    assert log_path() == tmp_path / "elsewhere.log"


def test_migrations_leave_the_session_log_alone():
    """alembic/env.py calls fileConfig(), which removes the root logger's handlers
    and disables existing loggers. The app's own Alembic config switches it off."""
    from app.db.session import _alembic_config

    assert _alembic_config().attributes.get("configure_logger") is False


# --- crashes -----------------------------------------------------------------

def test_a_crash_reaches_the_log_even_without_a_console(tmp_path, restore_logging, monkeypatch):
    """A windowed build has sys.stderr = None, so the log is the only witness."""
    from app.core.log import configure

    path = tmp_path / "plater.log"
    configure(path)
    monkeypatch.setattr(sys, "stderr", None)

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())

    text = path.read_text(encoding="utf-8")
    assert "Unhandled exception" in text
    assert "RuntimeError: boom" in text


# --- @logged ------------------------------------------------------------------

def test_an_action_logs_one_line_with_its_ids_and_nothing_else(caplog):
    from app.core.log import logged

    @logged("thing.save")
    def save(template_id: int, name: str, amount: float) -> int:
        return 7

    caplog.set_level(logging.INFO, logger="plater")
    save(3, "Acme Ltd", 1250.0)

    (record,) = plater_records(caplog)
    message = record.getMessage()
    assert record.levelno == logging.INFO
    assert message.startswith("thing.save ok in ")
    assert "template_id=3" in message and "id=7" in message
    assert "Acme" not in message and "1250" not in message


def test_an_expected_error_logs_its_code_without_a_traceback(caplog):
    """The user is told about it already; one line is enough."""
    from app.core.log import logged
    from app.services.errors import InvalidSelection

    @logged("thing.save")
    def save(template_id: int) -> None:
        raise InvalidSelection("prefix taken", code="prefix_clash", user_message="Taken.")

    caplog.set_level(logging.INFO, logger="plater")
    with pytest.raises(InvalidSelection):
        save(3)

    (record,) = plater_records(caplog)
    assert record.levelno == logging.WARNING
    assert "thing.save failed" in record.getMessage()
    assert "code=prefix_clash" in record.getMessage()
    assert record.exc_info is None


def test_an_unexpected_error_logs_its_traceback(caplog):
    from app.core.log import logged

    @logged("thing.save")
    def save(template_id: int) -> None:
        raise ZeroDivisionError("a bug")

    caplog.set_level(logging.INFO, logger="plater")
    with pytest.raises(ZeroDivisionError):
        save(3)

    (record,) = plater_records(caplog)
    assert record.levelno == logging.ERROR
    assert "thing.save crashed" in record.getMessage()
    assert record.exc_info is not None


def test_a_decorated_method_keeps_its_signature():
    """Pylance and the GUI rely on the real parameters, not *args/**kwargs."""
    import inspect

    from app.services.template.repository import TemplateRepository

    assert list(inspect.signature(TemplateRepository.copy).parameters) == ["self", "template_id", "name"]
    assert hasattr(TemplateRepository.copy, "__wrapped__")


def test_alembic_plugin_setup_is_quiet(tmp_path, restore_logging):
    """Alembic logs six "setup plugin" lines at INFO on every launch."""
    from app.core.log import configure

    configure(tmp_path / "plater.log")

    assert logging.getLogger("alembic.runtime.plugins").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("alembic.runtime.migration").getEffectiveLevel() == logging.INFO, \
        "the migration lines stay: they say which schema the session started on"
