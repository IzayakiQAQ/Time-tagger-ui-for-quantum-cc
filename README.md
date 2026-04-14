# TimeTagger UI 项目说明

## 1. 项目简介

这个项目用于配合 Swabian Instruments 的 TimeTagger 系列设备完成以下工作：

- 实时采集时间戳数据
- 在线生成符合计数直方图
- 手动或自动搜索峰位并修正延时
- 在单台 TDC、双台 TDC、本地 USB、远程网络等多种模式下运行
- 将实验数据保存为文本、CSV 或 `ttbin`
- 支持 Franson 相关实验中的自动化采集与后处理

项目当前以 `PyQt5` 图形界面为主，另外包含一套用于 Franson 自动扫压的 `Tkinter` 自动化脚本，以及若干离线处理脚本。

## 2. 项目目录

仓库中的主要文件如下：

- `ui timestamp 1TDC folder.py`
  单台 TimeTagger 的本地采集界面。适合单设备、单机直连场景。

- `ui timetamp 2TDC folder.py`
  双 TimeTagger 采集界面。支持两台设备之间通过 PPS 做同步，也支持将数据保存为 `ttbin`。

- `Virtual Host/NodeA_Transmitter.py`
  分布式网络方案中的发送端脚本，运行在远端节点 A。

- `Virtual Host/WLAN_NodeB_Central_UI.py`
  分布式网络方案中的中心控制界面，运行在本地节点 B，用于连接远端 Node A 并进行集中采集。

- `AFI_for_TTU.py`
  Franson 自动化实验脚本。负责控制源表、等待稳定、向采集界面发起采集请求、汇总保存结果。

- `afi_tdc_sync.py`
  `AFI_for_TTU.py` 与 `ui timestamp 1TDC folder.py` 之间的文件式联动模块。通过 `requests/processing/done/failed` 目录交换状态。

- `process_franson_group1.py`
  根据 `manifest.csv`、Link1 直方图和 singles 参考计数，提取相位差曲线数据。

- `Data Processing.py`
  针对时钟差、峰位等数据做离线拟合处理的脚本。

- `data_merger.py`
  将多个周期生成的直方图按固定组数合并，便于做后续统计或降采样处理。

- `WORK_PLAN.md`
  当前一些开发和实验任务记录。

## 3. 适用场景

这个仓库主要覆盖三类实验场景：

### 3.1 单台 TDC 本地采集

适用于：

- 单台 TimeTagger
- 所有信号直接接入同一台设备
- 本地 USB 连接
- 需要快速查看两路符合峰、保存直方图或保存 `ttbin`

入口脚本：

- `ui timestamp 1TDC folder.py`

### 3.2 双台 TDC 本地采集

适用于：

- 两台 TimeTagger 分别接入不同信号
- 通过 PPS 做时间基准对齐
- 需要在同一界面中同时看两组 Link
- 需要将双机采集结果保存为文本或 `ttbin`

入口脚本：

- `ui timetamp 2TDC folder.py`

### 3.3 分布式网络采集

适用于：

- 一台 TDC 在远端节点 A
- 一台 TDC 在本地节点 B
- 两端通过局域网或可达网络通信
- 本地节点需要统一控制与显示

入口脚本：

- 远端：`Virtual Host/NodeA_Transmitter.py`
- 本地：`Virtual Host/WLAN_NodeB_Central_UI.py`

## 4. 环境依赖

### 4.1 Python 版本

建议：

- Python 3.10 到 3.13

理论上更早版本也可能可用，但当前代码是在较新的 Windows Python 环境下维护的。

### 4.2 必需依赖

至少需要安装以下 Python 包：

```bash
pip install PyQt5 pyqtgraph numpy scipy pandas tqdm pyvisa
```

如果需要运行 `AFI_for_TTU.py`，还需要：

```bash
pip install pyautogui pywin32 matplotlib elevate
```

说明：

