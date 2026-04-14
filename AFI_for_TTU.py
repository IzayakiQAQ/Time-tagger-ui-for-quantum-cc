import csv
import ctypes
import datetime
import os
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import traceback

import pyvisa
import win32api
import win32con
import pyautogui
import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_ROOT = os.path.dirname(SCRIPT_DIR)
for path in (SCRIPT_DIR, WORKSPACE_ROOT):
    if path not in sys.path:
        sys.path.append(path)

import afi_tdc_sync


def mouse_leftclick(x, y):
    win32api.SetCursorPos([x, y])
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


# 璇锋眰绠＄悊鍛樻潈闄?
def ensure_admin():
    if os.name != "nt":
        return

    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return
    except Exception:
        pass

    try:
        import elevate
    except ImportError:
        elevate = None

    if elevate is not None:
        elevate.elevate()
        return

    params = subprocess.list2cmdline(sys.argv)
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        params,
        None,
        1,
    )
    if result <= 32:
        raise RuntimeError("Failed to request administrator privileges.")
    sys.exit()


ensure_admin()
# 瀹炰緥鍖杘bject锛屽缓绔嬬獥鍙indow
window = tk.Tk()
window.title('Franson auto.exe')

# 鑾峰彇灞忓箷瀹藉害鍜岄珮搴?
screen_width = window.winfo_screenwidth()
screen_height = window.winfo_screenheight()
# 璁剧疆绐楀彛澶у皬
window_width = 900
window_height = 700
# 璁＄畻绐楀彛宸︿笂瑙掍綅缃娇鍏跺眳涓?
x = (screen_width - window_width) // 2
y = (screen_height - window_height) // 2
# 璁剧疆绐楀彛鐨勫嚑浣曞睘鎬э紝浣垮叾灞呬腑鏄剧ず
window.geometry('{}x{}+{}+{}'.format(window_width, window_height, x, y))

# 鏀剧疆绐楀彛鎺т欢
# 鐢靛帇璁剧疆鏂囨湰
voltage_setting_label = tk.Label(window, text='电压参数设置', font=('Arial', 12), width=10, height=2, bd=2, fg='blue')
voltage_setting_label.place(x=10, y=10)
# 璧峰鐢靛帇
voltage_start_label = tk.Label(window, text='初始电压（V）：', font=('Arial', 12), width=16, height=2)
voltage_start_label.place(x=13, y=61)
voltage_start_entry = tk.Entry(window, textvariable=tk.StringVar(value='10'), font=('Arial', 12), bd=2, relief="groove")
voltage_start_entry.place(x=215, y=72, width=60, height=38)
# 鐢靛帇姝ラ暱
voltage_step_label = tk.Label(window, text='步长（V）：', font=('Arial', 12), width=10, height=2)
voltage_step_label.place(x=353, y=61)
voltage_step_entry = tk.Entry(window, textvariable=tk.StringVar(value='2'), font=('Arial', 12), bd=2, relief="groove")
voltage_step_entry.place(x=488, y=72, width=60, height=38)
# 缁堟鐢靛帇
voltage_end_label = tk.Label(window, text='终止电压（V）：', font=('Arial', 12), width=16, height=2)
voltage_end_label.place(x=603, y=61)
voltage_end_entry = tk.Entry(window, textvariable=tk.StringVar(value='90'), font=('Arial', 12), bd=2, relief="groove")
voltage_end_entry.place(x=808, y=72, width=60, height=38)

# 绛夊緟绋冲畾鏃堕棿
stable_time_label = tk.Label(window, text='等待稳定时间（s）：', font=('Arial', 12), width=16, height=2)
stable_time_label.place(x=36, y=120)
stable_time_entry = tk.Entry(window, textvariable=tk.StringVar(value='5'), font=('Arial', 12), bd=2, relief="groove")
stable_time_entry.place(x=263, y=131, width=60, height=38)

# 鏁版嵁閲囬泦璁剧疆鏂囨湰
collection_setting_label = tk.Label(window, text='TDC参数设置', font=('Arial', 12), width=10, height=2, bd=2,
                                    fg='blue')
collection_setting_label.place(x=35, y=190)


