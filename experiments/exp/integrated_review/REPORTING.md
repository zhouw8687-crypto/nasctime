# 分域上报闭环

本实验沿用双 UE 集成场景、20 ms 决策周期和全信息 GCC 的候选求解器。域上报的编解码和传输时间在 Python 适配器内模拟，选出的动作经原 TCP 桥进入 Simu5G 执行。

## 复现

在 A100 的实验工作树运行。run.sh 末参数 ue0 选择目标 UE 的无线积压。结果目录须为新路径。

~~~bash
root=/media/a100/data/zbw
batch=$(mktemp -d "$root/reporting-loop-repeat.XXXXXXXX")
export DL_DISCIPLINES=PF SEED_COUNT=5 REPORT_MODES="exact boundary_periodic boundary"
export REPORT_REFRESH_MS=40
for profile in 0-40 5-40 5-60 25-40 25-80; do
    REPORT_DELAY_MS="${profile%-*}" REPORT_TTL_MS="${profile#*-}" \
        bash experiments/exp/integrated_review/run.sh \
        "$root/simu5g17-qfi.nJ2rCJ/Simu5G-qos" "$root/nasctime" "$batch/$profile" ue0
    (cd experiments/exp && python3 -B -m integrated_review.summarize "$batch/$profile") \
        > "$batch/$profile.csv"
done
(cd experiments/exp && python3 -B -m unittest integrated_review.test_uplink domain_coordination.test_baseline)
~~~

exact 为周期全量，boundary_periodic 为周期边界编码，boundary 为相同边界编码加变化触发及最长静默刷新。round8 保留原定点对照。未设置环境变量时，运行器仍运行原四种方法、MAXCI/PF 两种调度、种子 0–4，报告延迟为 0 ms，TTL 和最长静默各为 40 ms。

## 时间语义和评价

每条报告独立序列化，发送时写入源观测时间，固定单程延迟后可见。决策在每个 20 ms 观测时刻运行，使用最新的已到达报告。年龄等于决策时刻减源观测时刻，达到 TTL 即过期。任一域缺报或过期时保持当前执行配置，这一轮不会运行接收视图求解。刷新时间独立于 TTL，以最近一次发送为起点。这里模拟的是可靠的单程报告通道，命令和回执使用既有桥。

policy.jsonl 记录帧字节、源时刻、计划到达时刻、域状态年龄和策略动作。routes.jsonl 记录模拟器命令及回读。summarize.py 从帧日志重新推导每次决策可读取的域状态并核验保持行为、真实配置和 20 ms 业务按期交付。分域年龄统计只包含已到达的报告，含过期样本。缺报和过期次数单列。target_diff_ticks 比较执行目标与本轮同一条真实运行轨迹上用当前完整观测求出的参考动作。参考动作只供诊断，两条方法运行之间的收益差由实际端侧计数比较。应用层上报码率按实际帧长（含 12 B 头）核算，设置的传播延迟与操作系统耗时无关。

## 替换双端编解码器

uplink.py 暴露 Encoder.encode(domain, report) -> bytes 和 Decoder.decode(domain, payload) -> Report。分域输入输出为 RanReport（频带上限、UE MAC 积压字节）、TransportReport（当前路径和按直达、绕行排列的 LinkReport）及 CoreReport（估算视频 bit/s、突发桶字节）。两端共用字段、单位和稳定码本。报告需能独立解码。boundary 触发模式比较已编码载荷是否逐字节变化，所以编码应具有确定性。线上元数据由通道添加。

将自定义模块放入 PYTHONPATH，提供无参数工厂返回 `Codec(codec_id, version, sender, receiver)`，填入约定的非零单字节 ID 与版本。运行器通过 REPORT_CODEC_FACTORY=module:function 装配；也可给 integrated_review.policy 传 --codec-factory module:function。自定义载荷时，运行器的 mode 仍选择发送规则。后续双端 LoRA 可将域报告编码为离散索引的字节，并在 GCC 还原同样的类型。实验未注入编解码实测推理时延、链路丢包、带宽排队或码本同步开销。
