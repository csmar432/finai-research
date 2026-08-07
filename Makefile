# Makefile for 论文-研报工作流
# Usage: make [target]

.PHONY: help setup install test run clean health check lint format docs demo

# Default target
help:
	@echo "论文-研报工作流 - FinResearch Agent"
	@echo ""
	@echo "Available targets:"
	@echo "  make setup     — Install all dependencies (dev + all extras)"
	@echo "  make install   — Install package in editable mode"
	@echo "  make test      — Run full test suite"
	@echo "  make test-core — Run core module tests only"
	@echo "  make test-research — Run research framework tests"
	@echo "  make health    — Run system health check"
	@echo "  make check     — Run all checks (health + lint + tests)"
	@echo "  make lint      — Run ruff linter"
	@echo "  make format    — Run ruff formatter"
	@echo "  make docs      — Build documentation"
	@echo "  make demo      — Run demo research report"
	@echo "  make pipeline  — Run full agent pipeline"
	@echo "  make clean     — Clean cache and build artifacts"

# ─── Installation ────────────────────────────────────────────────────────────

setup: install
	python scripts/health_check.py --json

install:
	pip install -e ".[all]"

# ─── Testing ─────────────────────────────────────────────────────────────────

test:
	python -m pytest tests/ -x -q --tb=short

test-core:
	python -m pytest tests/test_ai_parliament.py tests/test_self_evolution.py \
		tests/test_specialized_agents.py tests/test_checkpoint.py \
		tests/test_orchestrator_comprehensive.py tests/test_hitl_gate_comprehensive.py \
		tests/test_autonomy_loop_comprehensive.py \
		-x -q --tb=short

test-research:
	python -m pytest tests/test_modern_did.py tests/test_regression_engine.py \
		tests/test_demo_research_report.py tests/test_event_monitor.py \
		tests/test_health_check.py -x -q --tb=short

test-quick:
	python -m pytest tests/ -x -q --tb=short -k "not slow"

# ─── Health & Checks ──────────────────────────────────────────────────────────

health:
	python scripts/health_check.py

check: health lint test

# ─── Linting & Formatting ─────────────────────────────────────────────────────

lint:
	python -m ruff check scripts/ tests/ --select=E,F,W

lint-fix:
	python -m ruff check scripts/ tests/ --fix

format:
	python -m ruff format scripts/ tests/

# ─── Documentation ─────────────────────────────────────────────────────────────

docs:
	mkdocs build -f mkdocs.yml

docs-serve:
	mkdocs serve -f mkdocs.yml

# ─── Demo & Pipeline ───────────────────────────────────────────────────────────

demo:
	python scripts/demo_research_report.py

pipeline:
	python scripts/agent_pipeline.py

# agent_pipeline has no --stage flag; lit-only entry is literature_download.py
pipeline-lit:
	python scripts/literature_download.py

# ─── Validation ────────────────────────────────────────────────────────────────

validate-econometrics:
	python scripts/validate_econometrics.py --method all

validate-novelty:
	python scripts/research_framework/pipeline.py --mode novelty-check

# ─── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	rm -rf build/ dist/ *.egg-info
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf output/cache/ output/provenance/*.json 2>/dev/null || true

clean-all: clean
	rm -rf data/*.db data/*.json output/ logs/ *.log

# ─── Dependency Info ───────────────────────────────────────────────────────────

requirements:
	pip install pip-tools
	pip-compile pyproject.toml --output-file requirements.txt --generate-hashes

.PHONY: requirements
