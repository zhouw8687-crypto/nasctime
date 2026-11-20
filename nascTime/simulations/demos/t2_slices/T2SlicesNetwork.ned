//
// T2SlicesNetwork —— 三流三切片的承载网场景（测试方案用例 T2）
//
// 拓扑（承载网单域，不含空口；与方案 2.1 节“两节点直线”等价）：
//
//   client1（切片1 / 高优先控制流） ─┐
//   client2（切片2 / 中优先大带宽流）─┼─ pe1 ── pe2 ── server
//   client3（切片3 / 低优先背景流） ─┘
//
// 切片与优先级的映射（仿真中用一个 PCP 值代表一个切片）：
//   切片1 → PCP 5 → 流量等级 2（最高）
//   切片2 → PCP 4 → 流量等级 1
//   切片3 → PCP 0 → 流量等级 0（最低）
//
// TAS 门控周期 1 ms，三相窗口：
//   0–200 µs   等级2 独占
//   200–800 µs 等级1 独占
//   800–1000 µs 等级0 独占
//
package nasctime.simulations.demos.t2_slices;

import inet.networks.base.TsnNetworkBase;
import inet.node.ethernet.EthernetLink;
import inet.node.tsn.TsnDevice;
import inet.node.tsn.TsnSwitch;

network T2SlicesNetwork extends TsnNetworkBase
{
    submodules:
        client1: TsnDevice {
            @display("p=120,160");
        }
        client2: TsnDevice {
            @display("p=120,320");
        }
        client3: TsnDevice {
            @display("p=120,480");
        }
        pe1: TsnSwitch {
            @display("p=420,320");
        }
        pe2: TsnSwitch {
            @display("p=680,320");
        }
        server: TsnDevice {
            @display("p=920,320");
        }
    connections:
        client1.ethg++ <--> EthernetLink <--> pe1.ethg++;
        client2.ethg++ <--> EthernetLink <--> pe1.ethg++;
        client3.ethg++ <--> EthernetLink <--> pe1.ethg++;
        pe1.ethg++ <--> EthernetLink <--> pe2.ethg++;
        pe2.ethg++ <--> EthernetLink <--> server.ethg++;
}
