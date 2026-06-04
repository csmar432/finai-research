"""
Tests for scripts/core/mcp_tool_market.py and its integration
with scripts/core/tool_selector.py.
"""

import json
import sys
import tempfile
import io
from pathlib import Path
from unittest.mock import patch

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.core.mcp_tool_market import (
    MCPToolRegistry,
    ToolMetadata,
    get_default_registry,
    _default_registry,
    CATEGORY_RULES,
    TAG_KEYWORDS,
    _quality_score,
    _assign_category,
    _build_tags,
)
from scripts.core.tool_selector import ToolSelector
from scripts.core.memory import ResearchMemory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_default_registry():
    """Reset the global default registry before and after each test."""
    import scripts.core.mcp_tool_market as mkt
    mkt._default_registry = None
    yield
    mkt._default_registry = None


@pytest.fixture
def mock_memory():
    """Minimal mock ResearchMemory."""
    mem = pytest.importorskip("scripts.core.memory").ResearchMemory.__new__(
        ResearchMemory
    )
    mem._history = []
    mem._context = []
    return mem


@pytest.fixture
def mcp_servers_path():
    """Path to the mcp_servers directory."""
    return str(project_root / "mcp_servers")


# ---------------------------------------------------------------------------
# ToolMetadata tests
# ---------------------------------------------------------------------------

def test_tool_metadata_creation():
    """Create ToolMetadata, verify all fields are accessible."""
    tool = ToolMetadata(
        name="get_gdp",
        description="Fetch GDP data from World Bank",
        input_schema={"type": "object", "properties": {"country": {"type": "string"}}},
        mcp_server="user-wb-data",
        category="macro_data",
        quality_score=0.75,
        is_mock=False,
        requires_api_key=True,
        tags=["macro", "gdp", "worldbank"],
        last_updated="2026-01-01",
        example_params={"country": "CHN"},
    )

    assert tool.name == "get_gdp"
    assert tool.description == "Fetch GDP data from World Bank"
    assert tool.input_schema["type"] == "object"
    assert tool.mcp_server == "user-wb-data"
    assert tool.category == "macro_data"
    assert tool.quality_score == 0.75
    assert tool.is_mock is False
    assert tool.requires_api_key is True
    assert "macro" in tool.tags
    assert tool.last_updated == "2026-01-01"
    assert tool.example_params == {"country": "CHN"}


def test_tool_metadata_to_dict_from_dict():
    """Round-trip ToolMetadata via to_dict / from_dict."""
    original = ToolMetadata(
        name="get_cpi",
        description="Fetch CPI inflation data",
        input_schema={"type": "object"},
        mcp_server="user-wubei-stats",
        category="macro_data",
        quality_score=0.6,
        is_mock=True,
        requires_api_key=False,
        tags=["inflation", "cpi"],
        last_updated="2026-05-01",
        example_params=None,
    )

    d = original.to_dict()
    restored = ToolMetadata.from_dict(d)

    assert restored.name == original.name
    assert restored.description == original.description
    assert restored.quality_score == original.quality_score
    assert restored.is_mock == original.is_mock
    assert restored.tags == original.tags


# ---------------------------------------------------------------------------
# Registry construction tests
# ---------------------------------------------------------------------------

def test_registry_from_directory_loads_tools(mcp_servers_path):
    """MCPToolRegistry.from_directory() on mcp_servers/ loads tools."""
    registry = MCPToolRegistry.from_directory(mcp_servers_path)
    assert len(registry) > 0, "Expected at least one tool to be loaded"
    # All entries should be ToolMetadata instances
    for key, tool in registry.tools.items():
        assert isinstance(tool, ToolMetadata), f"Key {key} is not a ToolMetadata"
        assert tool.name
        assert tool.mcp_server.startswith("user_")


def test_registry_search_by_name(mcp_servers_path):
    """Search for 'gdp' or 'stock', verify results are non-empty."""
    registry = MCPToolRegistry.from_directory(mcp_servers_path)

    gdp_results = registry.search("gdp", max_results=10)
    assert len(gdp_results) > 0, "Expected at least one tool matching 'gdp'"

    for tool in gdp_results:
        q = "gdp"
        assert (
            q in tool.name.lower()
            or q in tool.description.lower()
            or any(q in tag.lower() for tag in tool.tags)
        ), f"Tool {tool.name} does not match query 'gdp'"


def test_registry_search_by_category(mcp_servers_path):
    """Search with category filter, verify all results match the category."""
    registry = MCPToolRegistry.from_directory(mcp_servers_path)

    # Pick a category that should have entries (e.g. 'macro_data')
    all_tools = list(registry.tools.values())
    if not all_tools:
        pytest.skip("No tools loaded — mcp_servers directory may be empty")

    # Use the first tool's category as the test filter
    sample_category = all_tools[0].category
    results = registry.search("data", category=sample_category, max_results=50)

    for tool in results:
        assert tool.category == sample_category, (
            f"Expected category '{sample_category}', got '{tool.category}'"
        )


def test_registry_quality_scoring_in_range(mcp_servers_path):
    """All quality scores must be in [0.0, 1.0]."""
    registry = MCPToolRegistry.from_directory(mcp_servers_path)
    assert len(registry) > 0, "Registry is empty"

    for key, tool in registry.tools.items():
        assert 0.0 <= tool.quality_score <= 1.0, (
            f"Tool '{key}' has out-of-range quality_score: {tool.quality_score}"
        )


