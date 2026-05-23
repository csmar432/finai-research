#!/usr/bin/env python3
"""生成规范三线表Word文档"""
import re
import sys
import os
from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# ── 三线表格式工具 ──────────────────────────────────────────────

def set_cell_border(cell, **kwargs):
    """设置单元格边框。kwargs: top, bottom, left, right, each value is a dict with keys: sz, val, color"""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement('w:tcBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        if edge in kwargs:
            tag = 'w:{}'.format(edge)
            element = OxmlElement(tag)
            for k, v in kwargs[edge].items():
                element.set(qn('w:{}'.format(k)), v)
            tcBorders.append(element)
    tcPr.append(tcBorders)


def set_table_three_line(table):
    """
    将表格设为标准三线表格式：
    - 顶线：1.5pt 黑色实线 (000000)
    - 底线：1.5pt 黑色实线 (000000)
    - 栏目线（表头下）：0.75pt 黑色实线 (000000)
    - 内部：无线（白底）
    """
    # 先获取所有边框，设置为极细（0.5pt）黑色
    tbl = table._tbl
    tblPr = tbl.find(qn('w:tblPr'))
    if tblPr is None:
        tblPr = OxmlElement('w:tblPr')
        tbl.insert(0, tblPr)

    tblBorders = OxmlElement('w:tblBorders')
    for border_name in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
        border = OxmlElement(f'w:{border_name}')
        border.set(qn('w:val'), 'single')
        border.set(qn('w:sz'), '0')       # 最细
        border.set(qn('w:space'), '0')
        border.set(qn('w:color'), 'FFFFFF')  # 白色 = 看不见
        tblBorders.append(border)
    tblPr.append(tblBorders)

    rows = table.rows
    for row_idx, row in enumerate(rows):
        cells = row.cells
        for cell in cells:
            # 设置单元格内部白色填充
            tc = cell._tc
            tcPr = tc.get_or_add_tcPr()
            shd = OxmlElement('w:shd')
            shd.set(qn('w:val'), 'clear')
            shd.set(qn('w:color'), 'auto')
            shd.set(qn('w:fill'), 'FFFFFF')  # 白色背景
            tcPr.append(shd)

            tcBorders = OxmlElement('w:tcBorders')

            if row_idx == 0:
                # 表头行：顶部粗线，底部细线
                for edge in ['top', 'bottom', 'left', 'right']:
                    border = OxmlElement(f'w:{edge}')
                    border.set(qn('w:val'), 'single')
                    border.set(qn('w:sz'), '12')  # 1.5pt ≈ 12 half-pts
                    border.set(qn('w:space'), '0')
                    border.set(qn('w:color'), '000000')
                    tcBorders.append(border)
            elif row_idx == len(rows) - 1:
                # 最后一行：顶部细线，底部粗线
                for edge in ['top', 'bottom', 'left', 'right']:
                    border = OxmlElement(f'w:{edge}')
                    border.set(qn('w:val'), 'single')
                    if edge in ['top', 'bottom']:
                        border.set(qn('w:sz'), '12')
                    else:
                        border.set(qn('w:sz'), '4')  # 0.5pt
                    border.set(qn('w:space'), '0')
                    border.set(qn('w:color'), '000000')
                    tcBorders.append(border)
            else:
                # 中间行：只显示上下细线
                for edge in ['top', 'bottom', 'left', 'right']:
                    border = OxmlElement(f'w:{edge}')
                    border.set(qn('w:val'), 'single')
                    border.set(qn('w:sz'), '4')  # 0.5pt
                    border.set(qn('w:space'), '0')
                    border.set(qn('w:color'), '000000')
                    tcBorders.append(border)

            tcPr.append(tcBorders)


def set_cell_text(cell, text, bold=False, size=10, center=False):
    """设置单元格文本格式"""
    cell.text = ''
    p = cell.paragraphs[0]
    p.clear()
    if center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.font.name = 'Times New Roman'
    run.font.size = Pt(size)
    run.font.bold = bold
    run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')


def set_header_style(cell, text, size=10):
    """表头单元格样式（加粗）"""
    set_cell_text(cell, text, bold=True, size=size, center=True)


def parse_markdown_table(lines):
    """解析Markdown表格，返回 (headers, rows)"""
    # 跳过分隔符行
    data_lines = [l for l in lines if l.strip().startswith('|') and '---' not in l]
    if not data_lines:
        return [], []

    rows = []
    for line in data_lines:
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        rows.append(cells)
    return rows[0], rows[1:]


def md_to_docx(paper_text, output_path):
    doc = Document()

    # ── 页面设置 ──────────────────────────────────────────
    section = doc.sections[0]
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(3.18)
    section.right_margin = Cm(3.18)

    # ── 默认样式 ──────────────────────────────────────────
    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(12)
    style._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')

    # ── 辅助函数 ─────────────────────────────────────────
    def add_title(text, level='main'):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(text)
        run.font.name = 'Times New Roman'
        if level == 'main':
            run.font.size = Pt(18)
            run.bold = True
            run._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
        elif level == 'sub':
            run.font.size = Pt(14)
            run.bold = True
            run._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
        elif level == 'section':
            run.font.size = Pt(14)
            run.bold = True
        elif level == 'subsection':
            run.font.size = Pt(12)
            run.bold = True
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(6)
        return p

    def add_para(text, indent=False):
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.font.name = 'Times New Roman'
        run.font.size = Pt(12)
        run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
        if indent:
            p.paragraph_format.first_line_indent = Pt(24)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = Pt(24)
        return p

    def add_formula(text):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(text)
        run.font.name = 'Times New Roman'
        run.font.size = Pt(11)
        run.italic = True
        run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(6)
        return p

    def add_table_note(text):
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.font.name = 'Times New Roman'
        run.font.size = Pt(9)
        run.italic = True
        run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
        p.paragraph_format.space_after = Pt(6)
        return p

    def add_bullet(text):
        p = doc.add_paragraph(style='List Bullet')
        run = p.add_run(text)
        run.font.name = 'Times New Roman'
        run.font.size = Pt(12)
        run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
        p.paragraph_format.space_after = Pt(3)
        return p

    def insert_table(headers, rows_data):
        """插入三线表"""
        if not rows_data:
            return
        n_cols = len(headers)
        table = doc.add_table(rows=len(rows_data) + 1, cols=n_cols)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER

        # 表头
        for j, h in enumerate(headers):
            set_header_style(table.cell(0, j), h)

        # 数据行
        for i, row_data in enumerate(rows_data):
            for j, val in enumerate(row_data):
                if j < n_cols:
                    center = (j > 0)  # 第一列左对齐，其余居中
                    set_cell_text(table.cell(i + 1, j), val, center=center)

        # 三线表格式
        set_table_three_line(table)
        return table

    def insert_note(note_text):
        """插入表格注释"""
        p = doc.add_paragraph()
        run = p.add_run(note_text)
        run.font.name = 'Times New Roman'
        run.font.size = Pt(9)
        run.italic = True
        run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
        p.paragraph_format.space_after = Pt(12)

    # ── 逐行解析论文 ─────────────────────────────────────
    lines = paper_text.split('\n')
    i = 0
    pending_table = []  # 累积表格行
    in_note = False

    while i < len(lines):
        line = lines[i].strip()

        # ── 检测Markdown表格 ──
        if line.startswith('|'):
            pending_table.append(lines[i])
            i += 1
            continue

        # ── 处理累积的表格 ──
        if pending_table:
            headers, rows_data = parse_markdown_table(pending_table)
            if headers and rows_data:
                insert_table(headers, rows_data)
                # 找注释（在表注释行或下一个非空行）
                if i < len(lines) and lines[i].strip().startswith('*注：'):
                    note_text = lines[i].strip().lstrip('*')
                    insert_note(note_text)
                    i += 1
                else:
                    # 跳过空行
                    while i < len(lines) and not lines[i].strip():
                        i += 1
                    if i < len(lines) and lines[i].strip().startswith('*注：'):
                        note_text = lines[i].strip().lstrip('*')
                        insert_note(note_text)
                        i += 1
                    else:
                        doc.add_paragraph()  # 空行
            pending_table = []
            continue

        # ── 检测表格注释 ──
        if line.startswith('*注：'):
            note_text = line.lstrip('*')
            insert_note(note_text)
            i += 1
            continue

        # ── 分隔线 ──
        if line == '---':
            i += 1
            continue

        # ── 一级标题（论文标题） ──
        if line.startswith('# '):
            text = line[2:].strip()
            if text:
                add_title(text, 'main')
        # ── 英文标题 ──
        elif line.startswith('## ') and not line[3:].strip().startswith('**'):
            text = line[3:].strip()
            if text and not text.startswith('表'):
                add_title(text, 'sub')
        # ── 二级标题 ──
        elif line.startswith('### '):
            text = line[4:].strip()
            if text:
                # 跳过表标题
                if text.startswith('表'):
                    # 后面会跟表格
                    i += 1
                    continue
                add_title(text, 'section')
        # ── 三级标题 ──
        elif line.startswith('#### '):
            text = line[5:].strip()
            if text:
                add_title(text, 'subsection')
        # ── 加粗标题行（如 **表1：xxx**） ──
        elif line.startswith('**') and line.endswith('**') and '表' in line:
            # 表格标题已在上方处理
            pass
        # ── 无序列表 ──
        elif line.startswith('- '):
            text = line[2:]
            # 处理粗体
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            add_bullet(text)
        # ── 有序列表 ──
        elif re.match(r'^\d+\.', line):
            text = re.sub(r'^\d+\.\s*', '', line)
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            p = doc.add_paragraph()
            run = p.add_run(text)
            run.font.name = 'Times New Roman'
            run.font.size = Pt(12)
            run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
            p.paragraph_format.left_indent = Inches(0.25)
            p.paragraph_format.space_after = Pt(3)
        # ── LaTeX公式块（$$...$$，单行或多行） ──
        elif '$$' in line:
            # 收集完整公式块
            formula_parts = []
            remaining = line
            while True:
                start = remaining.find('$$')
                if start == -1:
                    formula_parts.append(remaining)
                    break
                end = remaining.find('$$', start + 2)
                if end == -1:
                    # 未闭合的 $$，收尾
                    formula_parts.append(remaining)
                    break
                # 找到了成对 $$，收集并继续
                formula_parts.append(remaining[start:end + 2])
                remaining = remaining[end + 2:]
            # 找下一行是否还有内容（多行公式）
            multi_lines = []
            if i + 1 < len(lines) and '$$' not in line:
                # 多行：收集直到遇到单独的 $$
                i += 1
                while i < len(lines):
                    next_line = lines[i].strip()
                    if next_line == '$$':
                        i += 1  # 跳过结束$$
                        break
                    if '$$' in next_line:
                        # 同行的结束符
                        formula_parts.append(next_line)
                        break
                    multi_lines.append(next_line)
                    i += 1
            raw = ''.join(formula_parts)
            formula_text = raw.strip()[2:-2].strip()
            if multi_lines:
                formula_text = raw[2:].strip() + '\n' + '\n'.join(multi_lines)
            add_formula(formula_text)
        # ── LaTeX环境（\begin...\end） ──
        elif '\\begin{' in line:
            env_lines = [line]
            brace_depth = line.count('{') - line.count('}')
            while brace_depth > 0 and i + 1 < len(lines):
                i += 1
                l = lines[i].strip()
                env_lines.append(l)
                brace_depth += l.count('{') - l.count('}')
            add_formula('\n'.join(env_lines))
        # ── 参考文献标题 ──
        elif line.startswith('### 参考文献') or line == '参考文献':
            p = doc.add_paragraph()
            run = p.add_run('参考文献')
            run.font.name = 'Times New Roman'
            run.font.size = Pt(14)
            run.bold = True
            run._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
            p.paragraph_format.space_before = Pt(12)
            p.paragraph_format.space_after = Pt(6)
        # ── 参考文献条目 ──
        elif re.match(r'^\d+\.', line) and '(' in line:
            # 参考文献格式
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.25)
            p.paragraph_format.first_line_indent = Inches(-0.25)
            run = p.add_run(line[line.index('.') + 1:].strip())
            run.font.name = 'Times New Roman'
            run.font.size = Pt(10)
            run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
            p.paragraph_format.space_after = Pt(4)
        # ── 普通段落 ──
        elif line:
            clean = line
            # 处理行内公式 $...$
            if '$' in clean and '$$' not in clean:
                parts = re.split(r'((?<!\\)\$[^$\n]+?\$)', clean)
                p = doc.add_paragraph()
                for part in parts:
                    if re.match(r'(?<!\\)\$[^$\n]+?\$', part):
                        r = p.add_run(part)
                        r.font.name = 'Times New Roman'
                        r.font.size = Pt(11)
                        r.italic = True
                        r._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
                    else:
                        r = p.add_run(part)
                        r.font.name = 'Times New Roman'
                        r.font.size = Pt(12)
                        r._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
                p.paragraph_format.space_after = Pt(6)
                p.paragraph_format.line_spacing = Pt(24)
            elif '$$' in clean:
                parts = re.split(r'(\$\$[^$]*?\$\$)', clean)
                p = doc.add_paragraph()
                for part in parts:
                    if part.startswith('$$') and part.endswith('$$'):
                        r = p.add_run(part)
                        r.font.name = 'Times New Roman'
                        r.font.size = Pt(11)
                        r.italic = True
                        r._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
                    else:
                        r = p.add_run(part)
                        r.font.name = 'Times New Roman'
                        r.font.size = Pt(12)
                        r._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
                p.paragraph_format.space_after = Pt(6)
                p.paragraph_format.line_spacing = Pt(24)
            else:
                p = add_para(clean)

        i += 1

    # 处理末尾可能残留的表格
    if pending_table:
        headers, rows_data = parse_markdown_table(pending_table)
        if headers and rows_data:
            insert_table(headers, rows_data)

    doc.save(output_path)
    print(f"✅ Word文档已保存: {output_path}")


# ── 主程序 ─────────────────────────────────────────────────
# GATED: matching_files = sorted((Path(__file__).parent.parent / "output").glob('关税政策影响研究_去AI版_*.md'))
if not matching_files:
    print("❌ 未找到匹配的论文文件: output/关税政策影响研究_去AI版_*.md")
    print("   请先生成去AI润色版论文，或修改文件名匹配模式。")
    sys.exit(1)
paper_file = matching_files[-1]
paper_text = paper_file.read_text(encoding='utf-8')

output_file = Path(__file__).parent.parent / "output/关税政策影响研究_三线表版.docx"
md_to_docx(paper_text, str(output_file))

print(f"\n生成完成！文件: {output_file}")
print(f"论文字数: {len(paper_text)} 字")
