#!/usr/bin/env python3
"""
终端输出转 PNG 工具
用于把 assets/ 下的文本快照转换成知乎可用的图片

用法：
  python tools/terminal_to_png.py                # 默认：所有 .txt → PNG
  python tools/terminal_to_png.py --file 01_health.txt
  python tools/terminal_to_png.py --theme dark    # 暗色主题
"""

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("❌ 缺少依赖 Pillow，请先安装：pip install Pillow")
    sys.exit(1)


# 配色方案（暗色 / 亮色）
THEMES = {
    "dark": {
        "bg": (40, 42, 54),       # Dracula 背景
        "fg": (248, 248, 242),     # 前景灰白
        "accent": (80, 250, 123),  # 绿色高亮
        "title": (139, 233, 253),  # 青色标题
    },
    "light": {
        "bg": (255, 255, 255),
        "fg": (40, 42, 54),
        "accent": (0, 150, 0),
        "title": (0, 100, 200),
    },
}


def get_font(size: int):
    """获取等宽字体（macOS / Linux 兼容）"""
    font_paths = [
        "/System/Library/Fonts/Menlo.ttc",          # macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",  # Linux
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ]
    for path in font_paths:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    # 兜底
    return ImageFont.load_default()


def render_text_to_image(text: str, title: str = "", theme: str = "dark", padding: int = 40) -> Image.Image:
    """把文本渲染成图片"""
    colors = THEMES[theme]
    font = get_font(16)
    title_font = get_font(20)

    # 估算尺寸（按最长行算）
    lines = text.split("\n")
    max_width = max((len(line) for line in lines), default=0)
    char_w = 10
    line_h = 22

    img_w = int(max_width * char_w + padding * 2)
    img_h = (len(lines) + 2) * line_h + padding * 2

    # 限制最大宽度
    img_w = min(img_w, 1600)
    img_h = min(img_h, 2400)

    img = Image.new("RGB", (img_w, img_h), colors["bg"])
    draw = ImageDraw.Draw(img)

    # 标题
    y = padding
    if title:
        draw.text((padding, y), title, fill=colors["title"], font=title_font)
        y += line_h + 10

    # 分隔线
    draw.line([(padding, y), (img_w - padding, y)], fill=colors["accent"], width=2)
    y += 10

    # 正文
    for line in lines:
        if y > img_h - line_h:
            break
        # 简化 ANSI 控制字符
        clean_line = line.replace("\x1b[0m", "").replace("\x1b[1m", "").replace("\x1b[2m", "")
        clean_line = clean_line.replace("\x1b[93m", "").replace("\x1b[91m", "").replace("\x1b[96m", "")
        clean_line = clean_line.replace("\x1b[0m", "").replace("\x1b[", "")
        # 简单的复选标记高亮
        color = colors["fg"]
        if "✅" in clean_line or "✓" in clean_line or "Tier" in clean_line:
            color = colors["accent"]
        draw.text((padding, y), clean_line, fill=color, font=font)
        y += line_h

    return img


def main():
    parser = argparse.ArgumentParser(description="终端输出转 PNG 工具")
    parser.add_argument("--file", help="指定单个文件")
    parser.add_argument("--theme", default="dark", choices=["dark", "light"], help="配色主题")
    parser.add_argument("--output-dir", default=None, help="输出目录（默认与输入同目录）")
    args = parser.parse_args()

    assets_dir = Path(__file__).parent.parent / "assets"
    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        out_dir = assets_dir

    # 选定文件
    if args.file:
        files = [assets_dir / args.file]
    else:
        files = sorted(assets_dir.glob("*.txt"))

    if not files:
        print(f"❌ {assets_dir} 下没有 .txt 文件")
        return

    print(f"📸 准备转换 {len(files)} 个文件，主题: {args.theme}")
    print(f"   输出目录: {out_dir}")
    print()

    for txt_file in files:
        if not txt_file.exists():
            print(f"⚠️  跳过 {txt_file.name}（不存在）")
            continue

        text = txt_file.read_text(encoding="utf-8")
        title = txt_file.stem.upper().replace("_", " ")

        img = render_text_to_image(text, title=title, theme=args.theme)
        output_path = out_dir / f"{txt_file.stem}.png"
        img.save(output_path, "PNG", dpi=(300, 300))

        size_kb = output_path.stat().st_size / 1024
        print(f"✅ {txt_file.name} → {output_path.name} ({img.size[0]}x{img.size[1]}, {size_kb:.1f} KB)")

    print()
    print("🎉 全部完成！PNG 文件已生成。")
    print()
    print("下一步：")
    print("  1. 在知乎编辑器中点击'插入图片'")
    print("  2. 上传生成的 PNG 文件")
    print("  3. 调整图片位置（建议每段正文下方 1 张）")


if __name__ == "__main__":
    main()
