import os
import re
import glob
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

# ================= 配置区域 =================

DATA_DIR = r"E:\lzy\2026.2.1"
OUTPUT_FILENAME = "clock_diff_filled.csv"

# 拟合参数
MIN_PEAK_COUNTS = 40
FIT_WIDTH_GUESS = 600

# 裁剪参数 (只拟合峰值附近的数据)
CROP_WINDOW = 2000


# ================= 核心算法 =================

def gaussian(x, y0, xc, w, A):
    return y0 + A * np.exp(-0.5 * ((x - xc) / w) ** 2)


def process_single_file_fast(filepath):
    try:
        # 使用 pandas C引擎快速读取
        df = pd.read_csv(filepath, sep=r'\s+', header=None, engine='c', dtype=float)

        if df.empty:
            return None

        x = df.iloc[:, 0].values
        y = df.iloc[:, 1].values

        # 1. 快速找最大值
        max_idx = np.argmax(y)
        peak_y = y[max_idx]

        if peak_y < MIN_PEAK_COUNTS:
            return None

        peak_x = x[max_idx]

        # 2. 数据裁剪 (ROI Clipping) - 极大提升速度
        start_idx = max(0, max_idx - CROP_WINDOW)
        end_idx = min(len(y), max_idx + CROP_WINDOW)

        if end_idx - start_idx < 50:
            x_fit = x
            y_fit = y
        else:
            x_fit = x[start_idx:end_idx]
            y_fit = y[start_idx:end_idx]

        min_y = np.min(y_fit)

        # 3. 拟合
        p0 = [min_y, peak_x, FIT_WIDTH_GUESS, peak_y - min_y]

        bounds = (
            [0, np.min(x_fit) - 100, 10, 0],
            [np.max(y) * 1.5, np.max(x_fit) + 100, 10000, np.inf]
        )

        try:
            popt, _ = curve_fit(gaussian, x_fit, y_fit, p0=p0, bounds=bounds, maxfev=1000)
            return popt[1]
        except RuntimeError:
            return np.nan

    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return np.nan


def process_cycle_pair(cycle_id, file_pair):
    path1 = file_pair.get('link1')
    path2 = file_pair.get('link2')

    # 初始化默认值
    val1 = np.nan
    val2 = np.nan

    # 尝试处理 Link 1
    if path1:
        res1 = process_single_file_fast(path1)
        if res1 is not None and not np.isnan(res1):
            val1 = res1

    # 尝试处理 Link 2
    if path2:
        res2 = process_single_file_fast(path2)
        if res2 is not None and not np.isnan(res2):
            val2 = res2

    correction = (val1 - val2) / 2.0

    return {
        'Cycle': cycle_id,
        'Link1_Delay_ps': val1,
        'Link2_Delay_ps': val2,
        'Clock_Correction_ps': correction
    }


# ================= 主逻辑 =================

def main():
    if not os.path.exists(DATA_DIR):
        print("目录不存在")
        return

    # 1. 扫描文件
    print("Scanning files...")
    files = glob.glob(os.path.join(DATA_DIR, "*.txt"))

    pattern = re.compile(r"Cycle_(\d+)_Link(\d+)_")
    tasks = {}

    for f in files:
        fname = os.path.basename(f)
        match = pattern.search(fname)
        if match:
            c = int(match.group(1))
            l = int(match.group(2))
            if c not in tasks: tasks[c] = {}
            if l == 1:
                tasks[c]['link1'] = f
            elif l == 2:
                tasks[c]['link2'] = f

    sorted_cycles = sorted(tasks.keys())

    print(f"Starting processing for {len(sorted_cycles)} cycles...")

    results = []

    # 并行处理
    with ProcessPoolExecutor() as executor:
        future_to_cycle = {
            executor.submit(process_cycle_pair, c, tasks[c]): c
            for c in sorted_cycles
        }

        for future in tqdm(as_completed(future_to_cycle), total=len(sorted_cycles), unit="cycle"):
            res = future.result()
            if res:
                results.append(res)

    if results:
        results.sort(key=lambda x: x['Cycle'])
        df = pd.DataFrame(results)

        valid_df = df.dropna(subset=['Clock_Correction_ps'])
        if not valid_df.empty:
            # ==== 新增异常数据点修正 ====
            # 根据中位数拉回偏离过10ps的异常数据，确保拟合时序连续不畸变
            median_val = valid_df['Clock_Correction_ps'].median()
            threshold = 10.0
            
            is_outlier = np.abs(df['Clock_Correction_ps'] - median_val) > threshold
            outliers_count = is_outlier.sum()
            
            if outliers_count > 0:
                print(f"\n警告：检测到 {outliers_count} 个大幅偏离(>{threshold}ps)的异常数据点！")
                print(f"正在强行将异常点修正回正常有效边界内（[ {median_val-threshold:.2f}, {median_val+threshold:.2f} ]）...")
                df['Clock_Correction_ps'] = np.clip(
                    df['Clock_Correction_ps'], 
                    median_val - threshold, 
                    median_val + threshold
                )
            
            std_dev = df['Clock_Correction_ps'].std()
            print(f"Non-null Std Dev (修正后/Final): {std_dev:.4f} ps")
        else:
            print("Warning: All results are invalid (NaN).")

        output_path = os.path.join(DATA_DIR, OUTPUT_FILENAME)
        df.to_csv(output_path, index=False, float_format='%.4f')
        print(f"\nDone! {len(df)} records saved to {output_path}")

    else:
        print("No cycles found.")

    input("Press Enter to exit...")

if __name__ == "__main__":
    main()
