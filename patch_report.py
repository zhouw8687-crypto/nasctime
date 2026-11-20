# -*- coding: utf-8 -*-
"""在用户修改版 docx 上，把端到端集成章节改成“日”字形双基站场景。

只改必要处：2.1 场景数、2.2 接入描述、2.6 全节文字、表7、图8。
其余内容（含附件1 照片、用户措辞）原样保留。
"""
import os
import shutil
from docx import Document
from docx.shared import Pt, Cm
from docx.oxml.ns import qn

SRC_DIR = r"D:\aaaLab\6g确定性网络"
src_name = [f for f in os.listdir(SRC_DIR) if f.endswith("-modbyzp(1).docx")][0]
src = os.path.join(SRC_DIR, src_name)
dst = os.path.join(SRC_DIR, "2_项目年度重要进展及成果的详细介绍-日字形.docx")
work = "report_ladder.docx"
shutil.copy2(src, work)

doc = Document(work)


def set_para(p, text):
    """替换段落文字，保留首个 run 的字体设置与段落格式。"""
    runs = list(p.runs)
    size = runs[0].font.size if runs else Pt(12)
    bold = runs[0].font.bold if runs else False
    for r in runs:
        r._element.getparent().remove(r._element)
    r = p.add_run(text)
    r.font.size = size if size else Pt(12)
    r.font.bold = bold
    r.font.name = "Times New Roman"
    rpr = r._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), "宋体")


def find_para(keyword):
    for p in doc.paragraphs:
        if keyword in p.text:
            return p
    return None


NEW = {
    # 2.1 场景数量
    "四个验证单元共形成 9 个可运行场景": (
        "截至本年度末，四个验证单元共形成 10 个可运行场景，覆盖无线接入、二层冗余、三层流量工程、"
        "承载门控、故障倒换、核心网用户面，以及链式与“日”字形两种端到端集成形态，"
        "形成覆盖无线、承载、核心、端到端四个层面的实测指标库。在此过程中同步沉淀了指标解析工具链，"
        "支持从仿真输出中自动提取交付率、分位数、抖动峰峰值、中断持续时间等指标，"
        "并支持门控开/关、显式路径开/关等对照实验的批量执行与一致性比对，"
        "为后续大规模参数扫描与智能化优化提供数据基础。"),

    # 2.2 接入描述：去掉“有线终端接入”
    "无线接入、有线终端接入与核心网均作为挂载单元接入承载域": (
        "据此，本年度将时间敏感定位为确定性承载设备（PE）的内置能力，而非独立验证域，"
        "确立了“承载为中心、多接入挂载”的架构：无线接入与核心网均作为挂载单元接入承载域，"
        "有线侧的测试仪表仅作为参考拓扑中的示意，未纳入仿真建模。端到端拓扑如图 2 所示，"
        "承载网采用“日”字形六节点结构，核心网双归顶部两个节点，两台基站分别接入底部两个节点。"
        "这一判断纠正了前期将时间敏感视为独立接入域的路线偏差，避免了重复建设，"
        "也使验证模型与任务书口径保持一致。"),

    # 2.6 小节标题
    "2.6 端到端集成验证": "2.6 端到端集成验证（“日”字形承载网）",

    # 2.6 拓扑描述
    "端到端集成域将无线接入、有线终端接入": (
        "端到端集成域按“日”字形承载网装配：两台基站分别接入承载网底部的 NE5、NE6，"
        "经日字形路由上行至顶部的 NE1、NE2，再双归接入核心网锚点用户面功能，最终到达数据网服务器，"
        "拓扑如图 2 所示。集成域的核心验证目标有两个：一是确认多基站、多级路由拼接后不引入额外时延；"
        "二是量化两个基站、两个方向上的确定性表现是否一致。"),

    # 2.6 测试方法
    "测试方法如下。在同一场景、同一时刻同时运行三条业务流": (
        "测试方法如下。两台基站各下挂一个终端，终端通过服务节点编号分别绑定 1 号与 2 号基站；"
        "每个终端与服务器之间同时运行一条上行、一条下行业务，共四条流，均为 200 字节、"
        "10 ms 周期的 UDP 报文，便于横向比较；承载网各链路速率统一为 100 Mbps，"
        "仿真时长 6 s，业务从第 2 s 开始，避开终端入网与路由收敛的瞬态过程；"
        "四条流在接收端按不同端口分别采集，避免相互混叠。"),

    # 表7 标题
    "表 7  端到端集成验证指标（3 s，同一场景同时运行）":
        "表 7  端到端集成验证指标（6 s，两台基站同时运行）",

    # 图8 标题
    "图 8  三类接入的端到端时延对比": "图 8  两台基站的上、下行端到端时延对比",

    # 2.6 结论一
    "集成验证得到两项关键结论。第一，多域拼接未引入额外时延": (
        "集成验证得到两项关键结论。第一，多级路由拼接未引入额外时延。日字形场景下无线下行端到端时延为 "
        "5.00 ms，与单域验证的 4.54 ms 处于同一量级，差异来自承载网新增的两跳路由；"
        "两台基站的指标完全一致（上行均为 20.29 ms、下行均为 5.00 ms），"
        "说明承载网的负载分担与路由选择对称，未出现某一侧拥塞。这表明承载段对时延的贡献仍在微秒量级，"
        "集成方法本身是“无损”的，后续可将集成域作为可信的端到端评价平台。"),

    # 2.6 结论二
    "第二，不同接入方式的确定性差异显著": (
        "第二，上、下行方向的确定性差异在双基站场景下稳定复现。四条流的上行时延均为 20.29 ms、"
        "下行均为 5.00 ms，上行约为下行的 4 倍，与单域实验结论一致。"
        "该差异与承载网拓扑无关——拓扑由链式改为日字形后，上、下行指标基本不变，"
        "进一步确认瓶颈位于 NR 上行调度环节，而非承载段或核心网段。"),

    # 2.6 结论三
    "上述结论对后续技术路线的优先级排序": (
        "上述结论对后续技术路线具有指导意义：承载网侧已具备亚毫秒级、低抖动的确定性能力，"
        "且在多跳、双归结构下仍保持稳定，继续增强承载能力的边际收益有限；"
        "提升端到端确定性的关键在于空口调度优化与跨域协同机制，应作为下一年度资源投入的重点方向。"),
}

