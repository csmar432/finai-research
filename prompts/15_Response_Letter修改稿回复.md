# 【模板15】Response Letter 修改稿回复信

## 工作流说明

根据审稿意见，逐条生成专业、有建设性的回复信（Rebuttal）。

---

## 使用方法

---

```
请帮我生成 Response Letter：

## 论文标题
[你的论文标题]

## 审稿意见
[粘贴全部审稿意见原文]

## 论文摘要（可选）
[粘贴摘要]
```

---

## 脚本命令

```bash
# 生成 Response Letter
python scripts/paper_cover_letter.py output/paper.md --type response --reviews "审稿人1: ... 审稿人2: ..." --save

# 同时生成 Cover + Response
python scripts/paper_cover_letter.py output/paper.md --type both --venue "NeurIPS" --save
```

---

## 生成的文件

| 文件 | 位置 |
|------|------|
| 回复信 | `output/response_letter_YYYYMMDD.txt` |

---

## Response Letter 写作要点

### 回复策略

| 审稿意见类型 | 策略 |
|---|---|
| Major（主要问题） | 必须认真修改，补充实验或分析 |
| Minor（次要问题） | 尽量修改，无法修改的需礼貌解释 |
| Suggestion（建议） | 感谢接受，说明是否采纳 |

### 语言规范

- **感谢审稿人**："Thank you for this insightful comment."
- **同意修改**："We agree with the reviewer that..."
- **不同意时**："We respectfully disagree because..."（提供证据）
- **避免**："This is wrong" / "The reviewer is incorrect"

### 回复结构

```
Reviewer #X: [意见标题]
> [引用原文]

Response: We thank the reviewer for this comment.
[是否同意 → 修改了什么/为什么不改]
As shown in Section 3.2, ...
```

---

## 注意事项

- 绝对不要 defensive 或 confrontational
- 所有修改都要有对应章节引用
- 补充实验记得加入 supplementary
- 保持礼貌，即使审稿意见不公