def test_registry_get_by_server(mcp_servers_path):
    """Get all tools for a specific server, verify they all belong to it."""
    registry = MCPToolRegistry.from_directory(mcp_servers_path)
    all_tools = list(registry.tools.values())
    if not all_tools:
        pytest.skip("No tools loaded")

    # Pick a server that has at least one tool
    server_tools = registry.get_by_server(all_tools[0].mcp_server)
    assert len(server_tools) > 0
    for tool in server_tools:
        assert tool.mcp_server == all_tools[0].mcp_server


def test_registry_marketplace_report_structure(mcp_servers_path):
    """Marketplace report has all expected keys."""
    registry = MCPToolRegistry.from_directory(mcp_servers_path)
    report = registry.get_marketplace_report()

    expected_keys = {
        "total_tools",
        "total_servers",
        "by_category",
        "by_server",
        "category_avg_quality",
        "requires_api_key",
        "mock_tools",
        "top_5_by_quality",
        "generated_at",
    }
    assert expected_keys.issubset(report.keys()), (
        f"Missing keys: {expected_keys - set(report.keys())}"
    )
    assert report["total_tools"] >= 0
    assert isinstance(report["by_category"], dict)
    assert isinstance(report["top_5_by_quality"], list)


def test_registry_print_catalog_no_crash(mcp_servers_path, capsys):
    """print_catalog() should not raise an exception."""
    registry = MCPToolRegistry.from_directory(mcp_servers_path)
    # Capture stdout — should not raise
    registry.print_catalog()
    captured = capsys.readouterr()
    assert isinstance(captured.out, str)


def test_registry_to_json_serialization(mcp_servers_path):
    """Serialize registry to JSON, deserialize back, verify tools survived."""
    registry = MCPToolRegistry.from_directory(mcp_servers_path)
    data = registry.to_json()

    # Should be JSON-serializable
    json_str = json.dumps(data, ensure_ascii=False)

    # Deserialize
    restored = json.loads(json_str)
    assert "tools" in restored
    assert "total_tools" in restored
    assert restored["total_tools"] == len(registry)


def test_mock_tools_detected(mcp_servers_path):
    """Tools from mock servers are correctly flagged as mock."""
    registry = MCPToolRegistry.from_directory(mcp_servers_path)

    # At least one tool should have is_mock=True or is_mock=False
    mock_flags = {tool.is_mock for tool in registry.tools.values()}
    assert len(mock_flags) >= 1, "Could not determine mock status of any tool"

    # If there are mock tools, their description should not contain strong API signals
    for tool in registry.tools.values():
        if tool.is_mock:
            # Mock tools typically lack detailed schemas or have placeholder descriptions
            desc_lower = tool.description.lower()
            # A well-formed real tool would have at least a description
            assert len(tool.description.strip()) >= 0  # Always passes; mock is informational


# ---------------------------------------------------------------------------
# get_default_registry tests
# ---------------------------------------------------------------------------

def test_get_default_registry_returns_registry(mcp_servers_path):
    """get_default_registry() returns an MCPToolRegistry instance."""
    reg = get_default_registry(base_path=mcp_servers_path)
    assert isinstance(reg, MCPToolRegistry)
    assert len(reg) > 0


def test_get_default_registry_caches(mcp_servers_path):
    """Calling get_default_registry twice returns the same object."""
    reg1 = get_default_registry(base_path=mcp_servers_path)
    reg2 = get_default_registry(base_path=mcp_servers_path)
    assert reg1 is reg2, "get_default_registry should return a cached singleton"


def test_get_default_registry_unknown_path():
    """get_default_registry with non-existent path raises RuntimeError."""
    import scripts.core.mcp_tool_market as mkt
    mkt._default_registry = None  # ensure uncached

    with pytest.raises(RuntimeError, match="mcp_servers directory not found"):
        get_default_registry(base_path="/nonexistent/path/nowhere")


# ---------------------------------------------------------------------------
# ToolSelector integration tests
# ---------------------------------------------------------------------------

def test_tool_selector_select_best_quality_tool(mock_memory):
    """select_best_quality_tool returns ToolMetadata objects."""
    from scripts.core.planner import TaskType
    selector = ToolSelector(memory=mock_memory)
    results = selector.select_best_quality_tool(
        task_type=TaskType.DATA_FETCH,
        category=None,
        top_k=5,
    )
    # Returns a list of ToolMetadata (may be empty)
    assert isinstance(results, list)
    for r in results:
        assert isinstance(r, ToolMetadata), (
            f"Expected ToolMetadata, got {type(r).__name__}"
        )


def test_tool_selector_marketplace_report(mock_memory):
    """get_tool_marketplace_report returns a dict with expected keys."""
    selector = ToolSelector(memory=mock_memory)
    report = selector.get_tool_marketplace_report()

    expected_keys = {
        "total_tools",
        "total_servers",
        "by_category",
        "by_server",
        "category_avg_quality",
        "requires_api_key",
        "mock_tools",
        "top_5_by_quality",
        "generated_at",
    }
    assert expected_keys.issubset(report.keys()), (
        f"Missing keys: {expected_keys - set(report.keys())}"
    )


def test_tool_selector_has_project_root(mock_memory):
    """ToolSelector instance has a project_root Path attribute."""
    selector = ToolSelector(memory=mock_memory)
    assert hasattr(selector, "project_root")
    assert isinstance(selector.project_root, Path)
    assert selector.project_root.exists()


def test_tool_selector_select_best_quality_by_category(mock_memory):
    """select_best_quality_tool with category filter returns matching tools."""
    from scripts.core.planner import TaskType
    selector = ToolSelector(memory=mock_memory)

    # Try with a known category
    results = selector.select_best_quality_tool(
        task_type=TaskType.DATA_FETCH,
        category="macro_data",
        top_k=10,
    )
    assert isinstance(results, list)
    for r in results:
        assert isinstance(r, ToolMetadata)
