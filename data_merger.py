import os
import re
import glob
import numpy as np
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

# ================= 配置区域 =================
INPUT_DIR = r"E:\lzy\2026.3.5 0km 2m单边"
OUTPUT_DIR = r"E:\lzy\2026.3.5 0km 2m单边_Merged"

# 每多少个文件合并成1组
GROUP_SIZE = 10

# 正则表达式用于提取文件的 Cycle 编号和 Link 编号
# 文件大致长相: Cycle_001_Link1_20260304_212621.txt
FILE_PATTERN = re.compile(r"Cycle_(\d+)_Link(\d+)_(.*)\.txt")
# ==========================================

def get_header_lines(filepath):
    """读取文件开头的文本头部信息(如果有的)，通常是由 TimeTaggerUI 生成的"""
    header = []
    try:
        with open(filepath, 'r') as f:
            for _ in range(2): # 读取前两行 (Duration / Bin)
                line = f.readline()
                if not line.strip() or line[0].isdigit() or line.startswith('-'):
                    break
                # 将原来的 Duration 乘以我们要合并的系数
                if "Duration:" in line:
                    parts = line.split(":")
                    if len(parts) == 2:
                        try:
                            dur = float(parts[1].strip())
                            header.append(f"# Duration: {dur * GROUP_SIZE}\n")
                        except:
                            header.append(f"# {line}")
                else:
                    header.append(f"# {line}")
    except:
        pass
    return "".join(header) if header else ""

def process_chunk(chunk_id, files_list, out_filename):
    """处理一组 (GROUP_SIZE) 个文件的叠加逻辑"""
    if not files_list:
        return False
        
    try:
        # 1. 以外部第一个文件为基准，提取它的标头和 x 轴时间序列
        base_file = files_list[0]
        header_text = get_header_lines(base_file)
        
        # 读取主干数据，跳过前两行文本(如果遇到非数字头部的话)
        base_df = pd.read_csv(base_file, sep=r'\s+', comment='#', header=None, engine='c', dtype=float)
        
        x_axis = base_df.iloc[:, 0].values
        aggregated_y = base_df.iloc[:, 1].values.copy()
        
        # 2. 将剩余 (GROUP_SIZE - 1) 个文件的计数 Y 列做累加
        for fpath in files_list[1:]:
            df = pd.read_csv(fpath, sep=r'\s+', comment='#', header=None, engine='c', dtype=float)
            if len(df) == len(aggregated_y):
                aggregated_y += df.iloc[:, 1].values
            else:
                print(f"警告：文件 {os.path.basename(fpath)} 行数不匹配！跳过累加该文件。")
        
        # 3. 输出合并后的新直方图
        combined_data = np.column_stack((x_axis, aggregated_y))
        output_path = os.path.join(OUTPUT_DIR, out_filename)
        
        # np.savetxt 会利用内置的 C 语言内核快速把矩阵无损写回 txt 文本
        np.savetxt(output_path, combined_data, fmt="%.1f\t%d", header=header_text.strip(), comments='')
        return True
        
    except Exception as e:
        print(f"合并 Chunk {chunk_id} 时发生系统错误: {e}")
        return False

def main():
    if not os.path.exists(INPUT_DIR):
        print(f"找不到输入的源数据目录：{INPUT_DIR}")
        return

    print("正在扫描原始文件(可能需要几秒钟)...")
    all_txt = glob.glob(os.path.join(INPUT_DIR, "Cycle_*_Link*.txt"))
    
    if not all_txt:
        print("指定目录中没有找到匹配的 Cycle_xxx_Link 文本文件！")
        return

    # 按 Link 分组收集文件信息: {'1': [(cycle_num, filepath, timestamp)], '2': [...]}
    link_data = {'1': [], '2': []}
    
    for fpath in all_txt:
        fname = os.path.basename(fpath)
        match = FILE_PATTERN.search(fname)
        if match:
            c_num = int(match.group(1))
            l_num = match.group(2)
            ts_str = match.group(3)
            
            if l_num in link_data:
                link_data[l_num].append((c_num, fpath, ts_str))

    # 按照实际采集的 Cycle 编号将它们严格升序排序
    link_data['1'].sort(key=lambda x: x[0])
    link_data['2'].sort(key=lambda x: x[0])

    print(f"目录共发现 Link 1 文件: {len(link_data['1'])} 个")
    print(f"目录共发现 Link 2 文件: {len(link_data['2'])} 个")
    
    # 建目标存放目录
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"已创建独立输出目录: {OUTPUT_DIR}")

    # ===== 准备并发合并的任务 =====
    tasks = []
    
    for link_id in ['1', '2']:
        files_for_link = link_data[link_id]
        total_files = len(files_for_link)
        
        # 使用切片，将比如 86400 个文件，切分为 8640 组（每组 10 个）
        for group_idx, i in enumerate(range(0, total_files, GROUP_SIZE)):
            chunk = files_for_link[i : i + GROUP_SIZE]
            
            # 只有恰好满足 10 个文件才算一组进行合并。这能够避开用户中间随意开关程序留下的不完整废数据
            if len(chunk) == GROUP_SIZE:
                new_cycle_num = group_idx + 1 # 新的从 1 开始的新 Cycle 号
                
                # 将取第一个文件的时间戳作为合并文件名的指纹
                ref_ts = chunk[0][2]
                out_name = f"Cycle_{new_cycle_num:03d}_Link{link_id}_{ref_ts}_Merged.txt"
                
                file_paths_only = [t[1] for t in chunk]
                tasks.append(({
                    'chunk_id': f"L{link_id}-{new_cycle_num}",
                    'files': file_paths_only,
                    'out_name': out_name
                }))

    if not tasks:
        print("未生成任何合并任务。可能单组文件不足批量大小。")
        return

    print(f"构建了 {len(tasks)} 个合并任务批次 (每批 {GROUP_SIZE} 个文本). 开始多核心并发执行！")
    
    success_count = 0
    # ====== 高速并发任务列队 ======
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = {
            executor.submit(process_chunk, t['chunk_id'], t['files'], t['out_name']): t 
            for t in tasks
        }
        
        # 使用 tqdm 画进度条展示当前的合并流转速率
        for future in tqdm(as_completed(futures), total=len(futures), desc="Merging files"):
            if future.result():
                success_count += 1
                
    print(f"\n==============================================")
    print(f"全部合并完成！共收割缩小出 {success_count} 份独立的新合并直方图文件。")
    print(f"您可以前往检查：{OUTPUT_DIR}")
    print(f"==============================================\n")

if __name__ == "__main__":
    main()
