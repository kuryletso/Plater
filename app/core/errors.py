from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from enum import StrEnum

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
        message: str,
        *,
        code: str | None = None,
        user_message: str | None = None,
        context: dict | None = None,
    ) -> None:
        
        super().__init__(message)

        self.code = code or type(self).__name__
        self.user_message = user_message        # if None, internal-only
        self.context = context or {}


    def as_diagnostic(
        self,
        severity: Severity = Severity.ERROR,
    ) -> Diagnostic:
        
        from app.core.diagnostics import Diagnostic
        return Diagnostic(
            layer=self.layer,
            severity=severity,
            code=self.code,
            message=self.user_message or str(self),
            context=self.context,
        )