# 鎹曡幏榧犳爣鍧愭爣鎸夐挳
# 鎸夐挳鐐瑰嚮浜嬩欢澶勭悊鍑芥暟
def cursor_pos_button_click():
    cursor_pos_button.config(text="按下Ctrl固定坐标", fg='red')

    def start_listener():
        while win32api.GetKeyState(win32con.VK_CONTROL) >= 0:
            listener_x, listener_y = win32api.GetCursorPos()
            cursor_pos_label.config(text=f"x={listener_x}, y={listener_y}")
            time.sleep(0.05)
        cursor_pos_button.config(text="获取鼠标坐标", fg='green')

    t = threading.Thread(target=start_listener)
    t.start()


cursor_pos_button = tk.Button(window, text="点击获取鼠标坐标", width=15, height=2, font=('Arial', 12), bd=2,
                              relief="ridge",
                              fg='green', command=cursor_pos_button_click)
cursor_pos_button.place(x=425, y=180)
# 榧犳爣鍧愭爣鏂囨湰
cursor_pos_label = tk.Label(window, text='x=0, y=0', font=('Arial', 12), width=14, height=2)
cursor_pos_label.place(x=675, y=184)

# TDC鍚姩鍧愭爣鏂囨湰&娴嬭瘯鎸夐挳
start_setting_label = tk.Label(window, text='TDC启动坐标', font=('Arial', 12), width=10, height=2, bd=2)
start_setting_label.place(x=35, y=280)
start_xPos_label = tk.Label(window, text='x:', font=('Arial', 12), width=10, height=2, bd=2)
start_xPos_label.place(x=280, y=280)
start_xPos_entry = tk.Entry(window, textvariable=tk.StringVar(value='1353'), font=('Arial', 12), bd=2, relief="groove")
start_xPos_entry.place(x=365, y=292, width=60, height=38)
start_yPos_label = tk.Label(window, text='y:', font=('Arial', 12), width=10, height=2, bd=2)
start_yPos_label.place(x=425, y=280)
start_yPos_entry = tk.Entry(window, textvariable=tk.StringVar(value='325'), font=('Arial', 12), bd=2, relief="groove")
start_yPos_entry.place(x=510, y=292, width=60, height=38)


def start_pos_button_click():
    mouse_leftclick(int(start_xPos_entry.get()), int(start_yPos_entry.get()))


start_pos_button = tk.Button(window, text="点击测试坐标", width=12, height=2, font=('Arial', 12), bd=2,
                             relief="ridge", command=start_pos_button_click)
start_pos_button.place(x=680, y=270)

# TDC淇濆瓨鍧愭爣鏂囨湰&娴嬭瘯鎸夐挳
save_setting_label = tk.Label(window, text='TDC保存坐标', font=('Arial', 12), width=10, height=2, bd=2)
save_setting_label.place(x=35, y=365)
save_xPos_label = tk.Label(window, text='x:', font=('Arial', 12), width=10, height=2, bd=2)
save_xPos_label.place(x=280, y=365)
save_xPos_entry = tk.Entry(window, textvariable=tk.StringVar(value='1355'), font=('Arial', 12), bd=2, relief="groove")
save_xPos_entry.place(x=365, y=377, width=60, height=38)
save_yPos_label = tk.Label(window, text='y:', font=('Arial', 12), width=10, height=2, bd=2)
save_yPos_label.place(x=425, y=365)
save_yPos_entry = tk.Entry(window, textvariable=tk.StringVar(value='911'), font=('Arial', 12), bd=2, relief="groove")
save_yPos_entry.place(x=510, y=377, width=60, height=38)


def save_pos_button_click():
    mouse_leftclick(int(save_xPos_entry.get()), int(save_yPos_entry.get()))
    time.sleep(1)
    mouse_leftclick(int(save_xPos_entry.get()) + 40, int(save_yPos_entry.get()) + 10)
    time.sleep(1)
    pyautogui.typewrite(f"10.00V")
    time.sleep(1)
    pyautogui.typewrite('\n\n')


save_pos_button = tk.Button(window, text="点击测试坐标", width=12, height=2, font=('Arial', 12), bd=2,
                            relief="ridge", command=save_pos_button_click)
save_pos_button.place(x=680, y=360)

# 閲囬泦鏃堕棿
collection_time_label = tk.Label(window, text='采集时间（s）：', font=('Arial', 12), width=16, height=2)
collection_time_label.place(x=13, y=440)
collection_time_entry = tk.Entry(window, textvariable=tk.StringVar(value='10'), font=('Arial', 12), bd=2,
                                 relief="groove")
