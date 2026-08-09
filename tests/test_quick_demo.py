"""Regression tests for the canonical README demo."""

import hashlib
from pathlib import Path

from PIL import Image

from scripts.demo import gen_quick_demo


def test_storyboard_contract() -> None:
    frames, durations = gen_quick_demo.build_frames()

    assert len(frames) == len(durations) == 15
    assert {frame.size for frame in frames} == {(1200, 675)}
    assert "NO LIVE CLAIMS OR STATISTICAL RESULTS" in gen_quick_demo.DISCLOSURE


def test_generate_valid_gif(tmp_path: Path) -> None:
    output = gen_quick_demo.generate(tmp_path / "demo.gif")

    with Image.open(output) as rendered:
        assert rendered.size == (1200, 675)
        assert rendered.n_frames == 15
        rendered.seek(0)
        total_duration = sum(
            rendered.seek(frame) or rendered.info["duration"]
            for frame in range(rendered.n_frames)
        )

    assert 8_000 <= total_duration <= 10_000
    assert output.stat().st_size < 400_000


def test_generation_is_repeatable_on_same_platform(tmp_path: Path) -> None:
    first = gen_quick_demo.generate(tmp_path / "first.gif")
    second = gen_quick_demo.generate(tmp_path / "second.gif")

    assert hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(second.read_bytes()).digest()


def test_readmes_reference_only_canonical_demo() -> None:
    root = gen_quick_demo.PROJECT_ROOT
    readmes = [root / "README.md", root / "README_EN.md"]

    for readme in readmes:
        content = readme.read_text(encoding="utf-8")
        assert ".github/demo/demo.gif" in content
        assert "demo_full_pipeline" not in content

    generator = Path(gen_quick_demo.__file__).read_text(encoding="utf-8")
    assert "RESEARCH_TOPIC.md" not in generator
    assert "RESEARCH_PLAN.md" not in generator
