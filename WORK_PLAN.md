# WORK_PLAN.md

## Current Objective
检查并修复 `WLAN_NodeB_Central_UI.py` 中的连接逻辑。目前代码使用的是 `createTimeTagger(serial)`，这通常用于本地 USB 连接，需要修改以支持通过 IP:Port 连接到远程 Transmitter。

---

## Diagnosis / Analysis
1. **现状**：`HardwareInterface.initialize` 中直接调用 `Swabian.TimeTagger.createTimeTagger(serial_a)`。
2. **问题**：如果 `serial_a` 是一个 IP 地址（例如 `192.168.1.100:4444`），普通的 `createTimeTagger` 可能无法正确识别为网络连接，或者在某些版本中需要显式调用 `createTimeTaggerNetwork`。
3. **需求**：发射端 `NodeA_Transmitter.py` 使用了 `tagger.startServer(4444)`，接收端（UI端）必须能够连接到这个地址。

---

## Proposed Code Changes

### 文件：`WLAN_NodeB_Central_UI.py`

#### 1. 修改 `HardwareInterface.initialize()`
- 增加逻辑：判断输入的字符串是否包含 `:`（IP:Port 格式）。
- 如果包含 `:`，调用 `Swabian.TimeTagger.createTimeTaggerNetwork(address)`。
- 如果不包含，保持 `Swabian.TimeTagger.createTimeTagger(serial)`。

#### 2. 更新 UI 默认值和标签
- 将 UI 上的 "Serial" 标签改为 "Serial / IP:Port"。
- 默认值可以设为一个示例 IP，方便用户测试。

---

## Results
- [x] 分析完成：确认当前代码确实缺乏显式的网络连接逻辑。
- [ ] 代码修改完成。
