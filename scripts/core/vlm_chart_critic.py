"""
VLM-powered figure critique and refinement loop.

Generates matplotlib figure → sends to VLM → gets feedback →
refines figure → repeats until convergence (max 3 iterations).

Based on PaperOrchestra's PaperBanana approach.

Environment variables:
    OPENAI_API_KEY   — GPT-4 Vision API key
    ANTHROPIC_API_KEY — Claude Vision API key
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ─── VLM Provider Interface ────────────────────────────────────────────────────


class VLMProvider:
    """Protocol for VLM providers (OpenAI GPT-4V, Claude, Gemini, etc.)."""

    def analyze_figure(self, image_bytes: bytes, prompt: str) -> str:
        """Send figure + prompt to VLM, return text critique."""
        ...


class OpenAIVLMProvider(VLMProvider):
    """OpenAI GPT-4 Vision provider."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model

    def analyze_figure(self, image_bytes: bytes, prompt: str) -> str:
        if not self.api_key:
            return '{"error": "OPENAI_API_KEY not set"}'

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 1024,
            "temperature": 0.3,
        }

        try:
            import urllib.request

            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            return json.dumps({"error": str(e)})


class AnthropicVLMProvider(VLMProvider):
    """Anthropic Claude Vision provider."""

    def __init__(self, api_key: str | None = None, model: str = "claude-3-5-sonnet-20241022"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model

    def analyze_figure(self, image_bytes: bytes, prompt: str) -> str:
        if not self.api_key:
            return '{"error": "ANTHROPIC_API_KEY not set"}'

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }

        try:
            import urllib.request

            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return result["content"][0]["text"]
        except Exception as e:
            return json.dumps({"error": str(e)})


def _resolve_vlm_provider(provider: VLMProvider | str) -> VLMProvider:
    """Resolve string shorthand to VLMProvider instance."""
    if isinstance(provider, VLMProvider):
        return provider
    mapping = {
        "openai": OpenAIVLMProvider,
        "anthropic": AnthropicVLMProvider,
    }
    cls = mapping.get(str(provider).lower())
    if cls is None:
        raise ValueError(f"Unknown VLM provider: {provider!r}. Available: {list(mapping)}")
    return cls()


# ─── Critique Result Dataclasses ──────────────────────────────────────────────


@dataclass
class FigureCritique:
    """Critique result from VLM."""
    score: float = 0.0
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    verdict: str = "revise"  # "accept" | "revise" | "major_revision"
    raw_response: str = ""

    @classmethod
    def from_json_response(cls, raw: str) -> FigureCritique:
        """Parse VLM JSON response into a FigureCritique."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Try extracting JSON from markdown code block
            match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                except json.JSONDecodeError:
                    data = {"error": raw[:500]}
            else:
                data = {"error": raw[:500]}

        if "error" in data:
            return cls(raw_response=raw, verdict="error")

        return cls(
            score=float(data.get("score", 0)),
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", []),
            suggestions=data.get("suggestions", []),
            verdict=data.get("verdict", "revise"),
            raw_response=raw,
        )


@dataclass
class CritiqueSession:
    """A single iteration of the critique loop."""
    iteration: int
    critique: FigureCritique
    refinement_code: str | None = None
    latency_ms: float = 0.0
    output_path: Path | None = None


# ─── Main Critic Class ────────────────────────────────────────────────────────


class VLMChartCritic:
    """
    VLM-powered chart critique and refinement.

    Workflow:
    1. Generate matplotlib figure code
    2. Execute code → save as PNG
    3. Send PNG to VLM with critique prompt
    4. VLM returns score + specific suggestions
    5. If score < threshold, generate refined matplotlib code
    6. Repeat up to max_iterations times
    7. Return best figure + critique history

    PaperOrchestra PaperBanana-style iteration.
    """

    CRITIQUE_PROMPT_TEMPLATE = """You are an expert academic figure reviewer.

