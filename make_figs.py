# -*- coding: utf-8 -*-
"""生成报告用的仿真拓扑与指标对比图（PNG）。"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figs")
os.makedirs(OUT, exist_ok=True)


def box(ax, x, y, w, h, text, fc="#EAF1FB", ec="#2F5597", fs=9, bold=False):
    p = FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                       boxstyle="round,pad=0.02,rounding_size=0.06",
                       linewidth=1.2, edgecolor=ec, facecolor=fc)
    ax.add_patch(p)
    ax.text(x, y, text, ha="center", va="center", fontsize=fs,
            fontweight="bold" if bold else "normal", color="#1F2A37", zorder=5)


def link(ax, p1, p2, style="-", color="#5B6B84", lw=1.3, text=None, dy=0.12):
    ax.plot([p1[0], p2[0]], [p1[1], p2[1]], style, color=color, lw=lw, zorder=1)
    if text:
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        ax.text(mx, my + dy, text, ha="center", va="bottom", fontsize=7.5, color="#44546A")


def canvas(w=10, h=5.2):
    fig, ax = plt.subplots(figsize=(w, h), dpi=200)
    ax.set_xlim(0, 10)
    ax.axis("off")
    return fig, ax


def save(fig, name):
    fig.tight_layout()
    path = os.path.join(OUT, name)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# ---------------------------------------------------------------- 图1 三层架构
def fig_arch():
    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=200)
    ax.set_xlim(0, 10); ax.set_ylim(0, 6); ax.axis("off")

    layers = [
        (4.55, "集成控制层  跨域控制与资源协同", "#E8F0FE", "#2F5597"),
        (2.95, "集成物理层  接口协议与时间同步", "#E6F4EA", "#2E7D32"),
        (1.35, "模拟业务层  性能检测与状态反馈", "#FFF4E5", "#B26A00"),
    ]
    for y, title, fc, ec in layers:
        ax.add_patch(FancyBboxPatch((0.15, y - 0.5), 9.7, 1.0,
                                    boxstyle="round,pad=0.02,rounding_size=0.05",
                                    linewidth=1.4, edgecolor=ec, facecolor=fc, alpha=0.55))
        ax.text(0.3, y + 0.68, title, fontsize=9.5, fontweight="bold", color=ec)

    puts = [
        (1.5, "全局控制器"), (3.3, "本地控制器"), (5.1, "无线侧短时\n尺度控制器"),
        (6.9, "有线侧长时\n尺度控制器"), (8.6, "意图→预算\n分解"),
    ]
    for x, t in puts:
        box(ax, x, 4.55, 1.55, 0.62, t, fc="#FFFFFF", fs=8)

    mid = [(1.5, "6G 模拟空口"), (3.4, "确定性承载网\n(PE + Qbv)"),
           (5.5, "6G 模拟核心网"), (7.6, "SyncE + PTP"), (9.0, "边界/透明\n时钟")]
    for x, t in mid:
        box(ax, x, 2.95, 1.75, 0.62, t, fc="#FFFFFF", fs=8)

    low = [(1.6, "业务模拟"), (3.3, "场景构建"), (5.0, "资源管理"),
           (6.7, "数据采集"), (8.4, "指标评估")]
    for x, t in low:
        box(ax, x, 1.35, 1.55, 0.62, t, fc="#FFFFFF", fs=8)

    for x in [1.5, 3.3, 5.1, 6.9, 8.6]:
        ax.annotate("", xy=(x, 3.3), xytext=(x, 4.2),
                    arrowprops=dict(arrowstyle="->", color="#2F5597", lw=1.1))
    for x in [1.5, 3.4, 5.5, 7.6]:
        ax.annotate("", xy=(x, 1.72), xytext=(x, 2.6),
                    arrowprops=dict(arrowstyle="->", color="#2E7D32", lw=1.1))
    ax.annotate("", xy=(9.35, 1.1), xytext=(0.55, 1.1),
                arrowprops=dict(arrowstyle="->", color="#B26A00", lw=1.3,
                                connectionstyle="arc3,rad=0.12"))
    ax.text(5.0, 0.42, "状态感知 → 策略决策 → 资源编排 → 控制执行（闭环，闭环响应 ≤100 ms）",
            ha="center", fontsize=8.5, color="#B26A00")
    return save(fig, "fig1_arch.png")


# ---------------------------------------------------------------- 图2 无线接入
def fig_ran():
    fig, ax = canvas(9, 4.2)
    ax.set_ylim(0, 4.2)
    box(ax, 1.2, 2.1, 1.7, 0.7, "UE（NrUe）", fs=9)
    box(ax, 3.4, 2.1, 1.9, 0.7, "gNodeB\n(Simu5G)", fs=9)
    box(ax, 5.7, 2.1, 1.6, 0.7, "I-UPF", fs=9)
    box(ax, 7.6, 2.1, 1.4, 0.7, "UPF", fs=9)
    box(ax, 9.2, 2.1, 1.3, 0.7, "Server", fs=9)
    for a, b in [((1.2, 2.1), (3.4, 2.1)), ((3.4, 2.1), (5.7, 2.1)),
                 ((5.7, 2.1), (7.6, 2.1)), ((7.6, 2.1), (9.2, 2.1))]:
        link(ax, a, b)
    ax.text(2.3, 2.45, "NR 空口", ha="center", fontsize=8, color="#C00000")
    ax.text(4.55, 2.45, "N3 (GTP-U)", ha="center", fontsize=8, color="#2F5597")
    ax.text(6.65, 2.45, "N3", ha="center", fontsize=8, color="#2F5597")
    ax.text(8.4, 2.45, "N6", ha="center", fontsize=8, color="#2E7D32")
    ax.text(5.2, 1.1,
            "下行 server→UE：4.54 ms（p99 4.49 ms）\n上行 UE→server：21.36 ms（p99 32.27 ms）",
            ha="center", fontsize=9.5,
            bbox=dict(boxstyle="round,pad=0.35", fc="#F5F7FA", ec="#BFC8D6"))
    return save(fig, "fig2_ran.png")


# ---------------------------------------------------------------- 图3 PE 承载
def fig_pe():
    fig, ax = canvas(9.6, 4.6)
    ax.set_ylim(0, 4.6)
    box(ax, 0.95, 3.1, 1.5, 0.62, "client1\n(BE)", fs=8.5, fc="#F2F2F2")
    box(ax, 0.95, 1.7, 1.5, 0.62, "client2\n(HP)", fs=8.5, fc="#E8F0FE")
    box(ax, 3.1, 2.4, 1.5, 0.7, "PE1\n(TsnSwitch)", fs=8.5)
    box(ax, 5.3, 2.4, 1.5, 0.7, "PE2\n(TsnSwitch)", fs=8.5)
    box(ax, 7.5, 2.4, 1.6, 0.7, "Server", fs=9)
    link(ax, (0.95, 3.1), (3.1, 2.6))
    link(ax, (0.95, 1.7), (3.1, 2.2))
    link(ax, (3.1, 2.4), (5.3, 2.4), text="100 Mbps")
    link(ax, (5.3, 2.4), (7.5, 2.4))
    ax.text(5.3, 3.35, "802.1Qbv 门控：周期 1 ms，class1 独占 200 µs",
            ha="center", fontsize=9, color="#2F5597", fontweight="bold")
    ax.plot([4.3, 6.3], [3.05, 3.05], color="#2F5597", lw=2)
    ax.text(7.55, 1.35, "无门控：均值 132.20 µs，峰峰 254.5 µs（15.6×）\n"
                        "有门控：均值 499.63 µs，峰峰 120.6 µs（1.28×）",
            ha="center", fontsize=8.5,
            bbox=dict(boxstyle="round,pad=0.35", fc="#F5F7FA", ec="#BFC8D6"))
    return save(fig, "fig3_pe.png")


# ---------------------------------------------------------------- 图4 MPLS 承载
def fig_mpls():
    fig, ax = canvas(10, 5.0)
    ax.set_ylim(0, 5.0)
    pos = {
        "host1": (0.8, 4.2), "host2": (0.8, 3.4), "host5": (0.8, 2.6),
        "LSR1": (2.6, 3.4), "LSR2": (4.3, 4.3), "LSR3": (4.3, 2.6),
        "LSR4": (6.0, 3.6), "LSR6": (6.0, 4.6), "LSR7": (6.0, 2.0),
        "LSR5": (7.7, 3.2), "host3": (9.4, 3.6), "host4": (9.4, 2.8),
    }
    for n, (x, y) in pos.items():
        fc = "#FFF4E5" if n.startswith("LSR") else "#EAF1FB"
        box(ax, x, y, 0.95, 0.5, n, fs=8, fc=fc)
    edges = [("host1", "LSR1", "10 ms"), ("host2", "LSR1", "10 ms"), ("host5", "LSR1", "10 ms"),
             ("LSR1", "LSR2", "15 ms"), ("LSR1", "LSR3", "5 ms"),
             ("LSR2", "LSR4", "5 ms"), ("LSR3", "LSR4", "5 ms"),
             ("LSR2", "LSR6", "10 ms"), ("LSR6", "LSR5", "10 ms"),
             ("LSR3", "LSR7", "10 ms"), ("LSR7", "LSR5", "10 ms"),
             ("LSR4", "LSR5", "5 ms"), ("LSR5", "host3", "10 ms"), ("LSR5", "host4", "10 ms")]
    for a, b, t in edges:
        link(ax, pos[a], pos[b], text=t, dy=0.08)
    ax.plot([2.6, 4.3], [3.4, 4.3], color="#C00000", lw=2.4, zorder=3)
    ax.plot([4.3, 6.0], [4.3, 3.6], color="#C00000", lw=2.4, zorder=3)
    ax.text(5.0, 0.9, "红色为 LSP 显式路径：LSR1→LSR2（15 ms 长链路）→LSR4→LSR5\n"
                      "LSP 生效 80.88 ms，关闭 FEC 分类后 55.90 ms（差 24.98 ms）",
            ha="center", fontsize=8.5,
            bbox=dict(boxstyle="round,pad=0.35", fc="#F5F7FA", ec="#BFC8D6"))
    return save(fig, "fig4_mpls.png")


# ---------------------------------------------------------------- 图5 核心网
def fig_core():
    fig, ax = canvas(9, 3.6)
    ax.set_ylim(0, 3.6)
    box(ax, 1.1, 1.9, 1.6, 0.65, "hostA\n(接入侧代理)", fs=8.5)
    box(ax, 3.4, 1.9, 1.5, 0.65, "I-UPF", fs=9)
    box(ax, 5.6, 1.9, 1.5, 0.65, "UPF", fs=9)
    box(ax, 7.9, 1.9, 1.5, 0.65, "Server", fs=9)
    link(ax, (1.1, 1.9), (3.4, 1.9), text="10 Gbps")
    link(ax, (3.4, 1.9), (5.6, 1.9))
    link(ax, (5.6, 1.9), (7.9, 1.9), text="N6")
    ax.text(4.5, 1.05, "299/299（100%），端到端平均 0.71 µs",
            ha="center", fontsize=9,
            bbox=dict(boxstyle="round,pad=0.35", fc="#F5F7FA", ec="#BFC8D6"))
    return save(fig, "fig5_core.png")


# ---------------------------------------------------------------- 图6 端到端
def fig_e2e():
    fig, ax = plt.subplots(figsize=(10, 5.0), dpi=200)
    ax.set_xlim(0, 10); ax.set_ylim(0, 5); ax.axis("off")

    box(ax, 1.0, 4.05, 1.6, 0.6, "UE（NrUe）", fs=8.5)
    box(ax, 3.0, 4.05, 1.6, 0.6, "gNodeB", fs=8.5)
    box(ax, 4.8, 3.35, 1.4, 0.55, "N3 路由", fs=8)
    box(ax, 4.8, 2.45, 1.4, 0.55, "边缘分类\n(N3Edge)", fs=7.5)

    box(ax, 1.0, 1.25, 1.6, 0.6, "有线终端", fs=8.5)
    box(ax, 2.9, 1.25, 1.5, 0.6, "边缘交换机", fs=8.5)

    box(ax, 6.4, 2.45, 1.3, 0.62, "PE1", fs=8.5)
    box(ax, 7.8, 2.45, 1.3, 0.62, "PE2", fs=8.5)
    box(ax, 9.2, 2.45, 1.3, 0.62, "PE3", fs=8.5)
    box(ax, 9.2, 1.25, 1.5, 0.6, "UPF", fs=8.5)
    box(ax, 9.2, 3.8, 1.5, 0.55, "Server", fs=8.5)

    link(ax, (1.0, 4.05), (3.0, 4.05), text="NR")
    link(ax, (3.0, 4.05), (4.8, 3.35), text="N3")
    link(ax, (4.8, 3.35), (4.8, 2.45))
    link(ax, (1.0, 1.25), (2.9, 1.25))
    link(ax, (2.9, 1.25), (4.8, 2.45))
    link(ax, (4.8, 2.45), (6.4, 2.45))
    link(ax, (6.4, 2.45), (7.8, 2.45), text="100 Mbps")
    link(ax, (7.8, 2.45), (9.2, 2.45))
    link(ax, (9.2, 2.45), (9.2, 3.8))
    link(ax, (9.2, 2.45), (9.2, 1.25))
    ax.text(5.6, 0.45, "承载段带 802.1Qbv 门控；无线下行 4.54 ms、上行 21.36 ms；有线 112.91 µs",
            ha="center", fontsize=8.5,
            bbox=dict(boxstyle="round,pad=0.3", fc="#F5F7FA", ec="#BFC8D6"))
    return save(fig, "fig6_e2e.png")


# ---------------------------------------------------------------- 图7 门控对比
def fig_gating():
    fig, ax = plt.subplots(figsize=(7.6, 4.0), dpi=200)
    labels = ["均值", "最小值", "最大值"]
    nog = [132.20, 17.43, 271.95]
    gat = [499.63, 432.97, 553.61]
    x = range(len(labels))
    w = 0.36
    b1 = ax.bar([i - w / 2 for i in x], nog, w, label="无门控", color="#9DB4D6")
    b2 = ax.bar([i + w / 2 for i in x], gat, w, label="Qbv 门控", color="#2F5597")
    for bars in (b1, b2):
        for r in bars:
            ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 8,
                    f"{r.get_height():.1f}", ha="center", fontsize=8)
    ax.set_xticks(list(x)); ax.set_xticklabels(labels)
    ax.set_ylabel("高优先级流端到端时延（µs）")
    ax.set_title("图 802.1Qbv 门控前后高优先级流时延对比（样本 1000/999）", fontsize=10)
    ax.legend(); ax.grid(axis="y", ls=":", alpha=0.5)
    return save(fig, "fig7_gating.png")


# ---------------------------------------------------------------- 图8 上下行
def fig_updown():
    fig, ax = plt.subplots(figsize=(7.6, 4.0), dpi=200)
    names = ["有线\nhost→server", "无线上行\nUE→server", "无线下行\nserver→UE"]
    means = [0.1129, 21.359, 4.537]
    p99 = [0.368, 32.273, 4.492]
    x = range(len(names))
    ax.bar([i - 0.18 for i in x], means, 0.36, label="均值", color="#2F5597")
    ax.bar([i + 0.18 for i in x], p99, 0.36, label="P99", color="#9DB4D6")
    for i, (m, p) in enumerate(zip(means, p99)):
        ax.text(i - 0.18, m + 0.4, f"{m:.2f}", ha="center", fontsize=8)
        ax.text(i + 0.18, p + 0.4, f"{p:.2f}", ha="center", fontsize=8)
    ax.set_xticks(list(x)); ax.set_xticklabels(names)
    ax.set_ylabel("端到端时延（ms）")
    ax.set_title("三类接入的端到端时延对比（同一场景、同一时刻）", fontsize=10)
    ax.legend(); ax.grid(axis="y", ls=":", alpha=0.5)
    return save(fig, "fig8_updown.png")


if __name__ == "__main__":
    for f in [fig_arch, fig_ran, fig_pe, fig_mpls, fig_core, fig_e2e, fig_gating, fig_updown]:
        print(f())
