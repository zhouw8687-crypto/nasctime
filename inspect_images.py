# -*- coding: utf-8 -*-
"""检查 -modbyzp(1) 文档中图片的位置与大小，便于原位替换。"""
import os
from docx import Document
from docx.shared import Emu

D = r"D:\aaaLab\6g确定性网络"
cand = [f for f in os.listdir(D) if f.endswith("-modbyzp(1).docx")]
src = os.path.join(D, cand[0])
doc = Document(src)

out = []
# 图片部件
for rid, rel in doc.part.rels.items():
    if "image" in rel.reltype:
        blob = rel.target_part.blob
        out.append("rel %s  %s  %d KB" % (rid, rel.target_part.partname, len(blob) // 1024))

out.append("\n段落中的内联图片：")
for i, p in enumerate(doc.paragraphs):
    xml = p._element.xml
    if "graphic" in xml or "blip" in xml:
        # 找 blip embed
        import re
        m = re.findall(r'r:embed="([^"]+)"', xml)
        out.append("[%03d] 图片 rel=%s 文字=%s" % (i, ",".join(m), p.text.strip()[:30]))

open("report_images.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
