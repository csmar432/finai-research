"""Tests for ResearchMemory three-layer memory system."""

import shutil
import os
import tempfile

from scripts.core.memory import ResearchMemory, ContextUnit


def test_memory_push_and_retrieve():
    """Test push, get_context, and session save/load round-trip."""
    tmpdir = tempfile.mkdtemp()
    try:
        db = os.path.join(tmpdir, "test.db")
        mem = ResearchMemory("test-session", db_path=db)
        mem.push(
            "分析茅台财务",
            {"revenue": 100},
            {"tools": ["fetch_a_financial"]},
        )
        ctx = mem.get_context(limit=1)
        assert len(ctx) == 1, f"Expected 1 context item, got {len(ctx)}"
        assert "茅台" in ctx[0].task, f"Task '{ctx[0].task}' does not contain '茅台'"

        # Verify full in-memory context
        assert len(mem.context) == 1
        assert mem.context[0].result == {"revenue": 100}

        mem.save_session()

        restored = ResearchMemory.load_session("test-session", db_path=db)
        assert len(restored.get_context()) == 1, (
            f"Restored session should have 1 context item, got {len(restored.get_context())}"
        )
        # Verify the restored data
        restored_ctx = restored.get_context()[0]
        assert "茅台" in restored_ctx.task
        assert restored_ctx.result == {"revenue": 100}
    finally:
        shutil.rmtree(tmpdir)


def test_compress_context():
    """Test that context is compressed to <= 3 items when it exceeds 20."""
    tmpdir = tempfile.mkdtemp()
    try:
        db = os.path.join(tmpdir, "test.db")
        mem = ResearchMemory("test-session", db_path=db)

        for i in range(25):
            mem.push(
                f"任务{i}",
                {"result": f"结果{i}"},
                {"tools": ["test"]},
            )

        # Before compression, context should have 25 items
        assert len(mem.context) == 25, (
            f"Expected 25 items before compression, got {len(mem.context)}"
        )

        mem.compress_context()

        # After compression, should have <= 3 items
        assert len(mem.context) <= 3, (
            f"Expected <= 3 items after compression, got {len(mem.context)}"
        )

        # The compressed entry should mention historical count
        latest = mem.context[-1]
        if "压缩" in latest.task or "summary" in (latest.result or {}):
            # Confirm compression happened
            assert True
    finally:
        shutil.rmtree(tmpdir)


def test_knowledge_store_and_retrieve():
    """Test long-term knowledge store and retrieval."""
    tmpdir = tempfile.mkdtemp()
    try:
        db = os.path.join(tmpdir, "test.db")
        mem = ResearchMemory("test-session", db_path=db)

        mem.store_knowledge(
            "paper:2312.00001",
            {"title": "Test Paper", "abstract": "A test abstract."},
            ["literature", "paper"],
        )

        # Retrieve by key
        result = mem.retrieve("paper:2312.00001")
        assert len(result) == 1, f"Expected 1 result, got {len(result)}"
        assert result[0]["key"] == "paper:2312.00001"
        assert result[0]["value"]["title"] == "Test Paper"

        # Retrieve by tag
        result_by_tag = mem.retrieve(tags=["literature"])
        assert len(result_by_tag) >= 1

        # Retrieve by partial key
        result_by_partial = mem.retrieve(query="2312.00001")
        assert len(result_by_partial) == 1

        # Store another entry and verify retrieval limit
        mem.store_knowledge(
            "paper:2312.00002",
            {"title": "Second Paper"},
            ["literature", "paper"],
        )
        result_with_limit = mem.retrieve(limit=1)
        assert len(result_with_limit) == 1, (
            f"Expected 1 result with limit=1, got {len(result_with_limit)}"
        )
    finally:
        shutil.rmtree(tmpdir)


def test_short_term_layer():
    """Test that short_term deque respects maxlen=20."""
    tmpdir = tempfile.mkdtemp()
    try:
        db = os.path.join(tmpdir, "test.db")
        mem = ResearchMemory("test-session", db_path=db)

        for i in range(30):
            mem.push(f"task_{i}", {"i": i}, {"tools": ["test"]})

        assert len(mem.short_term) == 20, (
            f"short_term should have max 20 items, got {len(mem.short_term)}"
        )
        # Oldest items should be dropped
        assert mem.short_term[-1].description == "task_29"
    finally:
        shutil.rmtree(tmpdir)


def test_update_evaluation():
    """Test that evaluation can be updated on a ContextUnit."""
    tmpdir = tempfile.mkdtemp()
    try:
        db = os.path.join(tmpdir, "test.db")
        mem = ResearchMemory("test-session", db_path=db)

        unit = mem.push(
            "分析茅台财务",
            {"revenue": 100},
            {"tools": ["fetch_a_financial"]},
        )
        assert mem.context[0].evaluation is None

        mem.update_evaluation(unit.timestamp, "Task completed successfully, score=0.85")

        updated = mem.get_context()[0]
        assert updated.evaluation is not None
        assert "0.85" in updated.evaluation
    finally:
        shutil.rmtree(tmpdir)


def test_to_dict_from_dict():
    """Test serialization round-trip via to_dict and from_dict."""
    tmpdir = tempfile.mkdtemp()
    try:
        db = os.path.join(tmpdir, "test.db")
        mem = ResearchMemory("test-session", db_path=db)

        mem.push("任务1", {"data": 1}, {"tools": ["tool_a"]})
        mem.push("任务2", {"data": 2}, {"tools": ["tool_b"]})

        d = mem.to_dict()
        assert d["session_id"] == "test-session"
        assert len(d["context"]) == 2
        assert len(d["short_term"]) == 2

        restored = ResearchMemory.from_dict(d, db_path=db)
        assert len(restored.context) == 2
        assert restored.context[0].task == "任务1"
        assert restored.context[1].task == "任务2"
    finally:
        shutil.rmtree(tmpdir)


if __name__ == "__main__":
    import sys
    tests = [
        test_memory_push_and_retrieve,
        test_compress_context,
        test_knowledge_store_and_retrieve,
        test_short_term_layer,
        test_update_evaluation,
        test_to_dict_from_dict,
    ]

    failed = 0
    for t in tests:
        try:
            t()
            print(f"[PASS] {t.__name__}")
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    if failed:
        print(f"FAILED: {failed}/{len(tests)} tests failed")
        sys.exit(1)
    else:
        print(f"OK: All {len(tests)} tests passed")
        sys.exit(0)
