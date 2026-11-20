# -*- coding: utf-8 -*-
"""把附件 docx 的段落大纲导出为 UTF-8 文本，供后续阅读。"""
from docx import Document

SRC = r"C:\Users\a\.dsh\attachments\v1\files\aa\aac03c5a8e20aee9d176ebae455416163886fefaee5b2b9ea52b743da34e0ad4\附件-国家科技重大专项年度执行情况报告_课题五20261017.docx"
OUT = r"C:\Users\a\.dsh\remote-workspaces\wmv4mdfl29ql5\report_outline.txt"

doc = Document(SRC)
lines = []
lines.append("段落总数: %d" % len(doc.paragraphs))
for i, p in enumerate(doc.paragraphs):
    t = p.text.strip()
    if not t:
        continue
    style = p.style.name if p.style is not None else ""
    lines.append("[%03d][%s] %s" % (i, style, t))

# 表格
lines.append("\n表格数: %d" % len(doc.tables))
for ti, tb in enumerate(doc.tables):
    lines.append("--- 表 %d: %d 行 x %d 列" % (ti, len(tb.rows), len(tb.columns)))
    for r in tb.rows[:4]:
        lines.append("  | " + " | ".join(c.text.strip()[:30] for c in r.cells))

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("written", OUT)
