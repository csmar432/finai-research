# 【模板14】Cover Letter 投稿附信

## 工作流说明

根据论文信息，自动生成符合学术期刊/会议规范的 Cover Letter。

---

## 使用方法

---

```
请帮我生成 Cover Letter：

## 论文标题
[你的论文标题]

## 作者列表
[格式：姓，名；姓，名；通讯作者用 * 标注]

## 目标期刊/会议
[例如：NeurIPS 2026, JFE, Nature Machine Intelligence]

## 论文摘要（可选）
[粘贴摘要，或让 AI 从论文中提取]
```

---

## 脚本命令

```bash
# 生成 Cover Letter
python scripts/paper_cover_letter.py output/paper.md --type cover --venue "NeurIPS" --save

# 指定作者
python scripts/paper_cover_letter.py output/paper.md --type cover --venue "ICML" --authors "张三,李四,王五" --save
```

---

## 生成的文件

| 文件 | 位置 |
|------|------|
| 投稿附信 | `output/cover_letter_YYYYMMDD.txt` |

---

## Cover Letter 写作要点

1. **主动联系** — 第一段声明原创性和未一稿多投
2. **核心贡献** — 用 1-2 句话强调 novelty 和 impact（不是摘要）
3. **合规声明** — 利益冲突、作者同意、arXiv 发布状态
4. **礼貌结尾** — 感谢考虑，表达期待

---

## 注意事项

- 生成后请填入真实作者信息和编辑姓名
- 检查是否需要伦理审查声明
- 通讯作者联系方式要准确
