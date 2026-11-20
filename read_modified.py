# -*- coding: utf-8 -*-
"""导出 -modbyzp(1) 版本的段落大纲与正文，供对比。"""
import os
from docx import Document

D = r"D:\aaaLab\6g确定性网络"
cand = [f for f in os.listdir(D) if f.endswith("-modbyzp(1).docx")]
src = os.path.join(D, cand[0])
doc = Document(src)

out = []
out.append("文件: %s  段落数=%d 表格数=%d" % (cand[0], len(doc.paragraphs), len(doc.tables)))
for i, p in enumerate(doc.paragraphs):
    t = p.text.strip()
    if not t:
        continue
    style = p.style.name if p.style is not None else ""
    out.append("[%03d][%s] %s" % (i, style, t))

for ti, tb in enumerate(doc.tables):
    out.append("--- 表%d: %d行 x %d列" % (ti, len(tb.rows), len(tb.columns)))
    for r in tb.rows[:3]:
        out.append("   | " + " | ".join(c.text.strip()[:24] for c in r.cells))

open("report_modified.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok", cand[0])