- `PyQt5` / `pyqtgraph`：图形界面与实时绘图
- `numpy` / `scipy` / `pandas`：数值计算、拟合与数据处理
- `tqdm`：离线脚本进度条
- `pyvisa`：源表通信
- `pyautogui` / `pywin32`：Windows 自动点击与输入
- `elevate`：`AFI_for_TTU.py` 在 Windows 下请求管理员权限

### 4.3 硬件与系统依赖

还需要满足以下条件：

- 已安装 Swabian Instruments 官方 TimeTagger Python API
- Windows 环境下建议已安装 VISA 运行时
- 若使用双机同步或分布式方案，建议正确接好外部 `10 MHz` 参考和 `1 PPS`

## 5. 快速开始

### 5.1 单台 TDC 界面

运行：

```bash
python "ui timestamp 1TDC folder.py"
```

界面主要功能：

- 连接单台 TDC
- 配置两组 Link 的 Start/Stop 通道
- 设置 `Delay(ns)` 做延迟补偿
- 实时显示两个符合直方图
- 自动搜索峰位
- 以 `Free`、`Single`、`Repeat` 三种模式采集
- 可选保存 `ttbin`

### 5.2 双台 TDC 界面

运行：

```bash
python "ui timetamp 2TDC folder.py"
```

界面主要功能：

- 同时连接两台 TDC
- 支持每个 Link 的 Start/Stop 分别来自 TDC A 或 TDC B
- 使用 `CH 5` 作为 PPS 同步通道
- 若跨设备采集，程序会先尝试 PPS 对齐
- 若 10 秒内未等到 PPS，同步逻辑会超时并以 `offset=0` 继续，避免界面一直卡住
- 支持保存双设备 `ttbin`

### 5.3 分布式网络方案

#### Node A

在远端机器运行：

```bash
python "Virtual Host\NodeA_Transmitter.py"
```

它的职责通常是：

- 连接远端 TDC
- 将控制与数据接口暴露给网络

#### Node B

在本地控制机器运行：

```bash
python "Virtual Host\WLAN_NodeB_Central_UI.py"
```

它的职责通常是：

- 输入远端 `IP:Port`
- 建立网络连接
- 集中完成采集、同步、显示与保存

## 6. 界面参数说明

下面是 UI 中最常用的参数含义。

### 6.1 采集模式

- `Free Run`
  持续采集并实时刷新界面，一般不按周期落盘。

- `Single Shot`
  按设定时长采集一个周期，然后停止。

- `Repeated`
  按设定时长重复采集多个周期，并依次保存结果。

### 6.2 全局参数

- `Save Dir`
  数据保存目录。

- `Duration (s)`
  单个周期的采集时长。

- `Cycles`
  `Repeated` 模式下的最大周期数。

- `Bin (ps)`
  直方图每个 bin 的宽度，单位皮秒。

- `Window (ps)`
  直方图显示与统计的总窗口半宽，实际统计范围通常为 `[-Window, +Window]`。

- `Search Thresh`
  自动找峰时的阈值系数。

### 6.3 Link 参数

对于每个 Link，通常都需要设置：

- `Start Dev`
  起始事件来自哪台设备。

- `Start CH`
  起始通道号。

- `Stop Dev`
  停止事件来自哪台设备。

- `Stop CH`
  停止通道号。

- `Delay (ns)`
  对 Stop 通道施加的手动补偿延时，单位纳秒。

- `Auto Search`
  通过当前缓冲区数据自动搜索符合峰位置，并回填推荐延时。

### 6.4 TTBIN 保存

当前仓库中，单机版和双机版 UI 都支持 `ttbin` 保存。

行为大致如下：

- 打开 `TTBIN Save`
- 程序会按周期创建 `ttbin` 子目录
- 每个通道分别保存一个 `.ttbin`
- 文件名中带有周期号、通道号、时间戳

