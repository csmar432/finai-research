"""Exception classes for the research workflow."""


class WorkflowError(Exception):
    """Base exception for all workflow errors."""

    pass


class DataFetchError(WorkflowError):
    """Raised when financial/academic data cannot be fetched."""

    pass


class LLMError(WorkflowError):
    """Raised when an LLM API call fails."""

    pass


class ValidationError(WorkflowError):
    """Raised when input validation fails."""

    pass


class CacheError(WorkflowError):
    """Raised when cache read/write fails."""

    pass


class CitationError(WorkflowError):
    """Raised when citation resolution fails."""

    pass


class EmbeddingError(WorkflowError):
    """Raised when embedding generation fails."""

    pass