collection_time_entry.place(x=215, y=448, width=60, height=38)

save_dir_label = tk.Label(window, text='保存路径：', font=('Arial', 12), width=12, height=2)
save_dir_label.place(x=11, y=520)
save_dir_entry = tk.Entry(window, textvariable=tk.StringVar(value=r'E:\lzy\demo\data\raw\franson'), font=('Arial', 12), bd=2,
                          relief="groove")
save_dir_entry.place(x=158, y=526, width=690, height=38)

visa_resource_label = tk.Label(window, text='VISA Resource:', font=('Arial', 12), width=12, height=2)
visa_resource_label.place(x=11, y=475)
visa_resource_entry = tk.Entry(window, textvariable=tk.StringVar(value=''), font=('Arial', 12), bd=2,
                               relief="groove")
visa_resource_entry.place(x=158, y=482, width=690, height=38)

auto_checkbox_var = tk.BooleanVar()
auto_checkbox_var.set(True)
auto_checkbox = tk.Checkbutton(window, text="手动", variable=auto_checkbox_var, font=('Arial', 12), width=12, height=2)
auto_checkbox.place(x=270, y=590)


def read_keithley_current(keithley, retries=3, retry_delay=0.1):
    """Read DC current from Keithley with simple retry for transient VISA I/O errors."""
    last_exc = None
    for _ in range(retries):
        try:
            response = keithley.query(":MEAS:CURR?")
            return float(response.split(",")[0].strip())
        except Exception as exc:
            last_exc = exc
            try:
                keithley.clear()
            except Exception:
                pass
            time.sleep(retry_delay)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Failed to read current from Keithley.")


def try_read_keithley_current(keithley, fallback=float("nan")):
    try:
        return read_keithley_current(keithley)
    except Exception as exc:
        print(f"Warning: failed to read Keithley current: {exc}")
        return fallback


def format_current_text(current_reading):
    if isinstance(current_reading, float) and np.isnan(current_reading):
        return "Current unavailable"
    return f"{current_reading * 1E9:+.4f}nA"


SYNC_DIRS = afi_tdc_sync.ensure_sync_dirs(os.path.join(WORKSPACE_ROOT, "afi_tdc_sync"))


def build_voltage_points(start, step, end):
    if step <= 0:
        raise ValueError("Voltage step must be positive.")
    points = []
    current = start
    while current <= end + 1e-9:
        points.append(round(current, 4))
        current += step
    return points


def enqueue_tdc_capture(run_dir, group_name, step_index, voltage, collection_time):
    request_id = afi_tdc_sync.build_request_id(group_name, step_index, voltage)
    voltage_label = f"{voltage:.2f}V"
    payload = {
        "request_id": request_id,
        "group_name": group_name,
        "step_index": step_index,
        "voltage": voltage,
        "voltage_label": voltage_label,
        "collection_time_s": collection_time,
        "run_dir": run_dir,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "status": "pending",
    }
    request_path, done_path = afi_tdc_sync.enqueue_request(SYNC_DIRS, payload)
    processing_path = os.path.join(SYNC_DIRS["processing"], f"{request_id}.json")
    failed_path = os.path.join(SYNC_DIRS["failed"], f"{request_id}.json")
    return request_id, request_path, processing_path, done_path, failed_path


def append_manifest_row(manifest_path, row):
    file_exists = os.path.exists(manifest_path)
    with open(manifest_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "group_name",
                "step_index",
                "voltage_set_v",
                "measured_current_a",
                "request_id",
                "link1_hist",
                "link2_hist",
                "singles_csv",
                "singles_avg_ch1_khz",
                "singles_avg_ch2_khz",
                "singles_avg_ch3_khz",
                "singles_avg_ch4_khz",
                "saved_at",
            ],
        )
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def wait_for_tdc_capture(request_path, processing_path, done_path, failed_path, collection_time):
    try:
        afi_tdc_sync.wait_for_claim_or_done(
            request_path,
            processing_path,
            done_path,
            failed_path,
            timeout_s=5.0,
            poll_s=0.1,
        )
    except TimeoutError as exc:
        raise TimeoutError(
            "ui timestamp 1TDC folder.py 没有接管联动请求。请关闭并重新打开该窗口后再试。"
        ) from exc
    return afi_tdc_sync.wait_for_done(
        done_path,
        failed_path,
        timeout_s=max(collection_time + 20.0, 30.0),
        poll_s=0.1,
    )