这类文件适合后续在官方工具或自定义脚本中做离线分析。

## 7. 输出文件说明

### 7.1 单/双机 UI 生成的直方图

常见文件名类似：

```text
Cycle_001_Link1_20260411_175904.txt
Cycle_001_Link2_20260411_175904.txt
```

内容一般为两列：

- 第 1 列：延时坐标
- 第 2 列：对应 bin 的计数

### 7.2 `ttbin` 文件

常见文件名类似：

```text
Cycle_001_CH1_20260411_175904.ttbin
Cycle_001_TDCA_CH1_20260411_175904.ttbin
Cycle_001_TDCB_CH3_20260411_175904.ttbin
```

用途：

- 保留原始时间标签流
- 用于更精细的离线分析

### 7.3 AFI 自动化实验输出

`AFI_for_TTU.py` 在每次实验运行时会创建：

- 一个 `run_YYYYMMDD_HHMMSS` 目录
- 其中包含 `group1`、`group2` 子目录
- 一个总表 `manifest.csv`

`manifest.csv` 会记录：

- 组名
- 步号
- 设定电压
- 实测电流
- 请求 ID
- Link1 / Link2 直方图路径
- singles CSV 路径
- 每个通道的平均 singles 速率
- 保存时间

### 7.4 Franson 曲线处理输出

`process_franson_group1.py` 运行后会输出：

- `group1_franson_curve.csv`
  或
- `group2_franson_curve.csv`

内容包括：

- 信号参考相位
- idler 参考相位
- 相位差
- Link1 中心峰位置
- 中心峰积分符合计数

## 8. Franson 自动化工作流

这一部分是当前仓库比较有特色的一条链路。

### 8.1 目标

`AFI_for_TTU.py` 负责：

- 控制源表扫压
- 在每个电压点稳定后发起一次 TDC 采集
- 收集每一步的直方图和 singles
- 生成 `manifest.csv`

### 8.2 联动方式

`AFI_for_TTU.py` 不直接调用 UI 内部对象，而是通过 `afi_tdc_sync.py` 提供的文件式队列联动。

工作目录为：

- `afi_tdc_sync/requests`
- `afi_tdc_sync/processing`
- `afi_tdc_sync/done`
- `afi_tdc_sync/failed`

流程大致如下：

1. `AFI_for_TTU.py` 创建采集请求 JSON
2. `ui timestamp 1TDC folder.py` 监听并接管请求
3. UI 完成单周期采集后保存文件
4. UI 将结果写入 `done`
5. `AFI_for_TTU.py` 读取结果并追加到 `manifest.csv`

### 8.3 使用前提

使用这条工作流前，请确保：

- `ui timestamp 1TDC folder.py` 已启动
- 监听心跳文件正常更新
- 采集设备已连接可用
- `AFI_for_TTU.py` 的保存路径、源表资源、鼠标坐标配置正确

### 8.4 运行

```bash
python AFI_for_TTU.py
```

注意：

- 该脚本会尝试请求管理员权限
- 依赖 Windows 自动化点击与键盘输入
- 对屏幕布局、按钮坐标、弹窗位置比较敏感

如果只是做数据采集而不需要源表自动控制，这个脚本不是必需的。

## 9. 离线处理脚本

### 9.1 `process_franson_group1.py`

用途：

- 从 `manifest.csv` 中提取某个 group 的记录
- 读取 Link1 直方图
- 识别中间峰并在指定窗口积分
- 基于 singles 参考计数恢复相位并计算相位差

示例：

```bash
python process_franson_group1.py "E:\your_run_dir" --group group1
```

可选参数：

- `--half-window-ps`
- `--idler-ref-min-khz`
- `--idler-ref-max-khz`

### 9.2 `Data Processing.py`

用途：

- 对已经采集好的直方图数据做峰位拟合
- 计算时钟修正量
- 生成离线处理结果表

说明：

