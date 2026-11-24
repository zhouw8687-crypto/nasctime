# EXP-10 外部控制器闭环验证

## 任务书对应关系

本实验在任务书的日字形拓扑中运行，沿用两台 gNB、六台 NE 和双上联 UPF。两条下行业务同时经过 server → UPF → NE1 → NE3 → NE5 → gNB1 → UE0，用同一条数据路径验证控制器从状态上报到策略生效后的业务反馈。

| 任务书模块 | 本实验接通的功能 | 后续联调接口 |
| --- | --- | --- |
| 跨域控制与资源协同 | 独立进程读取三域状态，运行中修改 UPF 的背景流准入速率，由仿真返回实际值 | 有线控制器的队列与门控执行、无线控制器的调度资源执行、策略协作与冲突处理 |
| 接口协议与时间同步 | 仿真按固定仿真时钟采样，使用同一仿真时刻关联状态与执行结果，保留接口往返墙钟时间 | 分域时钟同步误差、统一生效时刻及迟到策略、设备接口适配 |
| 性能检测与状态反馈 | 在线队列占用、UPF 通行与丢弃、UE 收包计数，离线应用序号与五处 PCAP 对齐 | 按切片实时延迟和期限违约、带宽与资源预算、故障下的可靠性 |

UPF 在 N6 解出 IPv4/UDP 后、进入流分类和 N3 封装前，对 UDP 目的端口 6202 使用 INET 令牌桶。限速扣减包含 IPv4 与 UDP 首部的 IP 包长度，突发容量 4120 B，余额不足丢弃。控制流 UDP 6200 直接通过。执行动作保留令牌桶余额并按原速率结清已过去的时间，随后切换补充速率。原理参考 [INET 令牌桶示例](https://inet.omnetpp.org/docs/showcases/tsn/streamfiltering/tokenbucket/doc/index.html)。

## 原理与参数

OMNeT++ 6.4.0、项目既有的 INET 和 Simu5G，所有组使用 seed 0，模拟 3 s。每段承载链路 30 km，NE1–NE3 配置 10 Mbit/s，两流使用同一路径和同一小区。控制流 200 B、5 ms 间隔、DSCP 46。背景流 1000 B、平时 8 ms 间隔、突发期 700 µs、DSCP 0。应用在 1.6 s 停发，按 0.2–1.6 s 的发送队列统计，仿真继续以收集晚到包。

每 20 ms 仿真时间采样一次，起止点为 200、1600 ms，共 71 次。示例策略以无线或有线任一队列过载为触发条件。若 gNB1 下行 MAC 虚拟缓冲达到 8000 B，或 NE1 背景队列达到 8 包，则请求将 UPF 背景流从 20 降到 2 Mbit/s。无线缓冲和有线队列分别连续 5 次采样同时不超过 2000 B、1 包后，解除限制。阈值取自当前场景队列量级，用于验证接口和控制链路。

| 组别 | 原理及运行参数 | 验证目的 |
| --- | --- | --- |
| ControllerBaseline | UPF 20 Mbit/s，突发 0.60–1.00 s，只采样 | 测得现有数据面自然积压和收包情况 |
| ControllerStaticCap | UPF 全程 2 Mbit/s，突发 0.60–1.00 s，只采样 | 使用同样的低限速值，衡量持续限速的取舍 |
| ControllerExternal | 初始 20 Mbit/s，突发 0.60–1.00 s，外部算法实时决策 | 核对状态、指令、执行回执与随后数据面的关联 |
| ControllerExternalShifted | 同一外部算法与初始速率，突发 0.80–1.20 s | 看首次决策是否随拥塞时间变化 |

## 可复现结果

| 组别 | 突发窗口控制流送达 | 控制流送达包 P99 | 突发窗口背景流送达 | UPF 全程丢背景包 | 无线虚拟缓冲采样峰值 | NE1 背景队列采样峰值 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 无外部控制 | 69/80 | 87.60 ms | 342/563 | 0 | 212810 B | 128 包 |
| 固定 2 Mbit/s | 78/80 | 80.00 ms | 97/563 | 465 | 163 B | 0 包 |
| 外部动态策略 | 71/80 | 80.00 ms | 137/563 | 374 | 23259 B | 14 包 |
| 外部策略，突发后移 | 71/80 | 89.50 ms | 138/563 | 374 | 23259 B | 14 包 |

原突发的四次执行是 640、800、840、1000 ms，后移组为 840、1000、1040、1200 ms。每组由限速、恢复、再次限速、再次恢复构成，执行回执与下一次采样读回值一致。原突发内，动态组比固定限速多交付 40 个背景包，少交付 7 个控制包。这组结果给出了初始策略的取舍和一次突发内的重新限速现象，策略目标与阈值仍需按期限、带宽预算和多种负载验证。

每个组按应用序号核对 UPF N6 和 N3。运行程序检验两处之间首个缺失的背景包数与限速器丢弃计数完全一致，两个外部组分别验证 71 次观察—决策—回执和下一采样点的状态。重复运行得到相同的 KPI、流统计和逐包轨迹，控制事件中仅墙钟等待字段随运行变化。另用独立客户端测试过期版本、错误流 ID 和重复配置，仿真分别返回版本不匹配、动作无效和无需变更。用可导入的自定义空策略得到与无外部控制组字节一致的流统计和逐包轨迹。用 50 ms 墙钟超时阈值、对端不应答的条件，仿真在首个采样点终止，保留了该观测记录。

## A100 复跑与证据

按交接文档配置并编译。A100 已有 Simu5G 使用的 nlohmann/json 头文件，控制桥使用同一个依赖。

```bash
cd /media/a100/data/zbw/nasctime
source omnetpp-6.4.0/setenv
export LD_LIBRARY_PATH="$PWD/../conda-envs/nasctime/lib:$PWD/omnetpp-6.4.0/lib"
export INET_ROOT="$PWD/inet" SIMU5G_ROOT="$PWD/Simu5G"
make -C nascTime -j4
bash experiments/exp/run_ladder_controller.sh
```

启动器打印独立的结果目录，写入 Git 版本、汇总 control-kpis.csv，并为每组保存 control.jsonl、flows.csv、packet-trace.csv、仿真日志、原始向量和 PCAP。packet-trace.csv 保留应用 TX、UPF N6/N3、NE1 egress、NE5 ingress、NE5→gNB 和 UE RX。P99 以成功交付的包为样本，送达数同时报告。无线峰值为 gNB1 全部下行连接的 MAC 虚拟缓冲采样值。该指标用于状态反馈，RLC/HARQ 细分需要相应独立计数。

## 接入自定义算法

用 Python 接入时，编写一个 decide(observation) 函数。返回 None 或 {"type":"set_upf_rate","flow_id":"background","rate_bps":2000000}，可以通过进程内持久化状态实现跨采样控制。端口设为 8765 时，在 A100 的第一个终端启动算法进程。

```bash
cd /media/a100/data/zbw/nasctime
PYTHONPATH=/path/to/algorithm python3 -B experiments/exp/ladder_controller.py \
    --port 8765 --policy my_algorithm:decide
```

在已加载上文环境的第二个终端启动仿真。

```bash
cd /media/a100/data/zbw/nasctime/nascTime/simulations/demos/e2e_ladder
out=$(mktemp -d /tmp/ladder-custom.XXXXXX)
../../../bin/nasctime-run.sh -f omnetpp_controller.ini -u Cmdenv -c ControllerExternal -r 0 \
    --result-dir="$out" '--*.controller.port=8765'
```

其他语言也可直接监听 127.0.0.1 上的 TCP 端口。每条消息是一行 UTF-8 JSON，单行不超过 16384 字节。仿真作为客户端连入后发送 observation，字段包括 version=1、request_id、sim_time_ns、generation、ran、transport、core、delivery。下面是同一次采样的策略请求和正常执行回执。

```json
{"version":1,"type":"decision","request_id":23,"base_generation":0,"action":{"type":"set_upf_rate","flow_id":"background","rate_bps":2000000}}
{"version":1,"type":"ack","request_id":23,"sim_time_ns":640000000,"generation":1,"status":"applied","reason":"rate_changed","flow_id":"background","rate_bps":2000000}
```

请求要回填本次 request_id 和 generation，rate_bps 为 1 到 1000000000 的整数。无动作时 action 取 null。回执包含已生效的实际速率和当前版本，状态有 applied、noop、unchanged、rejected。每步等待一次决策，默认限时 3000 ms 墙钟；超时或连接断开时实验失败。仿真时钟在等待期间暂停，因此当前统计可用于接口和算法联调，实设备下发时延、分域同步和定时生效需要在异步控制路径中验证。

下一项可在同一拓扑中加入可回读的有线动作，并让外部控制器联合下发 UPF 配额与 NE 端口的门控策略。之后将无线调度动作接入，按任务书区分无线短周期决策和有线较长周期编排。
