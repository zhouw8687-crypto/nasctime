# 控制消息上报基线

本目录在同一条分域轨迹上对比三种上报方式，并用同一候选策略分别读取当前状态与已到达消息。Python 3.10+ 标准库即可运行。

## 运行

从仓库根目录运行。

    exp=experiments/exp/control_reporting
    python3 -B -m unittest discover -s "$exp" -v
    python3 -B "$exp/replay.py" "$exp/example.domains.jsonl" --input-format domains --details /tmp/example.decisions.jsonl
    python3 -B "$exp/replay.py" /path/to/routes.jsonl --details /tmp/routes.decisions.jsonl

标准输出是每条轨迹的 JSON 汇总。逐次明细含发送原因、源时刻对应的实际帧十六进制、帧的到达时刻、接收端各域信息年龄、全信息候选、回放候选与分歧字段。示例记录见 example.decisions.jsonl。加上 --delay-ns 5000000 统一模拟 5 ms 单程延迟。每个观测时刻也是一次上报机会和决策机会，只有已到达的帧可供决策。首次信息未齐的决策单列为 unavailable。

## 输入输出约定

- 分域观测输入采用 example.domains.jsonl 的结构。每行为一次 version=1 的对齐观测，sim_time_ns 是严格递增的纳秒时间戳。ran 包含频带预算和最近调度块数，transport 包含当前路径和两个出口队列包数，core 包含视频监管速率 bit/s。现有 routes.jsonl 通过内置适配器读取 type=observation，跳过决策和回执。
- 覆盖区间为第一条观测至 end_ns_exclusive。均匀轨迹默认再向后延一个采样间隔，非均匀或只有一条观测的轨迹用 --end-ns 指定独占末端。上报计发送侧的字节，最后一条帧即使在窗尾尚未可用于决策也照常计费。
- 策略可用 --policy module:function 替换。将该模块加入 PYTHONPATH。函数读取与分域观测相同的 domains 对象并返回绝对候选动作字段，保持返回键集合固定且不依赖调用次序。内置策略复用 ladder_route_policy.py 的 choose_joint_policy，将空动作还原为保持当前的绝对候选。可用不同输入轨迹分别评价各场景。
- 汇总中的 wire_bps 是应用层帧位数之和除以区间秒数，含帧头。payload_bits 单独列出。每个域同时输出 Hz、报告次数、平均 bit/次、最大相邻发送间隔和决策时刻 Age of Information。年龄为决策时刻减最新到达帧的源观测时刻，未收到帧的年龄为 null，分位数取 nearest rank。候选分歧指任一目标字段不同，同时给出逐字段次数和可比较分母。

## 帧、触发器与插件

帧头按大端序写入 12 B，依次是四个单字节的协议版本、载荷编解码编号、载荷版本、域编号，以及 8 B 源观测时刻。协议版本为 1，域编号 1、2、3 依次对应 ran、transport、core。路径枚举 0、1 对应 direct、detour。帧通过保留消息边界的接口传递。实际接入字节流时应把分帧开销一并计入。

| 方法 | 编码 | 触发 |
| --- | --- | --- |
| periodic_full | 编号 1，状态字段无损，路径 1 B，其余每个字段 4 B | 每域每条观测 |
| periodic_fixed | 编号 2，频带和调度块各 1 B，路径及两条队列各 1 B，速率 2 B | 每域每条观测 |
| threshold_fixed | 同 periodic_fixed，每次发送该域的独立快照 | 首条观测、分类字段变化、任一数值增量达阈值，或距上次发送已达最长静默 |

定点队列单位为 8 包，核心速率单位为 100 kbit/s，RAN 单位为 1 块或 1 频带。半步向上取整，值超出格式范围报错。阈值与该域上次发送前的原始观测比较，默认队列 8 包、RAN 频带和调度块各 1、速率 100 kbit/s。默认最长静默 100 ms，在遇到第一条满足条件的观测时触发。采样缺口或非整倍数的配置可能推迟发送，可通过实际相邻间隔核验。--thresholds 接受部分数值阈值覆盖的 JSON 对象，--max-silence-ns 接受正整数。

