# -*- coding: utf-8 -*-
"""导出测试方案 docx 的正文与表格，便于比较。"""
import io
from docx import Document

SRC = r"C:\Users\a\.dsh\attachments\v1\files\c3\c341aa0bde675f73055f23c40460bc5950858c9e14dda465c39739b13032f7e6\6G确定性承载网集成测试方案（仪表模式与仿真模式）.docx"

doc = Document(SRC)
out = []
out.append("段落数=%d 表格数=%d" % (len(doc.paragraphs), len(doc.tables)))
for i, p in enumerate(doc.paragraphs):
    t = p.text.strip()
    if not t:
        continue
    st = p.style.name if p.style is not None else ""
    out.append("[%03d][%s] %s" % (i, st, t))

for ti, tb in enumerate(doc.tables):
    out.append("\n=== 表%d: %d行 x %d列 ===" % (ti, len(tb.rows), len(tb.columns)))
    for r in tb.rows:
        out.append(" | ".join(c.text.strip()[:40] for c in r.cells))

io.open("testplan.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
