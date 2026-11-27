# PF 双 UE 全信息教师

从集成场景重放相同的在线 GCC 前缀，在指定采样点分叉。每个分叉显式执行一个绝对联合动作，保持 100 ms，再恢复原 GCC 并用该分支自己的实时状态继续控制。控制器仍每 20 ms 读取域状态。默认用 5 个种子、6 个采样点与 8 个动作，另有每个种子的滚动 GCC 参考。实验不重设分叉时的队列、调度或令牌桶。

## 复现

从仓库根目录运行。前三个参数是现有 Simu5G 1.7 隔离树、含 OMNeT++/INET 的运行库仓库以及尚不存在的结果目录。

    bash experiments/exp/counterfactual_teacher/run.sh "$simu5g" "$runtime" "$new_output"
    (cd experiments/exp && python3 -B -m unittest counterfactual_teacher.test_teacher)
    (cd experiments/exp && python3 -B -m counterfactual_teacher.dataset "$new_output")

小规模复核可加 `--seeds 0 --forks 420 --jobs 2`。正式分叉时刻为 280、420、440、640、1020、1140 ms，覆盖稳定段、换路前、换路点和回切点。动作按 direct/detour、4/10 频带、1/3 Mbit/s UPF 限速做笛卡尔积。候选是否被模型过滤不会阻止合法动作进入仿真。

## 使用标签

- `counterfactuals.jsonl` 每行是一个种子和决策点，含 8 个候选。训练因果输入为 `sim_time_ns`、`intent`、`domains`、`domain_budgets` 和可选的 `active_action`。域编码器只读本域栏与公共意图。域候选接口复用 `domain_coordination.baseline` 的三个生成器，未把终端结果反馈到输入。模型估计在 `domain_candidates` 和 `gcc_prediction`，实测监督在 `candidates[].outcomes[]`。
- 每个有效分支保留发送窗口内的控制按期、视频最终交付和 20 ms 诊断、竞争 UE 的收包及 20 ms 诊断、两 UE 和小区调度块、六条支路端口的 N3 外层 IP 位跳。包按发送时刻归组，允许在 4 s 仿真截止前交付。维持原突发窗 20 ms、99/100 的控制判定，同时把局部 100 ms 窗的 20 个控制包用于分支可行性判断。边界时间戳按左闭右开，包含发送时刻恰等于分叉时间的包。位跳和授权块按发生时刻计量，可能含跨窗的在途业务。
- `pareto_action_ids` 联合考虑控制、视频及竞争 UE 的离散结果和实测资源用量，`service_pareto_action_ids` 忽略资源成本。相同目标值的可行动作都保留。比较以 GCC 本轮选出的动作在相同 100 ms 持续期内的反事实为基准。某个候选的资源收益和业务损失可以同时存在，此时标为 `tradeoff`。等价只针对已列出的离散目标，P99 等原始值仍保留。需要固定偏好时，`dataset.weighted_regret` 接受所选行动、各目标偏好权重和单位尺度。
- `rolling_gcc_reference` 是未强制持有动作、持续每 20 ms 决策的单独运行。其未来状态和结果只是标签侧参考。默认按整条种子轨迹划分，种子 0–2 训练、3 验证、4 测试，同一 `split_group` 不可跨集合使用。所有组共享拓扑和业务设定，适合验证管道和构造配对样本。
- `prefix_state_sha256` 要求相同的控制事务、分叉前可观测向量和分叉观测全部一致。分叉观测包含各 NE1 业务类队列、各 CID 虚拟 MAC 积压、UPF 令牌、控制版本和 RNG draw 计数。 `exogenous_trace_id` 标识共用初始种子和完整应用发送记录。原生信道计算仍使用仿真内随机流，动作会改变调度和后续随机数消费，未把分叉后的信道实现冻结为同一相同轨迹。结果描述共享前缀和应用负载条件下的配对效应。
- `summary.json` 汇总配对关系、分段与目标。原始命令、回读、队列和应用向量、抓包在各运行目录。任何前缀、业务输入、命令或回读核验失败会终止标签构造。