def reset_sync_workspace():
    for key in ("requests", "processing", "done", "failed"):
        folder = SYNC_DIRS[key]
        for name in os.listdir(folder):
            if name.lower().endswith(".json"):
                os.remove(os.path.join(folder, name))


def ensure_sync_listener_ready():
    heartbeat = afi_tdc_sync.read_heartbeat(SYNC_DIRS["root"])
    if heartbeat is None:
        raise RuntimeError(
            "没有检测到 ui timestamp 监听器心跳。请先关闭并重新打开 ui timestamp 1TDC folder.py。"
        )
    age_s = time.time() - float(heartbeat.get("updated_at", 0))
    if age_s > 2.0 or int(heartbeat.get("listener_version", 0)) < 1:
        raise RuntimeError(
            "检测到的 ui timestamp 监听器不是最新状态。请关闭并重新打开 ui timestamp 1TDC folder.py。"
        )


def run_group_capture(
    keithley,
    voltages,
    voltage_end,
    stable_time,
    collection_time,
    group_name,
    run_dir,
    manifest_path,
    pause_before_next=False,
):
    os.makedirs(os.path.join(run_dir, group_name), exist_ok=True)
    for step_index, current_voltage in enumerate(voltages, start=1):
        keithley.write(":SOUR:VOLT:LEV %.4f" % current_voltage)
        keithley.write(":OUTP ON ")
        current_reading = float("nan")
        if stable_time > 0:
            wait_s = stable_time + (15 if step_index == 1 else 0)
            target_time = time.perf_counter() + wait_s
            next_read_time = time.perf_counter()
            while True:
                now = time.perf_counter()
                if now >= target_time:
                    break
                if now >= next_read_time:
                    current_reading = try_read_keithley_current(keithley, current_reading)
                    next_read_time = now + 0.5
                current_voltage_label.config(
                    text=(
                        f"{current_voltage: .2f}V/{voltage_end: .2f}V"
                        f"（等待源表稳定）\n{format_current_text(current_reading)} {group_name}"
                    ),
                    fg='blue',
                )
                time.sleep(0.05)
            current_reading = try_read_keithley_current(keithley, current_reading)
        else:
            current_reading = try_read_keithley_current(keithley, current_reading)
            current_voltage_label.config(
                text=(
                    f"{current_voltage: .2f}V/{voltage_end: .2f}V"
                    f"（等待源表稳定）\n{format_current_text(current_reading)} {group_name}"
                ),
                fg='blue',
            )

        request_id, request_path, processing_path, done_path, failed_path = enqueue_tdc_capture(
            run_dir, group_name, step_index, current_voltage, collection_time
        )
        target_time = time.perf_counter() + collection_time
        while True:
            remaining = target_time - time.perf_counter()
            if remaining <= 0:
                break
            current_voltage_label.config(
                text=(
                    f"{current_voltage: .2f}V/{voltage_end: .2f}V"
                    f"（采集数据中）\n剩余{remaining:.1f}s {group_name}"
                ),
                fg='green',
            )
            time.sleep(0.05)

        if pause_before_next:
            current_voltage_label.config(
                text=f"{current_voltage: .2f}V/{voltage_end: .2f}V（手动）",
                fg='black',
            )
            while auto_checkbox_var.get() is True:
                time.sleep(0.05)

        result_payload = wait_for_tdc_capture(
            request_path,
            processing_path,
            done_path,
            failed_path,
            collection_time,
        )
        saved_files = result_payload.get("saved_files", {})
        avg_rates = result_payload.get("singles_avg_khz", ["", "", "", ""])
        append_manifest_row(
            manifest_path,
            {
                "group_name": group_name,
                "step_index": step_index,
                "voltage_set_v": f"{current_voltage:.4f}",
                "measured_current_a": f"{current_reading:.12e}",
                "request_id": request_id,
                "link1_hist": saved_files.get("link1_hist", ""),
                "link2_hist": saved_files.get("link2_hist", ""),
                "singles_csv": saved_files.get("singles", ""),
                "singles_avg_ch1_khz": avg_rates[0] if len(avg_rates) > 0 else "",
                "singles_avg_ch2_khz": avg_rates[1] if len(avg_rates) > 1 else "",
                "singles_avg_ch3_khz": avg_rates[2] if len(avg_rates) > 2 else "",
                "singles_avg_ch4_khz": avg_rates[3] if len(avg_rates) > 3 else "",
                "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
            },
        )

