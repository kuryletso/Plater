from app.core.errors import AppError, ErrorCategory, Layer


class UIError(AppError):
    layer = Layer.UI


class MissingUIElement(UIError):
    category = ErrorCategory.INTERNAL