from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from enum import StrEnum

from app.core.messages import fill, literal

if TYPE_CHECKING:
    from app.core.diagnostics import Diagnostic


class Severity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class Layer(StrEnum):
    PARSER = "parser"
    NORMALIZATION = "normalization"
    BLUEPRINT = "blueprint"
    RENDER = "render"
    PERSISTENCE = "persistence"     # CRUD
    ORCHESTRATION = "orchestration"
    UI = "ui"


class ErrorCategory(StrEnum):
    FORMAT = "format"
    SECURITY = "security"
    UNSUPPORTED = "unsupported"
    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    USAGE = "usage"     # developer error
    INTERNAL = "internal"


class AppError(Exception):
    layer: ClassVar[Layer]
    category: ClassVar[ErrorCategory] = ErrorCategory.INTERNAL
    recoverable: ClassVar[bool] = False

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        user_message: str | None = None,
        context: dict | None = None,
    ) -> None:
        """`message` is for developer and the traceback. It defaults to the user message.
        Meanwhile `user_message` is a template marked with QT_TRANSLATE_NOOP (app/core/messages.py), 
        filled from `context`.
        """

        self.code = code or type(self).__name__
        self.user_message = user_message        # if None, internal-only
        self.context = context or {}
        
        super().__init__(message if message is not None else self.user_text or self.code)


    @property
    def user_text(self) -> str | None:
        """The user message in English, filled in with values. The GUI translates it."""

        return fill(self.user_message, self.context) if self.user_message else None


    def as_diagnostic(
        self,
        severity: Severity = Severity.ERROR,
        **context,
    ) -> Diagnostic:
        """`context` adds what only the caller knows, e.g. where the error was found."""
        
        from app.core.diagnostics import Diagnostic
        return Diagnostic(
            layer=self.layer,
            severity=severity,
            code=self.code,
            message=self.user_message or literal(str(self)),
            context={**self.context, **context},
        )