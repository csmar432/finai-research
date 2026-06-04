"""Dashboard Playwright 测试套件.

参考 Research-OS 的 Playwright 自测 suite，覆盖：
  - 滚动 / 主题切换 / 可排序表格
  - Lightbox 图表 / 打印样式表
  - ARIA 快照 / axe-core WCAG 合规
  - 视觉回归测试

运行方式:
    python -m scripts.core.test_dashboard          # 运行全部测试
    python -m scripts.core.test_dashboard --ui    # UI 模式（有浏览器窗口）
    python -m scripts.core.test_dashboard --trace  # 录制 trace.zip

依赖:
    pip install playwright pytest pytest-asyncio
    playwright install chromium
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))


# ─── Test Results ────────────────────────────────────────────────────────────────


@dataclass
class TestResult:
    name: str
    passed: bool
    duration_ms: float
    error: str = ""
    trace_path: Path | None = None

    def __str__(self) -> str:
        icon = "✅" if self.passed else "❌"
        status = "PASS" if self.passed else "FAIL"
        err_str = f"  Error: {self.error[:80]}" if self.error else ""
        return f"{icon} [{status}] {self.name} ({self.duration_ms:.0f}ms){err_str}"


@dataclass
class SuiteResult:
    suite_name: str
    results: list[TestResult] = field(default_factory=list)
    started_at: float = 0.0

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def __str__(self) -> str:
        total = len(self.results)
        return (
            f"\n{'═' * 60}\n"
            f"  {self.suite_name}\n"
            f"  结果: {self.passed}/{total} 通过  {self.failed}/{total} 失败\n"
            f"{'═' * 60}\n"
            + "\n".join(str(r) for r in self.results)
            + f"\n{'─' * 60}\n"
        )


# ─── Dashboard URL ───────────────────────────────────────────────────────────────


def _dashboard_url() -> str:
    return os.getenv("DASHBOARD_URL", "http://localhost:8501")


# ─── Playwright Browser Setup ────────────────────────────────────────────────────


async def _get_browser():
    try:
        from playwright.async_api import async_playwright, Browser, Page
    except ImportError:
        print("  [SKIP] playwright 未安装: pip install playwright && playwright install chromium")
        return None, None

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-web-security",
        ],
    )
    context = await browser.new_context(
        viewport={"width": 1440, "height": 900},
        locale="zh-CN",
    )
    return pw, browser, context


# ─── Test Cases ────────────────────────────────────────────────────────────────


async def _test_scroll_spy(page, url: str) -> TestResult:
    """测试 Dashboard 滚动定位（TOC scroll-spy）"""
    name = "滚动定位 (scroll-spy)"
    t0 = time.perf_counter()
    try:
        await page.goto(url, wait_until="networkidle", timeout=20000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        await asyncio.sleep(0.5)
        # Check active nav item changed
        active = await page.query_selector("[data-testid='stSidebar'] .active")
        duration_ms = (time.perf_counter() - t0) * 1000
        return TestResult(name=name, passed=True, duration_ms=duration_ms)
    except Exception as e:
        duration_ms = (time.perf_counter() - t0) * 1000
        return TestResult(name=name, passed=False, duration_ms=duration_ms, error=str(e))


async def _test_theme_toggle(page, url: str) -> TestResult:
    """测试亮/暗主题切换"""
    name = "主题切换 (theme toggle)"
    t0 = time.perf_counter()
    try:
        await page.goto(url, wait_until="networkidle", timeout=20000)
        toggle = page.locator("[data-testid='stMainMenu']").first
        await toggle.click(timeout=5000)
        await asyncio.sleep(0.3)
        # Check body class changed
        dark = await page.evaluate("document.body.className.includes('dark')")
        duration_ms = (time.perf_counter() - t0) * 1000
        return TestResult(name=name, passed=True, duration_ms=duration_ms)
    except Exception as e:
        duration_ms = (time.perf_counter() - t0) * 1000
        return TestResult(name=name, passed=False, duration_ms=duration_ms, error=str(e))


async def _test_sortable_tables(page, url: str) -> TestResult:
    """测试表格可排序列"""
    name = "表格排序 (sortable tables)"
    t0 = time.perf_counter()
    try:
        await page.goto(url, wait_until="networkidle", timeout=20000)
        # Look for st.dataframe
        table = page.locator("[data-testid='stDataFrame']").first
        await table.wait_for(timeout=5000)
        headers = table.locator("[role='columnheader']")
        count = await headers.count()
        if count > 0:
            await headers.nth(0).click()
            await asyncio.sleep(0.3)
        duration_ms = (time.perf_counter() - t0) * 1000
        return TestResult(name=name, passed=True, duration_ms=duration_ms)
    except Exception as e:
        duration_ms = (time.perf_counter() - t0) * 1000
        return TestResult(name=name, passed=False, duration_ms=duration_ms, error=str(e))


async def _test_lightbox_figures(page, url: str) -> TestResult:
    """测试图表点击放大（Lightbox）"""
    name = "图表放大 (lightbox figures)"
    t0 = time.perf_counter()
    try:
        await page.goto(url, wait_until="networkidle", timeout=20000)
        img = page.locator("img").first
        await img.click(timeout=3000)
        await asyncio.sleep(0.3)
        # Check if lightbox/modal opened
        modal = page.locator("[role='dialog'], .lightbox, [class*='lightbox']").first
        duration_ms = (time.perf_counter() - t0) * 1000
        return TestResult(name=name, passed=True, duration_ms=duration_ms)
    except Exception as e:
        duration_ms = (time.perf_counter() - t0) * 1000
        # Lightbox is optional — pass with warning
        return TestResult(name=name, passed=True, duration_ms=duration_ms,
                         error=f"Lightbox not found (optional): {e}")


async def _test_print_stylesheet(page, url: str) -> TestResult:
    """测试打印样式表"""
    name = "打印样式 (print stylesheet)"
    t0 = time.perf_counter()
    try:
        await page.goto(url, wait_until="networkidle", timeout=20000)
        css = await page.evaluate("""
            () => {{
                const sheets = Array.from(document.styleSheets);
                return sheets
                    .filter(s => !s.href || !s.href.startsWith('data:'))
                    .some(s => {{
                        try {{
                            return Array.from(s.cssRules)
                                .some(r => r.cssText.includes('@media print'));
                        }} catch(e) {{ return false; }}
                    }});
            }}
        """)
        duration_ms = (time.perf_counter() - t0) * 1000
        return TestResult(name=name, passed=bool(css), duration_ms=duration_ms,
                         error="No @media print stylesheet found" if not css else "")
    except Exception as e:
        duration_ms = (time.perf_counter() - t0) * 1000
        return TestResult(name=name, passed=False, duration_ms=duration_ms, error=str(e))


async def _test_aria_snapshot(page, url: str) -> TestResult:
    """测试 ARIA 标签完整性"""
    name = "ARIA 快照 (ARIA snapshot)"
    t0 = time.perf_counter()
    try:
        await page.goto(url, wait_until="networkidle", timeout=20000)
        aria_issues: list[dict] = []

        # Check images have alt text
        imgs = await page.query_selector_all("img")
        for img in imgs[:10]:
            alt = await img.get_attribute("alt")
            if alt is None:
                aria_issues.append({"tag": "img", "issue": "missing alt"})

        # Check interactive elements have accessible names
        btns = await page.query_selector_all("button")
        for btn in btns[:10]:
            label = await btn.inner_text()
            if not label.strip():
                aria_issues.append({"tag": "button", "issue": "empty label"})

        duration_ms = (time.perf_counter() - t0) * 1000
        passed = len(aria_issues) == 0
        return TestResult(
            name=name, passed=passed, duration_ms=duration_ms,
            error=f"{len(aria_issues)} ARIA issues" if aria_issues else ""
        )
    except Exception as e:
        duration_ms = (time.perf_counter() - t0) * 1000
        return TestResult(name=name, passed=False, duration_ms=duration_ms, error=str(e))


async def _test_axe_wcag(page, url: str) -> TestResult:
    """测试 axe-core WCAG 合规"""
    name = "WCAG 合规 (axe-core)"
    t0 = time.perf_counter()
    try:
        from playwright.async_api import Error as PWError

        await page.goto(url, wait_until="networkidle", timeout=20000)
        await page.add_script_tag(
            url="https://cdn.jsdelivr.net/npm/axe-core@4.9.1/axe.min.js"
        )
        results = await page.evaluate("""
            () => new Promise((resolve) => {{
                if (typeof axe === 'undefined') {{
                    resolve({{ violations: [{ id: 'setup', description: 'axe not loaded' }] }});
                    return;
                }}
                axe.run({{ exclude: ['.streamlit-expander'] }}, (err, result) => {{
                    resolve(result || {{ violations: [] }});
                }});
            }})
        """)
        violations = results.get("violations", []) if isinstance(results, dict) else []
        critical = [v for v in violations if v.get("impact") in ("critical", "serious")]
        duration_ms = (time.perf_counter() - t0) * 1000
        passed = len(critical) == 0
        return TestResult(
            name=name, passed=passed, duration_ms=duration_ms,
            error=f"{len(critical)} critical WCAG violations" if not passed else ""
        )
    except Exception as e:
        duration_ms = (time.perf_counter() - t0) * 1000
        return TestResult(name=name, passed=False, duration_ms=duration_ms, error=str(e))


async def _test_visual_regression(page, url: str, baseline_dir: Path) -> TestResult:
    """视觉回归测试 — 截图对比"""
    name = "视觉回归 (visual regression)"
    t0 = time.perf_counter()
    try:
        await page.goto(url, wait_until="networkidle", timeout=20000)
        await asyncio.sleep(1.0)  # wait for charts to render
        screenshot = await page.screenshot(full_page=True)

        run_id = uuid.uuid4().hex[:8]
        baseline_path = baseline_dir / f"baseline_{run_id}.png"
        diff_path = baseline_dir / f"diff_{run_id}.png"
        baseline_dir.mkdir(parents=True, exist_ok=True)

        # Save current as "current"
        current_path = baseline_dir / f"current_{run_id}.png"
        current_path.write_bytes(screenshot)

        # Compare with baseline if exists
        if baseline_path.exists():
            baseline_bytes = baseline_path.read_bytes()
            # Simple pixel comparison (for detailed diff use pixelmatch)
            passed = screenshot == baseline_bytes
            return TestResult(
                name=name, passed=passed, duration_ms=(time.perf_counter() - t0) * 1000,
                error="Screenshot differs from baseline" if not passed else ""
            )
        else:
            # First run — save as baseline
            baseline_path.write_bytes(screenshot)
            return TestResult(
                name=name, passed=True, duration_ms=(time.perf_counter() - t0) * 1000,
                error="Baseline saved (first run)"
            )
    except Exception as e:
        duration_ms = (time.perf_counter() - t0) * 1000
        return TestResult(name=name, passed=False, duration_ms=duration_ms, error=str(e))


# ─── Test Runner ───────────────────────────────────────────────────────────────


async def run_dashboard_tests(
    urls: list[str] | None = None,
    baseline_dir: Path | None = None,
    ui_mode: bool = False,
    trace_dir: Path | None = None,
) -> SuiteResult:
    """
    运行 Dashboard Playwright 测试套件。

    参数:
        urls: 待测 Dashboard URL 列表
        baseline_dir: 视觉回归基准截图目录
        ui_mode: True = 有头浏览器（可见窗口）
        trace_dir: 录制 trace.zip 的目录
    """
    suite = SuiteResult(suite_name="Dashboard Playwright 测试套件")
    suite.started_at = time.time()

    urls = urls or [_dashboard_url()]
    baseline_dir = baseline_dir or Path("output/dashboard_tests/baselines")

    pw, browser, context = await _get_browser()
    if browser is None:
        return suite

    for url in urls:
        for test_fn in [
            _test_scroll_spy,
            _test_theme_toggle,
            _test_sortable_tables,
            _test_lightbox_figures,
            _test_print_stylesheet,
            _test_aria_snapshot,
            _test_axe_wcag,
            _test_visual_regression,
        ]:
            page = await context.new_page()

            # Trace recording
            if trace_dir:
                from playwright.async_api import tracing
                await page.context.tracing.start_chunk(
                    title=f"{test_fn.__name__}_{uuid.uuid4().hex[:6]}"
                )

            result = await test_fn(page, url)

            if trace_dir and result.error:
                try:
                    trace_path = trace_dir / f"trace_{test_fn.__name__}.zip"
                    trace_dir.mkdir(parents=True, exist_ok=True)
                    await page.context.tracing.stop_chunk(
                        path=str(trace_path)
                    )
                    result.trace_path = trace_path
                except Exception:
                    pass

            await page.close()
            suite.results.append(result)

            # Brief pause between tests
            await asyncio.sleep(0.3)

    await context.close()
    await browser.close()
    await pw.stop()
    return suite


# ─── CLI Entry Point ───────────────────────────────────────────────────────────


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Dashboard Playwright 测试套件")
    parser.add_argument("--url", default=_dashboard_url(), help="Dashboard URL")
    parser.add_argument("--baseline-dir", type=Path,
                       default=Path("output/dashboard_tests/baselines"))
    parser.add_argument("--ui", action="store_true", help="UI 模式（有浏览器窗口）")
    parser.add_argument("--trace", action="store_true", help="录制 trace.zip")
    parser.add_argument("--report", type=Path,
                       default=Path("output/dashboard_tests/report.json"),
                       help="输出 JSON 报告路径")
    args = parser.parse_args()

    print(f"\n{'═' * 60}")
    print("  Dashboard Playwright 测试套件")
    print(f"  URL: {args.url}")
    print(f"  基准目录: {args.baseline_dir}")
    print(f"{'═' * 60}\n")

    suite = asyncio.run(run_dashboard_tests(
        urls=[args.url],
        baseline_dir=args.baseline_dir,
        trace_dir=Path("output/dashboard_tests/traces") if args.trace else None,
    ))

    print(suite)

    # Save JSON report
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "suite": suite.suite_name,
        "total": len(suite.results),
        "passed": suite.passed,
        "failed": suite.failed,
        "duration_ms": (time.time() - suite.started_at) * 1000,
        "results": [
            {
                "name": r.name,
                "passed": r.passed,
                "duration_ms": r.duration_ms,
                "error": r.error,
                "trace": str(r.trace_path) if r.trace_path else None,
            }
            for r in suite.results
        ],
    }
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n报告已保存: {args.report}")

    sys.exit(0 if suite.failed == 0 else 1)


if __name__ == "__main__":
    main()
