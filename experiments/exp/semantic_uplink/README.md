# 同码率上行语义压缩首轮

本目录比较周期定点、周期边界、小 MLP 和双端 LoRA。每个域、每 20 ms 发送 4 B 载荷，加既有 12 B 帧头，三域合计 19,200 bit/s。全量参考独立计费。载荷和帧均实际序列化。短消息仅使用方向预配置的目标 UE 与业务契约，模型输入为本域当前数值和域类型。码字是四个独立可寻址的 8 bit 索引，接收端只读取它们和域编号，恢复固定单位的求解器字段。

LoRA 两端使用同一来源的预训练 CLIP 文本模型，各自保存对应 q/v LoRA 适配器、数值嵌入和输出头。训练采用硬二值码字与直通梯度，重建目标对承载的队列门槛和控制队列权重更高。MLP 使用相同硬码字与重建监督。所有模型使用训练划分拟合，通过验证集重建误差选检查点。实测候选分叉结果只用于最终计分。

## A100 入口

从此前的独立闭环工作树出发。dataset 指向教师组已发布目录。args.output 均使用新路径。

~~~bash
cd /media/a100/data/zbw/nasctime-reporting-loop-20261127/experiments/exp
py=/home/a100/anaconda3/envs/minimind/bin/python
base=/home/a100/lrs/TURBO-DDCM/models/FLUX.1-dev/text_encoder
dataset=/media/a100/data/zbw/semantic-teacher-results-20261128/v0.2.0
artifacts=$(mktemp -d /media/a100/data/zbw/semantic-uplink-repeat.XXXXXXXX)
export CUDA_VISIBLE_DEVICES=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
"$py" -B -m semantic_uplink.fit mlp "$dataset" "$artifacts/mlp" --device cpu --epochs 220 --lr 0.003
"$py" -B -m semantic_uplink.fit lora "$dataset" "$artifacts/lora" --base "$base" --epochs 80
"$py" -B -m semantic_uplink.evaluate "$dataset" "$artifacts/eval" \
    --mlp "$artifacts/mlp" --lora "$artifacts/lora" --latency-frames 128
python3 -B -m unittest semantic_uplink.test_semantic integrated_review.test_uplink
~~~

运行器接受教师发布 v0.1.0 的 seed 组清单和 v0.2.0 的逐轨迹冻结清单，读取前核对所有文件 SHA-256。每次评价固定使用老师分叉时刻可用的三域报告、20 ms 周期、0 ms 传播时延、原 GCC 枚举规则和 balanced 权重。三域无法在一轮内到达或领到过期状态的较长延迟需要连续源轨迹和对应分叉标签。由于教师标签已在源时刻分叉，这轮使用与标签对齐的零延迟。对新的位宽、训练目标或求解器改动，应另行冻结后再做留出评价。

comparison.json 含按实际帧长核算的 bit/s、预测可行但实测违约的次数及分母、最终执行动作的实测可行性、同前缀全信息选择与压缩选择的有符号实测效用差。正差表示相对全信息损失，SLA 违约单列。效用按发布合同折算为 100 ms，使用标签中实际视频与竞争流交付、视频按期包、调度块和 N3 位跳。decisions.jsonl 保留测试分组、UE / 流、纳秒时刻、有效期、评价窗、偏好及逐域码字。P99 在验证输入上去掉模型加载与预热，每域重复实测 128 次，含设备数据往返。真实 Simu5G 的单轨迹周期由网络仿真决定，测得的壁钟推理时延未加入传播队列。

## 闭环冒烟与装配

跑旧版教师数据时，在 artifacts 目录将输出分别命名为 mlp-smoke、lora-smoke。运行旧版单种子 PF 闭环。

~~~bash
cd /media/a100/data/zbw/nasctime-reporting-loop-20261127
d=/media/a100/data/zbw
bash experiments/exp/semantic_uplink/run_smoke.sh "$d/simu5g17-qfi.nJ2rCJ/Simu5G-qos" \
    "$d/nasctime" "$d/semantic-uplink-results-20261128" "$d/semantic-smoke-repeat" \
    /home/a100/anaconda3/envs/minimind/bin/python
~~~

主闭环保持集成分支定义的 Codec 接口。指定 REPORT_CODEC_FACTORY=semantic_uplink.learned:make_learned、SEMANTIC_CODEC_DIR、REPORT_PYTHON 和启动等待 REPORT_STARTUP_ATTEMPTS 即可加载已训练端点，或替换工厂为 formats:make_fixed / make_boundary。可通过 SEMANTIC_BASE_MODEL 指定等内容的本地 CLIP 目录，加载时校验文件指纹。LoRA 从已激活的两端推理部件分别产生或识别报文字节。GCC 仍执行同一个结构化候选求解器。

教师扩充版各动作的结果来自共享前缀后单独实跑。本模块对这些测量做动作选择和效用核对，正式留出的结果描述受控分叉的选择表现。单种子在线冒烟连接了实时轨迹、编码、解码、求解和下发，连续多轮的留出部署表现尚未测量。