for key, newtext in NEW.items():
    p = find_para(key)
    if p is None:
        print("!! 未找到:", key[:24])
        continue
    set_para(p, newtext)
    print("已改:", key[:24])

# ---------------- 表7：改写为四条流 ----------------
tb = doc.tables[6]
header = ["业务流", "承载路径", "发送/接收", "均值", "P99"]
rows = [
    ["上行 ue[0]→server", "gnb1–NE5–NE3–NE1–UPF", "401 / 399", "20.29 ms", "32.06 ms"],
    ["上行 ue[1]→server", "gnb2–NE6–NE4–NE2–UPF", "401 / 399", "20.29 ms", "32.06 ms"],
    ["下行 server→ue[0]", "UPF–NE1–NE3–NE5–gnb1", "401 / 400", "5.00 ms", "4.95 ms"],
    ["下行 server→ue[1]", "UPF–NE2–NE4–NE6–gnb2", "401 / 400", "5.00 ms", "4.95 ms"],
]
# 补齐行数
while len(tb.rows) < 1 + len(rows):
    tb.add_row()
for ci, txt in enumerate(header):
    cell = tb.rows[0].cells[ci]
    cell.text = ""
    r = cell.paragraphs[0].add_run(txt)
    r.font.bold = True
    r.font.size = Pt(9.5)
    r.font.name = "Times New Roman"
for ri, row in enumerate(rows, start=1):
    for ci, txt in enumerate(row):
        cell = tb.rows[ri].cells[ci]
        cell.text = ""
        r = cell.paragraphs[0].add_run(txt)
        r.font.size = Pt(9.5)
        r.font.name = "Times New Roman"
print("表7 已改写")

# ---------------- 图8：替换图片 ----------------
blip_rid = None
for rid, rel in doc.part.rels.items():
    if "image" in rel.reltype and str(rel.target_part.partname).endswith("image8.png"):
        blip_rid = rid
if blip_rid:
    part = doc.part.related_parts[blip_rid]
    with open("fig8_ladder.png", "rb") as f:
        part._blob = f.read()
    print("图8 已替换")
else:
    print("!! 未找到 image8.png")

doc.save(work)
shutil.copy2(work, dst)
print("saved:", dst, os.path.getsize(dst) // 1024, "KB")
