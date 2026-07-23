"""Exception classes for the research workflow."""


class WorkflowError(Exception):
    """Base exception for all workflow errors."""



class DataFetchError(WorkflowError):
    """Raised when financial/academic data cannot be fetched."""



class LLMError(WorkflowError):
    """Raised when an LLM API call fails."""



class ValidationError(WorkflowError):
    """Raised when input validation fails."""



class CacheError(WorkflowError):
    """Raised when cache read/write fails."""



class DataSourceError(WorkflowError):
    """Raised when no data source is available for a research direction."""



class CitationError(WorkflowError):
    """Raised when citation resolution fails."""



class EmbeddingError(WorkflowError):
    """Raised when embedding generation fails."""

