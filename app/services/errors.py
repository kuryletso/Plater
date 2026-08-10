from app.core.errors import AppError, Layer, ErrorCategory


class ServiceError(AppError):
    layer = Layer.PERSISTENCE


class MissingRequiredPlaceholderValue(ServiceError):
    category = ErrorCategory.VALIDATION
    recoverable = True


class EntityNotFound(ServiceError):
    category = ErrorCategory.NOT_FOUND


class InvalidSelection(ServiceError):
    category = ErrorCategory.VALIDATION
    recoverable = True


class SequenceConflict(ServiceError):
    """The number consumed after rendering is not the number the document carries."""

    category = ErrorCategory.INTERNAL
    recoverable = True