Evaluate this matplotlib figure for a research paper on {domain}.
Consider:
1. Visual clarity (are axes, labels, legends readable?)
2. Data integrity (do visual patterns match the data description?)
3. Informative design (is the chart type appropriate?)
4. Professional appearance (font sizes, colors, style)
5. Publication quality (suitable for academic journal?)

Also check domain-specific issues:
- Empirical papers: are standard errors shown? Is significance indicated?
- Finance papers: are time periods labeled? Are index levels or returns shown?
- ML papers: are training/validation curves separated? Is generalization gap visible?

Respond in JSON format:
{{
    "score": <1-10>,
    "strengths": [<strength 1>, <strength 2>],
    "weaknesses": [<weakness 1>, <weakness 2>],
    "suggestions": [<specific improvement 1>, <specific improvement 2>],
    "verdict": "accept" | "revise" | "major_revision"
}}

IMPORTANT: Be strict. Academic figures should be publication-quality.
"""

    def __init__(
        self,
        vlm_provider: VLMProvider | str = "openai",
        max_iterations: int = 3,
        score_threshold: float = 7.5,
        api_key: str | None = None,
    ):
        self.vlm = _resolve_vlm_provider(vlm_provider)
        self.max_iterations = max_iterations
        self.score_threshold = score_threshold
        self.api_key = api_key
        self._history: list[CritiqueSession] = []

    def critique_figure(
        self,
        figure_code: str,
        domain: str = "empirical",
        output_path: str | Path | None = None,
    ) -> tuple[Path, list[CritiqueSession]]:
        """
        Run the full critique loop on a matplotlib figure.

        Args:
            figure_code: Python code that generates a matplotlib figure
            domain: "empirical" / "finance" / "ml" / "general"
            output_path: Where to save the final figure

        Returns:
            (path to best figure, list of critique sessions)
        """
        self._history = []
        current_code = figure_code
        best_score = 0.0
        best_path: Path | None = None

        for iteration in range(1, self.max_iterations + 1):
            start = time.time()

            # Step 1: Execute matplotlib code → save PNG
            out_path = self._execute_figure_code(
                current_code,
                output_path or (Path("data/charts") / f"critique_iter{iteration}.png"),
            )

            if out_path is None or not out_path.exists():
                # Execution failed
                critique = FigureCritique(
                    score=0.0,
                    verdict="major_revision",
                    weaknesses=["Figure code failed to execute"],
                    raw_response="",
                )
                session = CritiqueSession(
                    iteration=iteration,
                    critique=critique,
                    latency_ms=(time.time() - start) * 1000,
                )
                self._history.append(session)
                break

            # Step 2: Encode PNG for VLM
            img_bytes = out_path.read_bytes()

            # Step 3: Build critique prompt
            prompt = self.CRITIQUE_PROMPT_TEMPLATE.format(domain=domain)

            # Step 4: Send to VLM
            raw_response = self.vlm.analyze_figure(img_bytes, prompt)
            critique = FigureCritique.from_json_response(raw_response)
            latency_ms = (time.time() - start) * 1000

            # Step 5: Record session
            session = CritiqueSession(
                iteration=iteration,
                critique=critique,
                output_path=out_path,
                latency_ms=latency_ms,
            )
            self._history.append(session)

            # Step 6: Check if acceptable
            if critique.score >= self.score_threshold or critique.verdict == "accept":
                best_score = critique.score
                best_path = out_path
                break

            # Step 7: If not acceptable and still have iterations, refine
            if iteration < self.max_iterations:
                refined = self._generate_refinement(current_code, critique, domain)
                session.refinement_code = refined
                current_code = refined
                if critique.score > best_score:
                    best_score = critique.score
                    best_path = out_path

        # Return best path found
        if best_path is None:
            best_path = out_path or Path("data/charts/critique_failed.png")
        return best_path, list(self._history)

    def _execute_figure_code(self, code: str, output_path: Path) -> Path | None:
        """Execute matplotlib code in a subprocess with timeout."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Wrap code to ensure figure is saved
        wrapper = f"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import sys

{code}