reporting.py 定义独立的 Encoder.encode(domain, state) 和 Decoder.decode(domain, payload)，由 Codec(codec_id, version, encoder, decoder) 配对。后续双端 LoRA 可让域端输出离散索引的实际字节，GCC 端将字节还原为当前版本的结构化域状态，并通过不同 codec ID 和 version 管理码本。传给 replay.evaluate 的 Trigger.reason 可以独立替换。接入模型时应固定消息方向、域、字段和码本版本，使用真实码字字节跑同一核算；新增候选表或下行配额类型时需另定义载荷版本及接收端字段契约。当前帧、适配器和评估覆盖域到 GCC 的上报方向。

## 动作后果标签与训练样本

训练 JSONL 每行是同一决策点下的一组候选，见 example.training.jsonl。样例展示待标注的结构。version、scenario_id、decision_id、split_group 标识格式、工况、组内决策及数据划分单元。sim_time_ns 是输入截止时刻，intent 定义控制包期限和 99% 按期率约束，domains 只含该时刻及以前可用的状态。apply_at_ns 给出共同生效时刻，send_window_ns 是按发包归组的左闭右开评价窗，drain_until_ns 保留排空时间。candidates 中每个 action_id 对应一个绝对动作，由路径、RAN 预算和 UPF 速率组成。待标注行用 label_status=pending 和空 outcomes。

每个候选的 outcomes 保存逐重复结果。每条包含以下字段。

| 字段 | 含义 |
| --- | --- |
| replicate_id、seed、prefix_state_sha256、exogenous_trace_id | 重复编号、种子、分叉前状态摘要和外生业务及信道轨迹标识。各候选的同一 replicate_id 使用同一前缀和同一外生轨迹。 |
| applied_at_ns、applied_action、apply_status | 真实生效时刻、网元动作回读与 applied、rejected 或 error。回读与预定动作或生效时刻不符时单列执行失败。 |
| control_sent_packets、control_on_time_packets | 窗口发出的控制包、在业务期限内交付的控制包。丢包和迟到都留在分母中。 |
| video_delivered_payload_bits | 窗口发出且在观察截止前交付的视频应用净负载位数。 |
| ran_allocated_blocks、transport_branch_bit_hops | 评价窗内实际调度块累计值、分支链路统计的业务转发位跳数。 |
| resource_constraints_met | 按实验设定校验各域预算、路径和监管等约束后的布尔值。 |

每个有效重复按相同业务窗口计算后果向量。按期率由控制包计数相除，视频吞吐、无线块率和承载位跳率分别用计数除以窗口秒数。动作成功生效、控制发包量达到 intent.minimum_control_packets、按期率达到 intent.minimum_control_on_time_fraction 且资源约束全部满足时，得到该次重复的可行标签。发包不足的重复标记为缺测，执行失败和资源违约分别保留。跨重复汇总应同时保留样本数、逐重复方差和评估区间，再按预先固定的规则定义稳健可行性和候选偏好。完整配对并通过核验的组标记 label_status=complete。

分叉时优先从同一仿真前缀快照执行每个动作。若只能重放，应核验队列、调度和令牌桶等前缀状态及外生轨迹。域端编码器训练只读本域输入及公共意图，GCC 解码器用可行性与后果向量监督。下行可复用同一后果标签，将公共输入扩展为带动作有效期的域预算和当时域状态，目标是域执行器回读和业务后果。训练、验证、测试按 split_group 划分；同一拓扑、同一负载轨迹或同一场景种子的相关窗口需留在同组。旧 routes.jsonl 的回执属于原始在轨执行，不能为其余候选填充反事实 outcomes。

## 回放与闭环的测量边界

回放能直接核验应用层帧长、上报频率、假定延迟下的信息年龄及同一候选策略的分歧。两类视图都沿用原始行为生成的队列与当前配置。当候选改变时，后续队列、调度和监管状态仍来自记录，因此 SLA、视频有效吞吐、真实资源成本、可行性误判、决策遗憾、超期拒绝和控制收敛需要闭环或配对分叉。完整控制面的开销还需要预算下发、回执、码本同步和传输层开销；控制闭环时延还需要编码、传输、解码、求解和实际生效时间。
