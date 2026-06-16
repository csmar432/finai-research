#!/usr/bin/env python3
"""
Example 04: MCP Data Fetching · 从 MCP 服务器拉取数据

演示如何从 43 个 MCP 数据源获取金融数据。
覆盖 4 层 fallback：MCP → Python lib → HTTP → synthetic。
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

OUTPUT_DIR = project_root / "output" / "examples" / "04-mcp-fetch"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def demo_4_layer_fallback():
    """演示 4 层 fallback 数据获取。"""
    print("🌐 4 层数据 Fallback 演示")
    print("=" * 60)
    print()
    print("每个数据需求按以下顺序尝试：")
    print()
    print("  1️⃣ MCP 服务器 (优先，实时数据)")
    print("  2️⃣ Python lib (akshare / yfinance / baostock)")
    print("  3️⃣ HTTP API (公开 API)")
    print("  4️⃣ Synthetic (模拟数据，需显式标记)")
    print()
    print("✅ 优点: 任何网络环境都能拿到数据")
    print("⚠️  约束: 模拟数据必须经用户明确授权")
    print()
    print("💡 真实使用：")
    print()
    print("   ```python")
    print("   from scripts.data_fetcher import fetch_with_fallback")
    print()
    print("   # A 股行情")
    print("   df = fetch_with_fallback(")
    print("       data_type='a_share_quote',")
    print("       ticker='000001.SZ',")
    print("       start='2024-01-01',")
    print("       end='2024-12-31',")
    print("       allow_synthetic=False,  # 禁止静默 fallback")
    print("   )")
    print()
    print("   # 中国宏观 GDP")
    print("   gdp = fetch_with_fallback(")
    print("       data_type='macro_china_gdp',")
    print("   )")
    print()
    print("   # 学术论文")
    print("   papers = fetch_with_fallback(")
    print("       data_type='openalex_works',")
    print("       query='carbon trading innovation',")
    print("       max_results=20,")
    print("   )")
    print("   ```")


if __name__ == "__main__":
    demo_4_layer_fallback()
    print()
    print(f"📁 预期输出: {OUTPUT_DIR}/")