- 这个脚本目前仍然是“改配置后直接运行”的风格
- 使用前需要先修改脚本中的输入目录等参数

### 9.3 `data_merger.py`

用途：

- 将多个周期的 Link1 / Link2 直方图按固定组大小合并
- 常用于把大量短时间采集结果压缩成较少的长时间结果

说明：

- 默认通过修改脚本顶部常量指定 `INPUT_DIR`、`OUTPUT_DIR` 和 `GROUP_SIZE`

## 10. 推荐使用流程

### 10.1 只看实时符合峰

推荐流程：

1. 运行 `ui timestamp 1TDC folder.py`
2. 连接设备
3. 配置两组 Link
4. 先用 `Free Run`
5. 用 `Auto Search` 粗找峰位
6. 微调 `Delay(ns)`

### 10.2 做周期采集并保存直方图

推荐流程：

1. 设置 `Save Dir`
2. 设置 `Duration` 与 `Cycles`
3. 切到 `Repeated`
4. 点击 `START`
5. 采集结束后检查输出目录

### 10.3 需要保存原始时间标签

推荐流程：

1. 勾选 `TTBIN Save`
2. 再开始采集
3. 采集结束后检查 `save_dir/ttbin`

### 10.4 Franson 自动化实验

推荐流程：

1. 先启动 `ui timestamp 1TDC folder.py`
2. 确认采集界面能正常接收数据
3. 再启动 `AFI_for_TTU.py`
4. 设置扫压范围、稳定时间、采集时间、保存路径
5. 开始自动实验
6. 完成后用 `process_franson_group1.py` 做曲线整理

## 11. 常见问题

### 11.1 `TimeTagger Library Missing`

说明：

- 没有正确安装 Swabian 官方 Python API

处理：

- 确认官方驱动和 Python 接口已安装
- 确认当前 Python 环境就是安装 API 的那个环境

### 11.2 双机模式一直停在同步阶段

可能原因：

- PPS 没接到 `CH 5`
- 两台设备没有共用参考
- 某一路根本没有收到 PPS

当前行为：

- 若超过约 10 秒仍未完成 PPS 对齐，程序会自动放弃严格同步并继续运行，避免界面长期卡死

### 11.3 网络模式能连接但没数据

优先排查：

- Node A 防火墙
- 数据端口是否被拦截
- 是否只有控制平面通、数据平面不通
- 远端设备是否真的有输入信号

### 11.4 `AFI_for_TTU.py` 提示缺少 `elevate`

处理：

```bash
pip install elevate
```

### 11.5 README 中文乱码

原因通常是：

- 文件编码被按 ANSI / GBK / 非 UTF-8 方式打开

建议：

- 统一使用 UTF-8 查看和编辑仓库文件

## 12. 开发建议

当前仓库历史较长，脚本风格不完全统一。继续维护时建议注意：

- 新脚本优先使用 UTF-8 编码
- 将“改顶部常量再运行”的脚本逐步改为命令行参数形式
- 将实验专用硬编码路径逐步抽离到配置文件
- 保持单机、双机、网络版三条链路的功能说明同步更新

## 13. 当前已知特点

当前版本有几个值得注意的点：

- `improved_v1` 是当前主要维护的仓库目录
- 单机版与双机版都已经加入 `ttbin` 保存能力
- `AFI_for_TTU.py` 已经改为优先在仓库内部寻找 `afi_tdc_sync.py`
- `.gitignore` 已忽略运行时生成的 `afi_tdc_sync/` 状态目录，避免把实验过程文件提交进仓库

## 14. 许可与说明

这个仓库更偏实验室内部工具集合，而不是一个已经完全产品化的通用软件包。

如果你准备把它交给新同学或合作方使用，建议至少一起提供：

- 一份硬件接线说明
- 当前实验使用的通道定义
- 一份实际可用的参数模板
- 一个示例输出目录

这样上手会比只给代码快很多。
