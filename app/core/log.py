"""The session log is one file beside the database, the previous session kept beside it.

Actions are logged at the service boundary through @logged.
It should never be done inside the document engine itself.

A log serves the purpose of debugging user-installed app. It should only 
record ids, counts and diagnostic codes; no user-provided data, e.g. names, 
addresses, descriptions etc.
"""

from __future__ import annotations

import functools
import inspect
import logging
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

from app.core.diagnostics import DiagnosticCollector
from app.core.errors import AppError

P = ParamSpec("P")
R = TypeVar("R")

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
HANDLER_NAME = "plater_session"

# @logged picks from a call's arguments by default
_ARGUMENT_NAMES = frozenset({"version", "code", "document_type"})

# libraries whose INFO lines are noise in every session
_QUIET = ("alembic.runtime.plugins",)

log = logging.getLogger("plater")
_actions = logging.getLogger("plater.action")

type Details = Callable[[Any, Mapping[str, Any]], Mapping[str, object]]

def configure(path: Path, level: int = logging.INFO) -> None:
    """Start this session's log at `path`. The last session's file is kept as 
    <name>.prev.log, so a crash survives the restart that follow it.
    """

    path.parent.mkdir(parents=True, exist_ok=True)

    mode = "w"
    if path.exists():
        try:
            path.replace(previous_log(path))
        except OSError:     # in case of another running instance holds it open
            mode = "a"

    handler = logging.FileHandler(path, mode=mode, encoding="utf-8")
    handler.set_name(HANDLER_NAME)
    handler.setFormatter(logging.Formatter(FORMAT))

    root = logging.getLogger()
    for existing in [h for h in root.handlers if h.get_name() == HANDLER_NAME]:
        root.removeHandler(existing)
        existing.close()
    root.addHandler(handler)
    root.setLevel(level)

    for name in _QUIET:
        logging.getLogger(name).setLevel(logging.WARNING)

    sys.excepthook = _log_uncaught


def previous_log(path: Path) -> Path:
    return path.with_name(f"{path.stem}.prev{path.suffix}")


def logged(action: str, details: Details | None = None) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Record an action's outcome in one line, with how long it took.
    
    By default lines carry the call's ids. `details` replaces that with whatever 
    it picks from (result, arguments), and may set outcome to something other 
    than 'ok', which logs a warning.
    
    AppError is expected, one warning with its code. Anything else logs 
    the traceback. Either way the exception propagates.
    """

    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        signature = inspect.signature(function)

        @functools.wraps(function)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            arguments = signature.bind_partial(*args, **kwargs).arguments
            started = time.perf_counter()

            try:
                result = function(*args, **kwargs)
            except AppError as error:
                cause = error.context.get("cause")
                _actions.warning(
                    "%s failed in %s | %s", action, _elapsed(started),
                    _fields({**_ids(arguments), "code": error.code, "cause": cause})
                )
                raise
            except Exception:
                _actions.exception(
                    "%s crashed in %s | %s", action, _elapsed(started), _fields(_ids(arguments)),
                )
                raise

            fields = dict(details(result, arguments)) if details is not None \
                else {**_ids(arguments), **_result_id(result)}
            outcome = fields.pop("outcome", "ok")

            _actions.log(
                logging.INFO if outcome == "ok" else logging.WARNING,
                "%s %s in %s | %s", action, outcome, _elapsed(started), _fields(fields),
            )
            return result

        return wrapper

    return decorate


def diagnostic_codes(diagnostics: DiagnosticCollector | None) -> str | None:
    """Get the distinct codes. User messages may contain user-data thus not used."""

    if diagnostics is None:
        return None
    return ",".join(sorted({item.code for item in diagnostics.items})) or None


def _ids(arguments: Mapping[str, Any]) -> dict[str, object]:
    return {
        name: value
        for name, value in arguments.items()
        if (name.endswith("_id") or name in _ARGUMENT_NAMES)
            and isinstance(value, (int, str))
            and not isinstance(value, bool)
    }


def _result_id(result: object) -> dict[str, object]:
    if isinstance(result, int) and not isinstance(result, bool):
        return {"id": result}
    identifier = getattr(result, "id", None)
    return {"id": identifier} if isinstance(identifier, int) else {}


def _fields(fields: Mapping[str, object]) -> str:
    return " ".join(f"{name}={value}" for name, value in fields.items() if value is not None) \
        or "--"

def _elapsed(started: float) -> str:
    return f"{(time.perf_counter() - started) * 1000:.0f} ms"

def _log_uncaught(kind, value, traceback) -> None:
    """Windowed build has no console, so without this a crash leaves no trace. 
    PySide reports an exception that escapes a slot here too.
    """

    if not issubclass(kind, KeyboardInterrupt):
        log.critical("Unhandled exception", exc_info=(kind, value, traceback))
    if sys.stderr is not None:
        sys.__excepthook__(kind, value, traceback)