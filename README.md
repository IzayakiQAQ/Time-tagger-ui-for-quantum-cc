# Time-Tagger UI for Quantum CC

This repository contains heavily optimized Python scripts for interacting with Swabian TimeTagger devices, developed primarily for quantum communication experiments. The code originally suffered from single-threading performance limits but has been significantly refactored.

## Features ✨
- **Multithreading for File I/O**: Eliminates application stuttering during the end-of-cycle data saving by offloading disk operations to `ThreadPoolExecutor` workers.
- **Thread Safety Configuration**: Incorporates native thread lock protections bridging the gap between Data Acquisition threads and UI manipulation, preventing data scrambling.
- **Improved UI and Adjustments**: 
    - Flexible Directory Save Selection.
    - Customizable **Auto Search** peak threshold configurations directly via UI.
    - In-place Serial Number updates for dynamic TDC switching routines.
- **Memory Enhancements**: Removes high-frequency Axis regeneration, resolving memory leaks and periodic GC UI stutters. Allows rapid data handling across heavy coincidence setups.

## Included Modules
1. `ui timestamp 1TDC folder.py`: Re-architectured 1TDC module.
2. `ui timetamp 2TDC folder.py`: 2TDC synchronization operations with fully implemented multi-threading architecture.
3. `Data Processing.py`: Robust analytical fitting curve scripts with updated tolerance logic utilizing `scipy` and NumPy NaN masking.

## Requirements
- Python Environment (Miniconda/Anaconda recommended)
- Support for `Swabian.TimeTagger` driver library
- `PyQt5`, `pyqtgraph`, `numpy`, `scipy`

## Notice for executables
Distributable executable bundles (pyinstaller builds) contain proprietary and dense scientific library structures, often approaching 700MB per `.exe`. These are explicitly disregarded in `.gitignore` to preserve repository lightweight traits and save GitHub LFS limitations.
