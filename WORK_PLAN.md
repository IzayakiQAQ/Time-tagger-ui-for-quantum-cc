# WORK_PLAN.md

## Current Objective
1. 诊断并解决 WLAN 分布式系统中“能连接、能操作，但收不到时间戳数据”的问题。
2. 确认是网络数据平面（Firewall/Port）阻塞还是软件同步逻辑（Synchronizer/Manual Merge）问题。

---

## Diagnosis / Analysis
- **现象描述**：能够通过 IP:Port 连接，能够执行 `setClockSource` 等控制指令（代表 RPC 控制平面正常），但计数器（Counter）和时间戳流（Stream）返回空数据（代表数据平面异常）。
- **可能原因 1：防火墙拦截数据端口**。Swabian Server 除了 4444 控制端口，数据传输会使用动态端口。若防火墙仅开启 4444，会导致“看得见连不上数据”。
- **可能原因 2：流订阅未生效**。在网络模式下，`TimeTagStream` 有时需要显式的 `start()` 以及确保服务端有物理信号触发。
- **可能原因 3：同步逻辑阻塞**。`WLAN_NodeB_Central_UI.py` 目前采用 Python 手动对齐 PPS。如果 Node A 没数据，循环会一直卡在 `Syncing PPS...`。
- **可能原因 4：用户误解了 ttbin**。UI 目前仅保存 `.txt` 格式的直方图。如果是指官方 GUI 连接服务器看不到数据，则基本确定是防火墙或硬件问题。

---

## Proposed Changes
1. **测试脚本**：编写一个简单的 `debug_network_data.py` 让用户在 Node B 上运行，跳过 UI 逻辑，直接测试 `Counter` 是否有数。
2. **防火墙配置指导**：要求用户暂时关闭 Node A 的防火墙进行测试，或将 `TimeTagger.exe` / `Python.exe` 加入白名单。
3. **优化 UI 连接逻辑**：在 UI 打印中增加“正在检测数据流...”的探测环节。

---

## Results
- [x] 诊断脚本已生成。
- [ ] 修复建议已发送。
