"""agent_loader.py — Declarative YAML agent definition system.

This module provides two classes for loading and using agent definitions from
`config/agents.yaml`:

`AgentLoader`
    Load agent, analyst, and pipeline definitions from YAML. Build
    `AgentConfig` / `AnalystConfig` instances. Register agents with an
    `AgentOrchestrator`.

`ConfigManager`
    Unified configuration facade that loads agents.yaml, halt_rules,
    llm_config, and project_config, and provides a single interface for
    all configuration needed by the orchestration layer.

Usage
-----
    # Option 1: AgentLoader only
    loader = AgentLoader("config/agents.yaml")
    loader.load()
    loader.register_all(orchestrator)

    steps = loader.get_pipeline_steps("paper")

    # Option 2: ConfigManager (loads everything)
    cm = ConfigManager()
    agents   = cm.load_agents()
    analysts = cm.load_analysts()
    rules    = cm.load_halt_rules("empirical_paper")
    pipeline = cm.build_pipeline("paper")
    routing  = cm.get_model_routing()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from scripts.core.agents.base import AgentConfig
from scripts.core.analyst import (
    AnalystConfig,
    AnalystType,
    BaseAnalystAgent,
    EnhancedEarningsQualityAgent,
    EnhancedFundamentalFinancialAgent,
    EnhancedValuationAgent,
)

logger = logging.getLogger(__name__)


# ─── AgentLoader ───────────────────────────────────────────────────────────────


class AgentLoader:
    """
    Load agent definitions from YAML and build AgentConfig instances.

    Parameters
    ----------
    yaml_path : str | Path
        Path to the agents.yaml configuration file.
        Defaults to "config/agents.yaml" relative to the workspace root.

    Attributes
    ----------
    yaml_path : Path
        Resolved path to the YAML file.
    _data : dict
        Parsed YAML content (populated by load()).

    Example
    -------
        loader = AgentLoader()
        loader.load()
        print(loader.list_agents())
        # ['outline', 'literature_review', 'plotting', 'section_writing',
        #  'content_refinement']

        config = loader.get_agent_config("outline")
        print(config.role)  # '论文大纲设计专家'

        loader.register_all(orchestrator)
    """

    def __init__(self, yaml_path: str | Path = "config/agents.yaml"):
        self.yaml_path = Path(yaml_path)
        self._data: dict[str, Any] = {}

    # ── Load ──────────────────────────────────────────────────────────────────

    def load(self) -> dict[str, Any]:
        """
        Load and parse the YAML file.

        Returns
        -------
        dict
            The parsed YAML content with keys: agents, analysts, pipelines,
            model_routing.

        Raises
        ------
        FileNotFoundError
            If the YAML file does not exist.
        yaml.YAMLError
            If the YAML content is malformed.
        """
        if not self.yaml_path.exists():
            raise FileNotFoundError(
                f"Agent definition file not found: {self.yaml_path}"
            )

        with open(self.yaml_path, encoding="utf-8") as fh:
            self._data = yaml.safe_load(fh) or {}

        logger.info(
            f"Loaded agent definitions from {self.yaml_path}: "
            f"{len(self._data.get('agents', {}))} agents, "
            f"{len(self._data.get('analysts', {}))} analysts, "
            f"{len(self._data.get('pipelines', {}))} pipelines"
        )
        return self._data

    # ── Agent Config ───────────────────────────────────────────────────────────

    def get_agent_config(self, name: str) -> AgentConfig | None:
        """
        Build an `AgentConfig` from a YAML agent definition.

        Parameters
        ----------
        name : str
            Agent name as defined in `agents` section of YAML.

        Returns
        -------
        AgentConfig | None
            A fully-populated AgentConfig, or None if the agent is not defined.
        """
        agents = self._data.get("agents", {})
        raw = agents.get(name)
        if raw is None:
            logger.warning(f"Agent '{name}' not found in {self.yaml_path}")
            return None

        return AgentConfig(
            name=name,
            role=str(raw.get("role", "")),
            goal=str(raw.get("goal", "")),
            backstory=str(raw.get("backstory", "")),
            allowed_tools=list(raw.get("allowed_tools", [])),
            max_iterations=int(raw.get("max_iterations", 5)),
            max_time_seconds=float(raw.get("max_time_seconds", 120.0)),
            temperature=float(raw.get("temperature", 0.7)),
            llm_model=raw.get("llm_model"),
            output_format=str(raw.get("output_format", "text")),
        )

    def get_analyst_config(self, name: str) -> AnalystConfig | None:
        """
        Build an `AnalystConfig` from a YAML analyst definition.

        Parameters
        ----------
        name : str
            Analyst name as defined in `analysts` section of YAML.

        Returns
        -------
        AnalystConfig | None
            A fully-populated AnalystConfig, or None if not defined.
        """
        analysts = self._data.get("analysts", {})
        raw = analysts.get(name)
        if raw is None:
            logger.warning(f"Analyst '{name}' not found in {self.yaml_path}")
            return None

        # Map analyst name → AnalystType enum
        analyst_type = _NAME_TO_ANALYST_TYPE.get(name, AnalystType.FUNDAMENTAL_MARKET)

        return AnalystConfig(
            analyst_type=analyst_type,
            name=str(raw.get("role", name)),
            role=str(raw.get("role", "")),
            focus_areas=[],  # Populated by subclass
            tools=list(raw.get("allowed_tools", [])),
            max_iterations=int(raw.get("max_iterations", 2)),
            temperature=float(raw.get("temperature", 0.7)),
        )

    # ── Pipeline ──────────────────────────────────────────────────────────────

    def get_pipeline_steps(self, pipeline_name: str) -> list[PipelineStep]:
        """
        Build a list of `PipelineStep` objects from a YAML pipeline definition.

        Parameters
        ----------
        pipeline_name : str
            Name of the pipeline defined under `pipelines` in YAML.

        Returns
        -------
        list[PipelineStep]
            Ordered list of pipeline steps. Returns an empty list if the
            pipeline is not defined or has no steps.

        Raises
        ------
        ValueError
            If the pipeline definition is invalid (e.g., both `steps` and
            `agents` are specified).
        """
        pipelines = self._data.get("pipelines", {})
        raw = pipelines.get(pipeline_name)
        if raw is None:
            logger.warning(
                f"Pipeline '{pipeline_name}' not found in {self.yaml_path}"
            )
            return []

        steps: list[PipelineStep] = []

        # Pipeline defined with explicit step list
        raw_steps = raw.get("steps", [])
        if raw_steps:
            for step_def in raw_steps:
                try:
                    steps.append(PipelineStep(
                        agent_name=str(step_def["agent"]),
                        stage=PipelineStage(step_def["stage"]),
                        hitl_gate=bool(step_def.get("hitl_gate", False)),
                        depends_on=[
                            PipelineStage(d) for d in step_def.get("depends_on", [])
                        ],
                    ))
                except (KeyError, ValueError) as exc:
                    logger.error(
                        f"Invalid pipeline step in '{pipeline_name}': {exc}"
                    )

        # Pipeline defined with agent list (parallel mode)
        raw_agents = raw.get("agents", [])
        hitl_gate_after = raw.get("hitl_gate_after")
        max_workers = raw.get("max_workers")
        if raw_agents and not raw_steps:
            for i, agent_name in enumerate(raw_agents):
                stage = _STAGE_FALLBACK_ORDER[i % len(_STAGE_FALLBACK_ORDER)]
                # Enable HITL gate for the specified agent
                step_hitl = (hitl_gate_after and agent_name == hitl_gate_after)
                steps.append(PipelineStep(
                    agent_name=agent_name,
                    stage=stage,
                    hitl_gate=step_hitl,
                    depends_on=[],
                    hitl_gate_after=hitl_gate_after,
                    max_workers=max_workers,
                ))

        logger.info(
            f"Built pipeline '{pipeline_name}': {len(steps)} steps, "
            f"mode={raw.get('mode', 'sequential')}, "
            f"hitl_gate_after={hitl_gate_after}, max_workers={max_workers}"
        )
        return steps

    # ── Model Routing ─────────────────────────────────────────────────────────

    def get_model_routing(self) -> dict[str, str]:
        """
        Return the task → LLM model mapping from YAML.

        Returns
        -------
        dict[str, str]
            Maps task names to model identifiers.
            Always includes the `default` key.
        """
        routing = self._data.get("model_routing", {})
        by_task = routing.get("by_task", {})
        by_task["default"] = routing.get("default", "deepseek")
        return by_task

    def get_model_for_task(self, task: str) -> str:
        """
        Get the LLM model for a specific task.

        Parameters
        ----------
        task : str
            Task identifier (e.g. "paper_cn", "research").

        Returns
        -------
        str
            Model identifier, falling back to the configured default.
        """
        routing = self.get_model_routing()
        return routing.get(task, routing.get("default", "deepseek"))

    # ── Registration ─────────────────────────────────────────────────────────

    def register_all(self, orchestrator: AgentOrchestrator) -> None:
        """
        Register all agents from YAML into an `AgentOrchestrator`.

        Instantiates each agent class with its YAML config and calls
        `orchestrator.register()`.

        Parameters
        ----------
        orchestrator : AgentOrchestrator
            The orchestrator instance to register agents into.
        """
        from scripts.core.agents.base import BaseAgent
        from scripts.core.agents.paper_agents import (
            ContentRefinementAgent,
            LiteratureReviewAgent,
            OutlineAgent,
            PlottingAgent,
            SectionWritingAgent,
        )

        _AGENT_NAME_TO_CLASS: dict[str, type[BaseAgent]] = {
            "outline": OutlineAgent,
            "literature_review": LiteratureReviewAgent,
            "plotting": PlottingAgent,
            "section_writing": SectionWritingAgent,
            "content_refinement": ContentRefinementAgent,
        }

        registered = 0
        for name, config in self.iter_agent_configs():
            agent_cls = _AGENT_NAME_TO_CLASS.get(name)
            if agent_cls is None:
                logger.warning(
                    f"No Python class registered for YAML agent '{name}', skipping"
                )
                continue

            # Extra kwargs for agents that need them
            extra_kwargs: dict[str, Any] = {}
            if name == "content_refinement":
                extra_kwargs["halt_rules_domain"] = (
                    self._data.get("agents", {})
                    .get(name, {})
                    .get("halt_rules_domain", "empirical_paper")
                )

            agent = agent_cls(config, orchestrator.gateway, **extra_kwargs)
            orchestrator.register(agent)
            registered += 1
            logger.debug(f"Registered agent: {name}")

        logger.info(f"Registered {registered}/{len(self.list_agents())} agents")

    def register_analysts(
        self,
        orchestrator: AgentOrchestrator,
    ) -> list[str]:
        """
        Register analyst agents from YAML into an `AgentOrchestrator`.

        Creates `Enhanced*` analyst subclasses when available for the type.

        Parameters
        ----------
        orchestrator : AgentOrchestrator
            The orchestrator to register analysts with.

        Returns
        -------
        list[str]
            Names of successfully registered analysts.
        """

        _ANALYST_TYPE_TO_CLASS = {
            AnalystType.FUNDAMENTAL_FINANCIAL: EnhancedFundamentalFinancialAgent,
            AnalystType.VALUATION: EnhancedValuationAgent,
            AnalystType.EARNINGS_QUALITY: EnhancedEarningsQualityAgent,
        }

        registered: list[str] = []
        for name, config in self.iter_analyst_configs():
            agent_cls = _ANALYST_TYPE_TO_CLASS.get(config.analyst_type, BaseAnalystAgent)
            agent = agent_cls(config, orchestrator.gateway)
            orchestrator.register(agent)
            registered.append(name)
            logger.debug(f"Registered analyst: {name} ({config.analyst_type.value})")

        logger.info(f"Registered {len(registered)} analyst agents")
        return registered

    # ── Enumeration ───────────────────────────────────────────────────────────

    def list_agents(self) -> list[str]:
        """List all agent names defined in YAML."""
        return list(self._data.get("agents", {}).keys())

    def list_analysts(self) -> list[str]:
        """List all analyst names defined in YAML."""
        return list(self._data.get("analysts", {}).keys())

    def list_pipelines(self) -> list[str]:
        """List all pipeline names defined in YAML."""
        return list(self._data.get("pipelines", {}).keys())

    def iter_agent_configs(self):
        """Yield (name, AgentConfig) pairs for all YAML agents."""
        for name in self.list_agents():
            config = self.get_agent_config(name)
            if config is not None:
                yield name, config

    def iter_analyst_configs(self):
        """Yield (name, AnalystConfig) pairs for all YAML analysts."""
        for name in self.list_analysts():
            config = self.get_analyst_config(name)
            if config is not None:
                yield name, config


# ─── PipelineStep (mirrors orchestrator.PipelineStep) ─────────────────────────


class PipelineStep:
    """
    A single step in a declarative pipeline definition.

    Mirrors `scripts.core.orchestrator.PipelineStep` so that the YAML loader
    does not need to import from the orchestrator module (avoiding circular
    imports). The orchestrator's own `PipelineStep` dataclass is used at
    runtime.

    Parameters
    ----------
    agent_name : str
        Name of the agent to invoke.
    stage : PipelineStage
        Pipeline stage identifier.
    hitl_gate : bool, default False
        Whether to pause for human approval before running.
    depends_on : list[PipelineStage], default []
        Stages that must complete before this step runs.
    """

    def __init__(
        self,
        agent_name: str,
        stage: PipelineStage,
        hitl_gate: bool = False,
        depends_on: list[PipelineStage] | None = None,
        hitl_gate_after: str | None = None,
        max_workers: int | None = None,
    ):
        self.agent_name = agent_name
        self.stage = stage
        self.hitl_gate = hitl_gate
        self.depends_on: list[PipelineStage] = depends_on or []
        self.hitl_gate_after: str | None = hitl_gate_after
        self.max_workers: int | None = max_workers


class ParallelPipeline:
    """
    Represents a parallel analyst pipeline with HITL gate and concurrency control.

    Used for pipelines that run multiple analysts simultaneously.
    """

    def __init__(
        self,
        name: str,
        agent_names: list[str],
        hitl_gate_after: str | None = None,
        max_workers: int = 6,
        mode: str = "parallel",
    ):
        self.name = name
        self.agent_names = agent_names
        self.hitl_gate_after: str | None = hitl_gate_after
        self.max_workers: int = max_workers
        self.mode: str = mode
        self.steps: list[PipelineStep] = [
            PipelineStep(agent_name=an, stage=PipelineStage(f"ANALYST_{i}"))
            for i, an in enumerate(agent_names)
        ]


class PipelineStage(str):
    """
    Stage identifier for pipeline steps, compatible with orchestrator.PipelineStage.

    Acts as a namespaced string enum. Supports both attribute access
    (``PipelineStage.OUTLINE``) and construction from a string value
    (``PipelineStage("outline")``).

    Attributes
    ----------
    OUTLINE : PipelineStage
    LITERATURE : PipelineStage
    PLOTTING : PipelineStage
    WRITING : PipelineStage
    REFINEMENT : PipelineStage
    EVALUATION : PipelineStage
    FINANCIAL_ANALYSIS : PipelineStage
    REPORT_WRITING : PipelineStage
    """

    # ── Singleton pool ────────────────────────────────────────────────────────

    _pool: dict[str, PipelineStage] = {}

    def __new__(cls, value: str) -> PipelineStage:
        if value not in cls._pool:
            cls._pool[value] = super().__new__(cls, value)
        return cls._pool[value]

    def __repr__(self) -> str:
        return f"PipelineStage({str.__str__(self)!r})"

    # ── Standard stage constants ─────────────────────────────────────────────

    OUTLINE: PipelineStage = ...  # defined below
    LITERATURE: PipelineStage = ...
    PLOTTING: PipelineStage = ...
    WRITING: PipelineStage = ...
    REFINEMENT: PipelineStage = ...
    EVALUATION: PipelineStage = ...
    FINANCIAL_ANALYSIS: PipelineStage = ...
    REPORT_WRITING: PipelineStage = ...


# Assign singleton instances after class definition
PipelineStage.OUTLINE = PipelineStage("outline")
PipelineStage.LITERATURE = PipelineStage("literature")
PipelineStage.PLOTTING = PipelineStage("plotting")
PipelineStage.WRITING = PipelineStage("writing")
PipelineStage.REFINEMENT = PipelineStage("refinement")
PipelineStage.EVALUATION = PipelineStage("evaluation")
PipelineStage.FINANCIAL_ANALYSIS = PipelineStage("financial_analysis")
PipelineStage.REPORT_WRITING = PipelineStage("report_writing")


# ─── Analyst type mapping ──────────────────────────────────────────────────────

_NAME_TO_ANALYST_TYPE: dict[str, AnalystType] = {
    "fundamental_market": AnalystType.FUNDAMENTAL_MARKET,
    "fundamental_financial": AnalystType.FUNDAMENTAL_FINANCIAL,
    "competitive": AnalystType.COMPETITIVE,
    "risk": AnalystType.RISK,
    "valuation": AnalystType.VALUATION,
    "earnings_quality": AnalystType.EARNINGS_QUALITY,
    "market": AnalystType.EARNINGS_QUALITY,  # Closest type for market analyst
}

# Fallback stage order for agent-list pipelines (parallel mode)
_STAGE_FALLBACK_ORDER = [
    PipelineStage.FINANCIAL_ANALYSIS,
    PipelineStage.FINANCIAL_ANALYSIS,
    PipelineStage.FINANCIAL_ANALYSIS,
    PipelineStage.FINANCIAL_ANALYSIS,
    PipelineStage.FINANCIAL_ANALYSIS,
    PipelineStage.FINANCIAL_ANALYSIS,
]


# ─── ConfigManager ─────────────────────────────────────────────────────────────


class ConfigManager:
    """
    Unified configuration manager for the PaperOrchestra agent system.

    Loads and caches:
        - agents.yaml          → agent definitions
        - config/halt_rules/    → quality gate rule sets
        - config/llm_config.json → LLM provider settings
        - config/project_config.json → project-level settings

    All paths are resolved relative to the workspace root (the directory
    containing the ``config/`` subdirectory).

    Usage
    -----
        cm = ConfigManager()
        cm.load_all()

        # Agent definitions
        for name, config in cm.iter_agents():
            print(name, config.role)

        # Pipeline
        steps = cm.build_pipeline("paper")
        for step in steps:
            print(step.agent_name, step.stage)

        # Halt rules for a specific domain
        rules = cm.load_halt_rules("empirical_paper")
        print(rules.name, len(rules.rules))

        # Model routing
        model = cm.get_model_for_task("paper_cn")

    Attributes
    ----------
    workspace_root : Path
        The root directory of the workspace. Resolved automatically from
        the location of this file's parent directory.
    agents_yaml : Path
        Path to the agents.yaml configuration file.
    halt_rules_dir : Path
        Directory containing halt rule YAML files.
    llm_config_path : Path
        Path to the llm_config.json file.
    project_config_path : Path
        Path to the project_config.json file.
    """

    def __init__(
        self,
        workspace_root: str | Path | None = None,
        agents_yaml: str | Path = "config/agents.yaml",
        halt_rules_dir: str | Path = "config/halt_rules",
        llm_config_path: str | Path = "config/llm_config.json",
        project_config_path: str | Path = "config/project_config.json",
    ):
        if workspace_root is None:
            # Resolve from the location of this file
            workspace_root = Path(__file__).parent.parent.parent.resolve()
        self.workspace_root = Path(workspace_root)

        self.agents_yaml = self.workspace_root / agents_yaml
        self.halt_rules_dir = self.workspace_root / halt_rules_dir
        self.llm_config_path = self.workspace_root / llm_config_path
        self.project_config_path = self.workspace_root / project_config_path

        self._agent_loader: AgentLoader | None = None
        self._halt_rules_cache: dict[str, Any] = {}
        self._llm_config: dict[str, Any] = {}
        self._project_config: dict[str, Any] = {}
        self._loaded: bool = False

    # ── Loading ───────────────────────────────────────────────────────────────

    def load_all(self) -> ConfigManager:
        """
        Load all configuration files.

        Returns
        -------
        ConfigManager
            Returns self for method chaining.
        """
        self._agent_loader = AgentLoader(self.agents_yaml)
        self._agent_loader.load()

        self._llm_config = self._load_json(self.llm_config_path)
        self._project_config = self._load_json(self.project_config_path)

        self._loaded = True
        logger.info(
            "ConfigManager loaded: "
            f"{len(self.list_agents())} agents, "
            f"{len(self.list_pipelines())} pipelines, "
            f"llm_config keys={list(self._llm_config.keys())}, "
            f"project={self._project_config.get('project_name', 'unknown')}"
        )
        return self

    # ── Agent accessors ───────────────────────────────────────────────────────

    @property
    def agent_loader(self) -> AgentLoader:
        """Lazily create and load the agent loader."""
        if self._agent_loader is None:
            self._agent_loader = AgentLoader(self.agents_yaml)
            self._agent_loader.load()
        return self._agent_loader

    def load_agents(self) -> dict[str, AgentConfig]:
        """Load all AgentConfig instances keyed by name."""
        return {
            name: config
            for name, config in self.agent_loader.iter_agent_configs()
        }

    def load_analysts(self) -> dict[str, AnalystConfig]:
        """Load all AnalystConfig instances keyed by name."""
        return {
            name: config
            for name, config in self.agent_loader.iter_analyst_configs()
        }

    def iter_agents(self):
        """Yield (name, AgentConfig) pairs."""
        yield from self.agent_loader.iter_agent_configs()

    def iter_analysts(self):
        """Yield (name, AnalystConfig) pairs."""
        yield from self.agent_loader.iter_analyst_configs()

    def list_agents(self) -> list[str]:
        """List all agent names."""
        return self.agent_loader.list_agents()

    def list_analysts(self) -> list[str]:
        """List all analyst names."""
        return self.agent_loader.list_analysts()

    def get_agent_config(self, name: str) -> AgentConfig | None:
        """Get AgentConfig for a specific agent."""
        return self.agent_loader.get_agent_config(name)

    def get_analyst_config(self, name: str) -> AnalystConfig | None:
        """Get AnalystConfig for a specific analyst."""
        return self.agent_loader.get_analyst_config(name)

    # ── Pipeline ──────────────────────────────────────────────────────────────

    def list_pipelines(self) -> list[str]:
        """List all pipeline names."""
        return self.agent_loader.list_pipelines()

    def build_pipeline(self, name: str) -> list[PipelineStep]:
        """
        Build a declarative pipeline from YAML.

        Parameters
        ----------
        name : str
            Pipeline name defined under `pipelines` in YAML.

        Returns
        -------
        list[PipelineStep]
            Ordered list of steps. Empty list if pipeline not found.
        """
        return self.agent_loader.get_pipeline_steps(name)

    def get_pipeline_definition(self, name: str) -> dict[str, Any]:
        """
        Return the raw YAML definition for a pipeline.

        Parameters
        ----------
        name : str
            Pipeline name.

        Returns
        -------
        dict
            Raw YAML dict for the pipeline, or empty dict if not found.
        """
        data = self.agent_loader._data
        return data.get("pipelines", {}).get(name, {})

    # ── Halt Rules ────────────────────────────────────────────────────────────

    def load_halt_rules(self, domain: str) -> Any:
        """
        Load halt rules for a specific domain.

        Loads from ``config/halt_rules/{domain}.yaml`` and caches the result.

        Parameters
        ----------
        domain : str
            Rule domain name (e.g. "empirical_paper", "finance_report").
            Corresponds to the filename ``{domain}.yaml`` in halt_rules_dir.

        Returns
        -------
        HaltRules
            A rules object with ``name``, ``rules``, and ``validate()`` method.
            Returns a dummy empty rules object if the file is not found.
        """
        if domain in self._halt_rules_cache:
            return self._halt_rules_cache[domain]

        rule_path = self.halt_rules_dir / f"{domain}.yaml"
        try:
            with open(rule_path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except FileNotFoundError:
            logger.warning(f"Halt rules not found: {rule_path}")
            data = {"name": domain, "rules": []}

        # Build a simple rules object
        rules_data = data.get("rules", [])
        self._halt_rules_cache[domain] = HaltRules(
            name=data.get("name", domain),
            domain=domain,
            rules=[
                HaltRule(
                    description=str(r.get("description", "")),
                    rule_id=str(r.get("rule_id", f"rule_{i}")),
                    severity=str(r.get("severity", "error")),
                    pattern=str(r.get("pattern", "")),
                )
                for i, r in enumerate(rules_data)
            ],
        )
        return self._halt_rules_cache[domain]

    def list_halt_rule_domains(self) -> list[str]:
        """List available halt rule domain names (files in halt_rules_dir)."""
        if not self.halt_rules_dir.exists():
            return []
        return [
            p.stem for p in self.halt_rules_dir.glob("*.yaml")
        ]

    # ── Model Routing ─────────────────────────────────────────────────────────

    def get_model_routing(self) -> dict[str, str]:
        """Return the task → LLM model routing map."""
        return self.agent_loader.get_model_routing()

    def get_model_for_task(self, task: str) -> str:
        """Get the LLM model for a specific task."""
        return self.agent_loader.get_model_for_task(task)

    # ── Raw config accessors ─────────────────────────────────────────────────

    def get_llm_config(self) -> dict[str, Any]:
        """Return the raw llm_config.json dict."""
        return dict(self._llm_config)

    def get_project_config(self) -> dict[str, Any]:
        """Return the raw project_config.json dict."""
        return dict(self._project_config)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a top-level key from any loaded config.

        Checks agents.yaml, llm_config.json, and project_config.json
        in order and returns the first match.
        """
        if key in self._agent_loader._data:
            return self._agent_loader._data[key]
        if key in self._llm_config:
            return self._llm_config[key]
        if key in self._project_config:
            return self._project_config[key]
        return default

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        """Load a JSON file, returning an empty dict on error."""
        import json as _json

        if not path.exists():
            logger.warning(f"Config file not found: {path}")
            return {}
        try:
            return _json.loads(path.read_text(encoding="utf-8"))
        except _json.JSONDecodeError as exc:
            logger.error(f"Invalid JSON in {path}: {exc}")
            return {}


