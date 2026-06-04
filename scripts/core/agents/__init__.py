"""Professional Agent classes for the research pipeline.

PaperOrchestra (Google) style multi-agent architecture:
    - OutlineAgent: Generates structured paper outlines
    - LiteratureReviewAgent: Searches, verifies, and synthesizes literature
    - SectionWritingAgent: Writes paper sections with data/tables
    - ContentRefinementAgent: Simulated peer-review with halt rules
    - PlottingAgent: Generates matplotlib figures with captions
"""

from scripts.core.agents.base import (
    AgentConfig,
    AgentResult,
    BaseAgent,
    HaltDecision,
)
from scripts.core.agents.paper_agents import (
    ContentRefinementAgent,
    LiteratureReviewAgent,
    OutlineAgent,
    PlottingAgent,
    SectionWritingAgent,
)

__all__ = [
    "BaseAgent",
    "AgentConfig",
    "AgentResult",
    "HaltDecision",
    "OutlineAgent",
    "LiteratureReviewAgent",
    "SectionWritingAgent",
    "ContentRefinementAgent",
    "PlottingAgent",
]
