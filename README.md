# Time-Tagger UI for Quantum CC
[中文说明](#中文说明) | [English](#english-description)

---

## 中文说明
本项目包含用于与 Swabian TimeTagger 设备进行交互、优化过度的高性能 Python 脚本，主要针对量子通信（Quantum CC）实验与符合计数（Coincidence Counting）应用场景开发。原始代码受限于单线程瓶颈与底层阵列重分配问题，现已完成深度的多线程与架构重构。

### ✨ 核心功能与提升
- **异步多线程存盘 (Async File I/O)**: 彻底消除了原始版本在周期结束、保存数据到硬盘时引发的 UI 界面死机与卡顿问题，所有文件读写均已转移至后台 `ThreadPoolExecutor` 线程池执行。
- **线程访问安全 (Thread Safety)**: 在 UI 参数配置和后台高频数据采集线程之间加入了原生的线程锁（`threading.Lock`）保护，彻底防止多线程资源抢占导致的数据读写错误。
- **完善的交互式 UI**: 
    - 引入直观的 **Save Directory**（保存目录）独立选择器（支持点击浏览目录）。
    - 开放了 **Auto Search** 自动寻峰的全局阈值调整参数，极大提升复杂底噪环境下的寻峰成功率。
    - **双通道设备联动**: 在 2TDC 版本中解锁了针对设备序列号（Serial Number）的直接文本编辑与重连功能。
- **内存防泄漏优化**: 消灭了高频（每 0.1 秒刷新）的坐标轴矩阵重建行为。不仅解决了旧有的内存泄漏（Memory Leak）隐患，连带根除了由于 Python 频繁执行垃圾回收（GC）而引发的规律性掉帧现象。

### 📦 安装指引
1. **环境准备**: 
   - 推荐安装 [Miniconda](https://docs.conda.io/en/latest/miniconda.html) 或 Anaconda 以隔离环境。
   - 核心依赖基于 Python 3.8+。
2. **驱动安装**:
   - 必须在系统中提前安装 **Swabian Instruments TimeTagger** 官方驱动平台，并确保 Python API 环境配置正确。
3. **安装依赖**:
   ```bash
   pip install PyQt5 pyqtgraph numpy scipy
   ```
4. **运行程序**:
   - 针对单台设备：直接运行 `ui timestamp 1TDC folder.py`
   - 针对双设备同频：运行 `ui timetamp 2TDC folder.py`
   - 后期数据拟合：运行 `Data Processing.py`

### ⚠️ 注意事项与必读
- **关于编译后的 EXE**: 如果您曾使用 Pyinstaller 对本项目进行了 EXE 独立程序打包，请注意生成的二进制执行程序通常在 700MB 上下，本代码仓库的 `.gitignore` 已经默认屏蔽了 `dist/` 和 `build/` 环境以防止云端 LFS 溢出。**请不要将生成的 executable 强制推送到仓库中**。
- **设备连接错误**: 若 UI 显示 `TimeTagger Library Missing`，请检查您的驱动层 API 是否已成功并入当前 Python 环境的环境变量中。

---

## English Description
This repository contains heavily optimized Python scripts for interacting with Swabian TimeTagger devices, developed primarily for quantum communication experiments and coincidence counting workflows. The code originally suffered from single-threading performance limits but has been significantly refactored.

### ✨ Features
- **Multithreading for File I/O**: Eliminates application stuttering during the end-of-cycle data saving by offloading disk operations to `ThreadPoolExecutor` workers.
- **Thread Safety Configuration**: Incorporates native thread lock protections bridging the gap between Data Acquisition threads and UI manipulation, preventing data scrambling.
- **Improved UI and Adjustments**: 
    - Flexible Directory Save Selection via UI browser.
    - Customizable **Auto Search** peak threshold configurations directly via UI.
    - In-place Serial Number updates for dynamic TDC switching routines.
- **Memory Enhancements**: Removes high-frequency Axis regeneration, resolving memory leaks and periodic GC UI stutters. Allows rapid data handling across heavy coincidence setups.

### 📦 Installation Guide
1. **Environment Setup**: 
   - Use of [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or Anaconda is highly recommended for creating an isolated Python environment.
   - Requires Python 3.8 or above.
2. **Hardware Drivers**:
   - You MUST have the official **Swabian Instruments TimeTagger** driver suite correctly installed, and the Python API must be accessible within your environment vars.
3. **Python Dependencies**:
   ```bash
   pip install PyQt5 pyqtgraph numpy scipy
   ```
4. **Execution**:
   - For single-TDC setups: run `ui timestamp 1TDC folder.py`
   - For dual-TDC setups: run `ui timetamp 2TDC folder.py`
   - For mathematical curve fitting: run `Data Processing.py`

### ⚠️ Important Notes
- **Compiled Executables (EXE)**: If you compile these modules into standalone executables using Pyinstaller, the resulting bundle often reaches ~700MB. The `.gitignore` by default blocks `dist/` and `build/` to prevent violating GitHub's standard LFS limits. **Do not force push EXE objects to this repository.**
- **Connection Diagnostics**: If the UI throws a `TimeTagger Library Missing` error upon connecting, please verify the Swabian TimeTagger installation path and Python hooking integrations.