# ─── Halt Rules (returned by ConfigManager.load_halt_rules) ─────────────────


@dataclass
class HaltRule:
    """A single halt rule definition."""
    description: str
    rule_id: str
    severity: str = "error"
    pattern: str = ""


@dataclass
class HaltRules:
    """
    A loaded set of halt rules for a specific domain.

    Returned by ``ConfigManager.load_halt_rules()``.
    """
    name: str
    domain: str
    rules: list[HaltRule] = field(default_factory=list)

    def validate(self, content: dict[str, Any]) -> HaltValidationResult:
        """
        Validate content against all rules.

        Parameters
        ----------
        content : dict
            Content to validate. Typically contains text, review, or draft keys.

        Returns
        -------
        HaltValidationResult
            Validation result with ``all_passed``, ``violations``, and
            ``halted`` attributes.
        """
        violations: list[HaltViolation] = []
        text = str(content.get("text", "")) + str(content.get("review", ""))

        for rule in self.rules:
            if rule.pattern and rule.pattern.lower() in text.lower():
                violations.append(HaltViolation(
                    rule_id=rule.rule_id,
                    message=rule.description,
                    severity=rule.severity,
                ))

        return HaltValidationResult(
            all_passed=len(violations) == 0,
            violations=violations,
            halted=any(v.severity == "error" for v in violations),
        )


@dataclass
class HaltViolation:
    """A single violated halt rule."""
    rule_id: str
    message: str
    severity: str = "error"


@dataclass
class HaltValidationResult:
    """Result of halt rules validation."""
    all_passed: bool
    violations: list[HaltViolation]
    halted: bool


# ─── Re-export orchestrator for convenience ────────────────────────────────────

def _lazy_import_orchestrator():
    from scripts.core.orchestrator import AgentOrchestrator
    return AgentOrchestrator


# ─── Exports ─────────────────────────────────────────────────────────────────

__all__ = [
    "AgentLoader",
    "ConfigManager",
    "PipelineStep",
    "PipelineStage",
    "HaltRule",
    "HaltRules",
    "HaltViolation",
    "HaltValidationResult",
]
