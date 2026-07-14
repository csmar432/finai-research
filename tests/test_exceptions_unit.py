"""Unit tests for scripts/exceptions.py."""

from __future__ import annotations

from scripts.exceptions import (
    CacheError,
    CitationError,
    DataFetchError,
    DataSourceError,
    EmbeddingError,
    LLMError,
    ValidationError,
    WorkflowError,
)


class TestWorkflowErrorBase:
    """Base WorkflowError is an Exception."""

    def test_workflow_error_is_exception(self):
        assert issubclass(WorkflowError, Exception)

    def test_can_instantiate(self):
        e = WorkflowError("test message")
        assert str(e) == "test message"

    def test_can_raise(self):
        try:
            raise WorkflowError("x")
        except WorkflowError as e:
            assert str(e) == "x"


class TestDataFetchError:
    """DataFetchError inherits from WorkflowError."""

    def test_inherits_workflow_error(self):
        assert issubclass(DataFetchError, WorkflowError)

    def test_can_raise(self):
        try:
            raise DataFetchError("fetch failed")
        except DataFetchError as e:
            assert "fetch failed" in str(e)
        except WorkflowError:
            # also catchable as WorkflowError
            assert True


class TestLLMError:
    """LLMError inherits from WorkflowError."""

    def test_inherits_workflow_error(self):
        assert issubclass(LLMError, WorkflowError)


class TestValidationError:
    """ValidationError inherits from WorkflowError."""

    def test_inherits_workflow_error(self):
        assert issubclass(ValidationError, WorkflowError)


class TestCacheError:
    """CacheError inherits from WorkflowError."""

    def test_inherits_workflow_error(self):
        assert issubclass(CacheError, WorkflowError)


class TestDataSourceError:
    """DataSourceError inherits from WorkflowError."""

    def test_inherits_workflow_error(self):
        assert issubclass(DataSourceError, WorkflowError)


class TestCitationError:
    """CitationError inherits from WorkflowError."""

    def test_inherits_workflow_error(self):
        assert issubclass(CitationError, WorkflowError)


class TestEmbeddingError:
    """EmbeddingError inherits from WorkflowError."""

    def test_inherits_workflow_error(self):
        assert issubclass(EmbeddingError, WorkflowError)


class TestAllErrorsCatchable:
    """All can be caught as WorkflowError."""

    def test_data_fetch_catchable(self):
        with __import__("pytest").raises(WorkflowError):
            raise DataFetchError("x")

    def test_llm_catchable(self):
        with __import__("pytest").raises(WorkflowError):
            raise LLMError("x")

    def test_validation_catchable(self):
        with __import__("pytest").raises(WorkflowError):
            raise ValidationError("x")

    def test_cache_catchable(self):
        with __import__("pytest").raises(WorkflowError):
            raise CacheError("x")

    def test_data_source_catchable(self):
        with __import__("pytest").raises(WorkflowError):
            raise DataSourceError("x")

    def test_citation_catchable(self):
        with __import__("pytest").raises(WorkflowError):
            raise CitationError("x")

    def test_embedding_catchable(self):
        with __import__("pytest").raises(WorkflowError):
            raise EmbeddingError("x")