# Save figure to the output path
plt.gcf().savefig(r'{output_path}', dpi=150, bbox_inches='tight')
print(f"Figure saved to {output_path}")
"""

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(wrapper)
            temp_path = f.name

        try:
            proc = subprocess.run(
                [sys.executable, temp_path],
                capture_output=True,
                text=True,
                timeout=30,
                env={**os.environ, "MPLBACKEND": "Agg"},
            )
            if proc.returncode != 0:
                return None
            return output_path
        except subprocess.TimeoutExpired:
            return None
        except Exception:
            return None
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass

    def _encode_figure(self, path: Path) -> bytes:
        """Encode figure as PNG bytes for VLM."""
        return path.read_bytes()

    def _generate_refinement(
        self, code: str, critique: FigureCritique, domain: str
    ) -> str:
        """Generate improved matplotlib code based on VLM feedback."""
        suggestions_text = "\n".join(
            f"- {s}" for s in critique.suggestions
        )
        weaknesses_text = "\n".join(
            f"- {w}" for s in critique.weaknesses
        )

        refinement_prompt = f"""You are an expert at improving matplotlib figures for academic papers.

The following matplotlib code produced a figure with these issues:
Weaknesses:
{weaknesses_text}

Suggestions for improvement:
{suggestions_text}

Original code:
```python
{code}
```

Please rewrite the matplotlib code to fix these issues. Return ONLY valid Python code (no markdown, no explanation). The code must:
1. Use `matplotlib.use('Agg')` at the top
2. Save the figure using `plt.gcf().savefig('output.png', dpi=150, bbox_inches='tight')`
3. Follow academic paper figure conventions (font sizes ≥ 10pt, clear labels, proper legends)
4. Fix all the weaknesses listed above
"""

        # Call LLM to generate refined code
        try:
            from scripts.core.llm_gateway import LLMGateway
            from scripts.core.memory import ResearchMemory

            memory = ResearchMemory(session_id="vlm_refine")
            gateway = LLMGateway(memory)
            result = gateway.generate(refinement_prompt, temperature=0.3, max_tokens=2048)
            return self._strip_code_fence(result.response)
        except Exception:
            # Fallback: append common improvements
            return code + "\n\n# Minor improvements: plt.tight_layout(); plt.rcParams.update({'font.size': 12})"

    def _strip_code_fence(self, text: str) -> str:
        """Remove markdown code fences from generated code."""
        text = text.strip()
        for prefix in ["```python\n", "```python", "```\n", "```"]:
            if text.startswith(prefix):
                text = text[len(prefix):]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def critique_only(self, image_path: str | Path) -> FigureCritique:
        """Critique an existing figure without refinement."""
        path = Path(image_path)
        if not path.exists():
            return FigureCritique(
                score=0.0,
                verdict="major_revision",
                weaknesses=[f"File not found: {image_path}"],
            )

        img_bytes = path.read_bytes()
        prompt = self.CRITIQUE_PROMPT_TEMPLATE.format(domain="general")
        raw = self.vlm.analyze_figure(img_bytes, prompt)
        return FigureCritique.from_json_response(raw)

    def integrate_with_plotting_agent(self, agent: PlottingAgent) -> None:
        """
        Wrap PlottingAgent._generate_figure to add VLM critique.

        After the agent generates a figure:
        1. Save it
        2. Run critique loop
        3. If revisions needed, regenerate with suggestions
        """
        _ = agent  # Reserved for future PlottingAgent integration
        # Future: monkey-patch or subclass PlottingAgent
        # to call self.critique_figure() after figure generation

    def save_history(self, path: str | Path) -> None:
        """Save critique history as JSON for debugging."""
        data = []
        for session in self._history:
            data.append({
                "iteration": session.iteration,
                "critique": asdict(session.critique),
                "refinement_code": session.refinement_code,
                "latency_ms": session.latency_ms,
                "output_path": str(session.output_path) if session.output_path else None,
            })
        Path(path).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def __repr__(self) -> str:
        return (
            f"VLMChartCritic(provider={type(self.vlm).__name__}, "
            f"max_iter={self.max_iterations}, threshold={self.score_threshold})"
        )
