# -*- coding: utf-8 -*-
"""生成日字形双基站场景的图8：两台基站的上下行时延对比。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

fig, ax = plt.subplots(figsize=(7.4, 4.0), dpi=200)
names = ["上行（UE→server）", "下行（server→UE）"]
gnb1 = [20.29, 5.00]
gnb2 = [20.29, 5.00]
x = range(len(names))
w = 0.34
b1 = ax.bar([i - w / 2 for i in x], gnb1, w, label="基站1（NE5）", color="#2F5597")
b2 = ax.bar([i + w / 2 for i in x], gnb2, w, label="基站2（NE6）", color="#9DB4D6")
for bars in (b1, b2):
    for r in bars:
        ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 0.4,
                f"{r.get_height():.2f} ms", ha="center", fontsize=9)
ax.set_xticks(list(x))
ax.set_xticklabels(names)
ax.set_ylabel("端到端时延（ms）")
ax.set_ylim(0, 26)
ax.set_title("两台基站的上、下行端到端时延对比（各 400 样本）", fontsize=10)
ax.legend()
ax.grid(axis="y", ls=":", alpha=0.5)
fig.tight_layout()
fig.savefig("fig8_ladder.png", bbox_inches="tight", facecolor="white")
print("saved fig8_ladder.png")
