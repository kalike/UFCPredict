"""Domain exceptions for ufc_core."""


class UFCCoreError(Exception):
    """Base exception for all ufc_core errors."""


class NotFoundError(UFCCoreError):
    """Resource not found."""


class ValidationError(UFCCoreError):
    """Validation failure."""
