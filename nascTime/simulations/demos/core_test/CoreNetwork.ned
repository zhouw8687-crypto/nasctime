//
// CoreNetwork —— 核心网域最小单元
//
// 结构：
//   hostA ── Eth10G ── iUpf ── Eth10G ── upf ── Eth10G ── server
//   (接入侧代理)      (N3 汇聚)        (用户面锚点)      (外部数据网)
//
// 为什么用 Router 而不是 Simu5G 的 Upf：
//   Simu5G 的 Upf 内部 dnPpp 接口只与 gtp_user 相连（见 Upf.ned 的 connections），
//   它需要一个 GTP 对端（gNB 的 GtpUser）才能完成封装/解封装并注册接口。
//   在没有 gNB 的独立核心域里，Upf 会在 `upf.ipv4.lp` 处分发失败
//   （"Connected network interfaces can register using registerInterface()"）。
//   官方 Upf 只出现在带 gNB 的网络里（SingleCell/MultiCell_Standalone）。
//
//   Simu5G 文档明确写 "act like IP routers in the current version"，
//   因此在"只验证转发/时延/切片"的最小核心域里，用 Router 代理 UPF 是等价的。
//   接真 gNB 之后（GTP 存在），把这两个 Router 换回 Upf 即可，
//   接法照抄 MultiCell_Standalone：iUpf.pppg++ <--> Eth10G <--> gnb.ppp。
//
package nasctime.simulations.demos.core_test;

import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.node.ethernet.Eth10G;
import inet.node.inet.Router;
import inet.node.inet.StandardHost;

network CoreNetwork
{
    submodules:
        configurator: Ipv4NetworkConfigurator {
            @display("p=60,60");
        }
        hostA: StandardHost {
            @display("p=200,200");
        }
        iUpf: Router {
            @display("p=420,200");
        }
        upf: Router {
            @display("p=640,200");
        }
        server: StandardHost {
            @display("p=860,200");
        }
    connections:
        hostA.pppg++ <--> Eth10G <--> iUpf.pppg++;
        iUpf.pppg++ <--> Eth10G <--> upf.pppg++;
        upf.pppg++ <--> Eth10G <--> server.pppg++;
}