def start_button_click():
    start_button.config(state="disabled")
    start_button.config(text="运行中", fg='red')

    def start_button_thread():
        Keithley2450 = None
        try:
            # 鑾峰彇绐楀彛鏁版嵁
            voltage_start = float(voltage_start_entry.get())
            voltage_step = float(voltage_step_entry.get())
            voltage_end = float(voltage_end_entry.get())
            stable_time = float(stable_time_entry.get())
            collection_time = float(collection_time_entry.get())
            save_dir = save_dir_entry.get()
            visa_resource = visa_resource_entry.get().strip()
            voltage_points = build_voltage_points(voltage_start, voltage_step, voltage_end)
            ensure_sync_listener_ready()
            reset_sync_workspace()
            run_stamp = datetime.datetime.now().strftime("run_%Y%m%d_%H%M%S")
            run_dir = os.path.join(save_dir, run_stamp)
            os.makedirs(run_dir, exist_ok=True)
            manifest_path = os.path.join(run_dir, "manifest.csv")

            # 杩炴帴鍒版簮琛?
            try:
                rm = pyvisa.ResourceManager()
            except ValueError as e:
                if "Could not locate a VISA implementation" in str(e):
                    rm = pyvisa.ResourceManager("@py")
                else:
                    raise
            res = rm.list_resources()
            print("Available equipments:", res)
            if visa_resource:
                Keithley2450 = rm.open_resource(visa_resource)
            elif res:
                Keithley2450 = rm.open_resource(res[0])
            else:
                raise RuntimeError(
                    "No VISA instruments found. Check cable/address/power, or enter VISA Resource manually."
                )
            Keithley2450.timeout = 20000
            Keithley2450.read_termination = "\n"
            Keithley2450.write_termination = "\n"
            try:
                Keithley2450.clear()
            except Exception:
                pass
            Keithley2450.write("*CLS")
            print("Initialize: " + Keithley2450.query("*IDN?").strip())
            Keithley2450.write(":SOUR:FUNC VOLT")
            Keithley2450.write(":SENS:FUNC \"CURR\"")
            Keithley2450.write(":SENS:CURR:RANG:AUTO 1")
            Keithley2450.write(":SOUR:VOLT:RANG:AUTO 1")
            run_group_capture(
                Keithley2450,
                voltage_points,
                voltage_end,
                stable_time,
                collection_time,
                "group1",
                run_dir,
                manifest_path,
                pause_before_next=False,
            )
            run_group_capture(
                Keithley2450,
                voltage_points,
                voltage_end,
                stable_time,
                collection_time,
                "group2",
                run_dir,
                manifest_path,
                pause_before_next=True,
            )
            start_button.config(text="开始", fg='green')
            current_voltage_label.config(text=f"已完成\n{run_dir}", fg='green')
            start_button.config(state="normal")
            if Keithley2450 is not None:
                try:
                    Keithley2450.write(":OUTP OFF ")
                except Exception:
                    pass
            return


        except Exception:
            traceback.print_exc()
            current_voltage_label.config(text="请查看控制台报错信息！", fg='red')
            start_button.config(state="normal")
            if Keithley2450 is not None:
                try:
                    Keithley2450.write(":OUTP OFF ")
                except Exception:
                    pass
        else:
            start_button.config(text="开始", fg='green')
            current_voltage_label.config(text="已完成", fg='green')
            start_button.config(state="normal")
            if Keithley2450 is not None:
                try:
                    Keithley2450.write(":OUTP OFF ")
                except Exception:
                    pass

    t = threading.Thread(target=start_button_thread)
    t.start()


start_button = tk.Button(window, text="开始", width=12, height=2, font=('Arial', 12), bd=2,
                         relief="ridge", command=start_button_click)
start_button.place(x=120, y=590)
current_voltage_label = tk.Label(window, text='当前电压：NAN/NAN', font=('Arial', 12), width=30, height=2)
current_voltage_label.place(x=420, y=595)

# 涓荤獥鍙ｅ惊鐜樉绀?
window.mainloop()
