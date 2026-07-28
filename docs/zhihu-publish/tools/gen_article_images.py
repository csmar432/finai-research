#!/usr/bin/env python3
"""知乎文章配图生成器 — 调用 zexapi (Gemini 原生格式) 文生图接口。

用法:
    export ZEX_API_KEY="你的密钥"
    python docs/zhihu-publish/tools/gen_article_images.py

说明:
    - 密钥从环境变量 ZEX_API_KEY 读取, 不写死在代码里。
    - 每个 prompt 生成一张图, 下载保存到 assets/gen/ 目录。
    - 同步接口, 单张超时 120s。
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

API_BASE = "https://zexapi.com/v1beta/models"
MODEL = "gemini-3.1-flash-image-preview"
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "gen"

# 每张配图的 (文件名, 宽高比, 提示词)。提示词统一走"深色学术科技风, 无文字"。
STYLE = (
    "clean flat vector illustration, dark navy (#0d1b2a) background, "
    "soft teal and amber accent colors, minimalist academic tech style, "
    "high detail, professional, NO text, NO words, NO letters"
)

FIGURES = [
    (
        "fig_cover_pipeline",
        "16:9",
        "A horizontal research pipeline of 8 connected glowing nodes flowing "
        "left to right, each node a simple icon (magnifier, book, network graph, "
        "database, chart, document), a subtle upward arrow of progress. " + STYLE,
    ),
    (
        "fig_did_estimators",
        "16:9",
        "A comparison chart concept: five small bar-chart panels side by side "
        "representing five different statistical estimators giving slightly "
        "different results, one panel highlighted with a checkmark glow. " + STYLE,
    ),
    (
        "fig_ai_vs_human",
        "16:9",
        "A split composition: left side a robot arm doing repetitive mechanical "
        "work (gears, data tables), right side a human head silhouette with a "
        "glowing lightbulb representing judgment and decision, a clean dividing "
        "line in the middle. " + STYLE,
    ),
    (
        "fig_data_sources",
        "1:1",
        "A central hub node connected by lines to many small database and globe "
        "icons arranged in a circle, representing many financial data sources "
        "feeding into one system. " + STYLE,
    ),
]


def generate_one(api_key: str, name: str, ratio: str, prompt: str) -> bool:
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": ratio, "imageSize": "2K"},
        },
    }
    req = urllib.request.Request(
        f"{API_BASE}/{MODEL}:generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"  [FAIL] {name}: 请求失败 {exc}")
        return False

    if "error" in body:
        print(f"  [FAIL] {name}: API 返回错误 {body['error'].get('message')}")
        return False

    try:
        url = body["data"][0]["url"]
    except (KeyError, IndexError):
        print(f"  [FAIL] {name}: 响应无图片 URL {json.dumps(body)[:200]}")
        return False

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / f"{name}.png"
    try:
        urllib.request.urlretrieve(url, dest)
    except Exception as exc:  # noqa: BLE001
        print(f"  [FAIL] {name}: 下载失败 {exc} (URL: {url})")
        return False
    print(f"  [OK]   {name}: {dest}")
    return True


def main() -> int:
    api_key = os.environ.get("ZEX_API_KEY", "").strip()
    if not api_key:
        print("ERROR: 未设置 ZEX_API_KEY 环境变量。")
        print('  export ZEX_API_KEY="你的密钥"')
        return 2

    print(f"生成 {len(FIGURES)} 张配图 → {OUT_DIR}")
    ok = 0
    for name, ratio, prompt in FIGURES:
        if generate_one(api_key, name, ratio, prompt):
            ok += 1
        time.sleep(1)
    print(f"\n完成: {ok}/{len(FIGURES)} 张成功")
    return 0 if ok == len(FIGURES) else 1


if __name__ == "__main__":
    sys.exit(main())
