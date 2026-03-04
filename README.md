# Time-Tagger UI for Quantum CC
[中文说明](#中文说明) | [English](#english-description)

---

## 中文说明
本软件为量子通信实验与符合计数（Coincidence Counting）提供了一个基于 PyQt5 的功能完整、直观的可视化界面。该程序主要用于控制 Swabian Instruments TimeTagger 系列硬件外设，并进行高精度的时间标签采集与分析。

### 核心功能
- **实时符合直方图 (Real-time Coincidence Histogram)**: 允许用户自由设定 Start 通道与 Stop 通道，动态调节 Bin 精度与 Window 观测窗口宽窄，并实时显示两者之间差值的符合计数直方分布图。
- **动态延时配置 (Delay Calibration)**: 支持在 UI 上直接为特定 Stop 信号增加纳秒 (ns) 级别的延时补偿，用于校准光路、光纤或电缆导致的时间差。
- **自动寻峰 (Auto Search)**: 提供一键“自动寻峰”功能，在大范围的时间窗口中自动搜索真实的符合峰值，并根据高斯/阈值特征提取峰值位置，自动将计算出的延时偏差回填给当前通道。
- **灵活的设备扩展 (1TDC / 2TDC)**: 支持在同一个界面内操控单台 TDC，或联动两台独立的 TDC 设备，允许跨设备设定符合逻辑（比如使用 TDC-A 的 CH1 做 Start，TDC-B 的 CH3 做 Stop），支持物理 PPS 同步。
- **设备速率监控**: UI 主界面内置实时的单光子计数率监控表（kHz），方便随时调整实验光压与耦合效率。
- **自动化采集循环 (Automated Acquisition)**: 具备 `Free Run` (自由监视)、`Single Shot` (单次采集) 与 `Repeated` (自动化批量循坏采集) 几种工作模式。在批量模式下，用户可自定义每一轮的积分时长 (Duration) 以及循环计数。每次积分完成后，软件会在后台静默将直方数据写入存储目录的 `.txt` 文件内供后续数据拟合与处理。

### 安装指引
1. **环境准备**: 
   - 依赖 Python 3.8 或以上环境（推荐使用 [Miniconda](https://docs.conda.io/en/latest/miniconda.html)）。
2. **驱动安装**:
   - 必须在系统中提前安装 **Swabian Instruments TimeTagger** 官方驱动平台，并确保 Python API 环境配置关联正确。
3. **安装依赖**:
   ```bash
   pip install PyQt5 pyqtgraph numpy scipy
   ```
4. **运行程序**:
   - 针对单台设备控制：直接运行 `ui timestamp 1TDC folder.py`
   - 针对双设备同频控制：运行 `ui timetamp 2TDC folder.py`
   - 采集后期的批量拟合与分析：运行 `Data Processing.py`

### ⚠️ 注意事项
- **关于编译后的 EXE**: 如果您使用 Pyinstaller 对本项目进行 EXE 独立程序打包，请注意生成的执行程序通常在 700MB 左右（因为附带了科学计算包），此时本代码仓库的 `.gitignore` 已经默认屏蔽了相关打包目录。**请不要将生成的 executable 文件强制推送到远端仓库中**。
- **设备连接错误**: 若初次打开时提示 `TimeTagger Library Missing`，说明您的 Python 解释器尚未找到 Swabian 的底层驱动 API，请检查环境变量和安装路径是否正确。

---

## English Description
This software provides a fully-featured, intuitive visualization interface based on PyQt5 for controlling Swabian Instruments TimeTagger hardware devices and acquiring continuous time-tagging data specifically tailored for quantum communication and coincidence counting experiments.

### Core Features
- **Real-time Coincidence Histogram**: Enables users to assign Start and Stop channels flexibly. You can dynamically adjust the Histogram's "Bin" resolution and "Window" range to acquire real-time counts depicting timing correlation distribution structures.
- **Dynamic Delay Configuration**: Allows setting manual nanosecond-level delays (offsets) targeted at specific stop channels. Perfect for calibrating time differences caused by unmatching optical paths, fiber spools, or electronic cable lengths.
- **Auto Search Feature**: Pinpoints the actual true coincidence peak across a sweeping wide time window via a single click. It extracts the peak alignment mathematically and intelligently auto-fills the offset value to match.
- **1TDC / 2TDC Scalability**: Offers code configurations that work natively down to a single TDC setup, while accommodating an entangled dual-TDC interconnected architecture (Allowing a Start input from TDC-A's CH1 cross-correlated with TDC-B's CH3) relying on PPS synchronization logic.
- **Channel Rate Monitoring**: Embedded multi-channel frequency monitoring metric (kHz) natively in the UI to seamlessly inspect and regulate the underlying experimental optical coupling setup.
- **Automated Acquisition Cycles**: Harnesses multi-tiered operational regimes: `Free Run` (live observation), `Single Shot`, and `Repeated` batching. Batch mode allows customized repetitive integration spans (`Duration`) linked tightly with automated silent saving capabilities. Data is periodically output to `.txt` files containing histograms cleanly formatted for posterior data fitting tools.

### 📦 Installation Guide
1. **Environment Setup**: 
   - Python 3.8+ is strictly required. (Utilization of an isolated [Miniconda](https://docs.conda.io/en/latest/miniconda.html) environment is heavily advocated).
2. **Hardware Drivers**:
   - You MUST have the official **Swabian Instruments TimeTagger** driver suite correctly deployed, mapped, and accessible within your native system dependencies.
3. **Python Dependencies**:
   ```bash
   pip install PyQt5 pyqtgraph numpy scipy
   ```
4. **Execution**:
   - For single-TDC setups: Invoke `ui timestamp 1TDC folder.py`
   - For interdependent dual-TDC hardware flows: Initiate `ui timetamp 2TDC folder.py`
   - To undergo batch mathematical operations tracking acquired data: Deploy `Data Processing.py`

### ⚠️ Precautions
- **Compiled Executables (EXE)**: Should you endeavor to compile these modules into standalone executables relying on `Pyinstaller`, keep in mind the bundle will weigh near ~700MB. The incorporated `.gitignore` implicitly omits standard build directories (`dist/` and `build/`). **Do not force push EXE binaries back payload into this git repository.**
- **Connection Checks**: In cases where the UI raises a `TimeTagger Library Missing` message box, reconsider revising the Swabian TimeTagger core installations. Ensure its Python interconnects are placed into the active operating environment configuration.
