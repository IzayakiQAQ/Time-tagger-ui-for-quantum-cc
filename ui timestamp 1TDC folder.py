import sys
import time
import os
import datetime
import numpy as np
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from PyQt5 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg
import threading

# ================== 配置与常量 ==================
SERIAL_NUMBER = "22440012ZN"
DEFAULT_SAVE_DIR = r"E:\lzy\2026"

try:
    import Swabian.TimeTagger
except ImportError:
    class MockSwabian:
        TimeTagger = None


    Swabian = MockSwabian()

STYLE_SHEET = """
QMainWindow { background-color: #2b2b2b; color: #e0e0e0; }
QWidget { background-color: #2b2b2b; color: #e0e0e0; font-family: "Segoe UI", sans-serif; }
QGroupBox { border: 1px solid #444; border-radius: 4px; margin-top: 10px; padding-top: 10px; font-weight: bold; color: #00bcd4; }
QPushButton { background-color: #3c3c3c; border: 1px solid #555; border-radius: 3px; padding: 6px; color: #fff; font-weight: bold; }
QPushButton:hover { background-color: #4c4c4c; border-color: #00bcd4; }
QPushButton#btn_start { background-color: #2e7d32; font-size: 12pt; }
QPushButton#btn_stop { background-color: #c62828; font-size: 12pt; }
QPushButton#btn_search { background-color: #f57f17; color: #000; font-weight: bold; border: none; }
QPushButton#btn_search:hover { background-color: #fbc02d; }
QLabel { color: #bbb; }
QLineEdit, QSpinBox, QDoubleSpinBox { background-color: #1e1e1e; border: 1px solid #444; border-radius: 2px; padding: 4px; color: #00e5ff; font-family: "Consolas", monospace; font-size: 11pt; }
"""


class HardwareInterface:
    def __init__(self):
        self.tt = None

    def initialize(self):
        if Swabian.TimeTagger is None: return False, "TimeTagger Library Missing"
        try:
            self.tt = Swabian.TimeTagger.createTimeTagger(SERIAL_NUMBER)
            return True, f"TDC Connected: {SERIAL_NUMBER}"
        except Exception as e:
            return False, str(e)


hw = HardwareInterface()


class ExperimentWorker(QtCore.QThread):
    status_update = QtCore.pyqtSignal(object, object, object, str, int)
    cycle_finished = QtCore.pyqtSignal(int, object, object, float)
    acq_finished = QtCore.pyqtSignal()
    peak_found = QtCore.pyqtSignal(int, float, float)
    debug_msg = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.config_lock = threading.Lock()
        self.running = False
        self.mode = 'repeat'
        self.duration = 1.0
        self.max_cycles = 1
        self.peak_threshold = 5
        self.configs = [{}, {}]
        self.bin_ps = 100
        self.window_ps = 10000
        self.buf = deque()
        self.monitor = None
        self.integ_time_s = 0.5
        self.hist_acc_1 = np.zeros(1)
        self.hist_acc_2 = np.zeros(1)
        self.search_request_idx = None

    def setup_global(self, bin_ps, win_ps):
        self.bin_ps, self.window_ps = int(bin_ps), int(win_ps)
        num_bins = (int(2 * self.window_ps) // self.bin_ps)
        if num_bins % 2 != 0: num_bins += 1
        self.hist_acc_1 = np.zeros(num_bins, dtype=np.int32)
        self.hist_acc_2 = np.zeros(num_bins, dtype=np.int32)
        self.axis_bins = np.arange(-num_bins // 2, num_bins // 2 + 1) * self.bin_ps
        if hw.tt:
            self.monitor = Swabian.TimeTagger.Counter(hw.tt, list(range(1, 9)), int(self.integ_time_s * 1e12), 1)

    def trigger_auto_search(self, link_idx):
        self.search_request_idx = link_idx

    def run(self):
        if not hw.tt: return
        with self.config_lock:
            ch_list = set()
            for c in self.configs:
                if c: ch_list.update([c['s'], c['p']])

        if not ch_list:
            self.status_update.emit(self.hist_acc_1, self.hist_acc_2, [0] * 4, "Error: No Channels", 0)
            return

        stream = Swabian.TimeTagger.TimeTagStream(hw.tt, 2000000, list(ch_list))
        stream.start()
        self.start_time = time.time()
        self.current_cycle = 1
        last_ui = time.time()

        while self.running:
            now = time.time()
            data = stream.getData()
            ts, ch = data.getTimestamps(), data.getChannels()
            if len(ts) > 0: self.buf.append((ts, ch))

            if self.search_request_idx is not None:
                total_ev = sum(len(x[0]) for x in self.buf)
                if total_ev > 20000:
                    self._perform_wide_search(self.search_request_idx)
                    self.search_request_idx = None
                else:
                    time.sleep(0.001);
                    continue
            else:
                self._process_histogram()

            # UI Update
            if now - last_ui > 0.1:
                rates = []
                if self.monitor:
                    raw_rates = self.monitor.getData()
                    rates = [(raw_rates[i][0] / self.integ_time_s) / 1000.0 for i in range(4)]
                elapsed = now - self.start_time
                prog = 100 if self.mode == 'free' else int((elapsed / self.duration) * 100)

                status_str = f"Cycle {self.current_cycle}"
                if self.mode == 'repeat':
                    status_str += f" / {self.max_cycles}"

                self.status_update.emit(self.hist_acc_1.copy(), self.hist_acc_2.copy(), rates,
                                        status_str, min(100, prog))
                last_ui = now

            # Cycle Check Logic
            if self.mode != 'free' and (now - self.start_time) >= self.duration:
                self.cycle_finished.emit(self.current_cycle, self.hist_acc_1.copy(), self.hist_acc_2.copy(),
                                         self.duration)

                should_stop = False
                if self.mode == 'single':
                    should_stop = True
                elif self.mode == 'repeat' and self.current_cycle >= self.max_cycles:
                    should_stop = True

                if should_stop:
                    self.running = False
                    self.acq_finished.emit()
                else:
                    self.current_cycle += 1
                    self.start_time = time.time()
                    self.hist_acc_1.fill(0)
                    self.hist_acc_2.fill(0)

            time.sleep(0.001)
        stream.stop()

    def _merge_buf(self):
        if not self.buf: return np.array([]), np.array([])
        return np.concatenate([x[0] for x in self.buf]), np.concatenate([x[1] for x in self.buf])

    def _perform_wide_search(self, idx):
        ts, ch = self._merge_buf()
        with self.config_lock:
            if not self.configs[idx]:
                self.buf.clear(); return
            cfg = self.configs[idx].copy()
        t_start, t_stop = ts[ch == cfg['s']], ts[ch == cfg['p']]
        if len(t_start) == 0 or len(t_stop) == 0: self.buf.clear(); return
        wide_win = 500000000
        idx_arr = np.searchsorted(t_stop, t_start)
        candidates = []
        valid = idx_arr < len(t_stop)
        if np.any(valid):
            d = t_stop[idx_arr[valid]] - t_start[valid]
            candidates.append(d[d < wide_win])
        valid_prev = idx_arr > 0
        if np.any(valid_prev):
            d = t_stop[idx_arr[valid_prev] - 1] - t_start[valid_prev]
            candidates.append(d[d > -wide_win])
        if not candidates: self.buf.clear(); return
        all_d = np.concatenate(candidates)
        if len(all_d) < 10: self.buf.clear(); return
        bins = np.arange(-wide_win, wide_win, 10000)
        counts, edges = np.histogram(all_d, bins=bins)
        max_idx = np.argmax(counts)
        peak_pos = (edges[max_idx] + edges[max_idx + 1]) / 2

        if counts[max_idx] > self.peak_threshold:
            self.peak_found.emit(idx, peak_pos, counts[max_idx])

        self.buf.clear()

    def _process_histogram(self):
        if not self.buf: return
        ts, ch = self._merge_buf();
        self.buf.clear()
        with self.config_lock:
            configs_copy = [c.copy() if c else {} for c in self.configs]
        for i in range(2):
            cfg = configs_copy[i]
            if not cfg: continue
            acc = self.hist_acc_1 if i == 0 else self.hist_acc_2
            t_s, t_p = ts[ch == cfg['s']], ts[ch == cfg['p']]
            if len(t_s) == 0 or len(t_p) == 0: continue
            t_p_shifted = t_p + cfg['off']
            idx = np.searchsorted(t_p_shifted, t_s)
            diffs = []
            for shift in [0, -1]:
                ii = idx + shift
                mask = (ii >= 0) & (ii < len(t_p_shifted))
                if np.any(mask):
                    d = t_p_shifted[ii[mask]] - t_s[mask]
                    diffs.append(d[(d > -self.window_ps) & (d < self.window_ps)])
            if diffs:
                counts, _ = np.histogram(np.concatenate(diffs), bins=self.axis_bins)
                acc += counts.astype(np.int32)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QTWTT Single TDC - Coincidence Master")
        self.resize(1300, 950)
        self.setStyleSheet(STYLE_SHEET)
        ok, msg = hw.initialize()
        self.worker = ExperimentWorker()
        self.save_pool = ThreadPoolExecutor(max_workers=4)

        self.curr_x = None
        self.curr_h1 = None
        self.curr_h2 = None

        self._init_ui()
        self.lbl_status.setText(msg)
        self.worker.status_update.connect(self.update_ui)
        self.worker.cycle_finished.connect(self.save_data)
        self.worker.acq_finished.connect(self.on_finished)
        self.worker.peak_found.connect(self.on_auto_peak_found)

    def _init_ui(self):
        central = QtWidgets.QWidget();
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)
        sidebar = QtWidgets.QWidget();
        sidebar.setFixedWidth(350);
        side_layout = QtWidgets.QVBoxLayout(sidebar)

        self.ui_links = []
        for i in range(1, 3):
            gb = QtWidgets.QGroupBox(f"LINK {i}")
            fl = QtWidgets.QFormLayout()
            s_ch = QtWidgets.QSpinBox();
            s_ch.setRange(1, 8);
            s_ch.setValue(1 if i == 1 else 3)
            p_ch = QtWidgets.QSpinBox();
            p_ch.setRange(1, 8);
            p_ch.setValue(2 if i == 1 else 4)
            dly = QtWidgets.QDoubleSpinBox();
            dly.setRange(-1e9, 1e9);
            dly.setSuffix(" ns");
            dly.setDecimals(3)
            btn_search = QtWidgets.QPushButton("Auto Search (Wide)");
            btn_search.setObjectName("btn_search")
            btn_search.clicked.connect(lambda checked, idx=i - 1: self.request_search(idx))
            fl.addRow("Start CH:", s_ch);
            fl.addRow("Stop CH:", p_ch);
            fl.addRow("Offset:", dly);
            fl.addRow(btn_search)
            gb.setLayout(fl);
            side_layout.addWidget(gb)
            self.ui_links.append({'s': s_ch, 'p': p_ch, 'd': dly, 'btn': btn_search})

        gb_mode = QtWidgets.QGroupBox("MODE");
        v_mode = QtWidgets.QVBoxLayout()
        self.rb_free = QtWidgets.QRadioButton("Free Run");
        self.rb_single = QtWidgets.QRadioButton("Single Shot");
        self.rb_repeat = QtWidgets.QRadioButton("Repeated")
        self.rb_repeat.setChecked(True);
        v_mode.addWidget(self.rb_free);
        v_mode.addWidget(self.rb_single);
        v_mode.addWidget(self.rb_repeat);
        gb_mode.setLayout(v_mode);
        side_layout.addWidget(gb_mode)

        gb_ctrl = QtWidgets.QGroupBox("CONTROL & SAVE");
        v_ctrl = QtWidgets.QVBoxLayout()

        # 基础参数
        self.sb_dur = QtWidgets.QDoubleSpinBox();
        self.sb_dur.setValue(1.0);
        self.sb_cyc = QtWidgets.QSpinBox();
        self.sb_cyc.setRange(1, 999999)
        self.sb_cyc.setValue(10)
        self.sb_threshold = QtWidgets.QSpinBox();
        self.sb_threshold.setRange(1, 10000)
        self.sb_threshold.setValue(5)

        form_ctrl = QtWidgets.QFormLayout()
        form_ctrl.addRow("Duration (s):", self.sb_dur)
        form_ctrl.addRow("Cycles:", self.sb_cyc)
        form_ctrl.addRow("Search Thresh:", self.sb_threshold)  # [新增]
        v_ctrl.addLayout(form_ctrl)

        h_path = QtWidgets.QHBoxLayout()
        self.le_path = QtWidgets.QLineEdit(DEFAULT_SAVE_DIR)
        btn_browse = QtWidgets.QPushButton("...")
        btn_browse.setFixedWidth(30)
        btn_browse.clicked.connect(self.browse_folder)
        h_path.addWidget(self.le_path)
        h_path.addWidget(btn_browse)
        v_ctrl.addWidget(QtWidgets.QLabel("Save Directory:"))
        v_ctrl.addLayout(h_path)

        self.btn_start = QtWidgets.QPushButton("START");
        self.btn_start.setObjectName("btn_start");
        self.btn_start.clicked.connect(self.toggle_start)
        v_ctrl.addWidget(self.btn_start)

        self.lbl_status = QtWidgets.QLabel("Ready");
        v_ctrl.addWidget(self.lbl_status);
        self.bar = QtWidgets.QProgressBar();
        v_ctrl.addWidget(self.bar);
        gb_ctrl.setLayout(v_ctrl);
        side_layout.addWidget(gb_ctrl)

        gb_mon = QtWidgets.QGroupBox("MONITOR (kHz)");
        g_mon = QtWidgets.QGridLayout();
        self.lbl_rates = []
        for i in range(4):
            l = QtWidgets.QLabel("0.0");
            g_mon.addWidget(QtWidgets.QLabel(f"CH{i + 1}"), i, 0);
            g_mon.addWidget(l, i, 1);
            self.lbl_rates.append(l)
        gb_mon.setLayout(g_mon);
        side_layout.addWidget(gb_mon);
        side_layout.addStretch();
        layout.addWidget(sidebar)

        right_w = QtWidgets.QWidget();
        right_layout = QtWidgets.QVBoxLayout(right_w)
        h_set = QtWidgets.QHBoxLayout()
        self.sb_bin = QtWidgets.QSpinBox();
        self.sb_bin.setRange(1, 10000);
        self.sb_bin.setValue(100)
        self.sb_win = QtWidgets.QSpinBox();
        self.sb_win.setRange(100, int(1e8));
        self.sb_win.setValue(100000)
        btn_apply = QtWidgets.QPushButton("Apply Settings");
        btn_apply.clicked.connect(self.apply_settings)
        h_set.addWidget(QtWidgets.QLabel("Bin (ps):"));
        h_set.addWidget(self.sb_bin);
        h_set.addWidget(QtWidgets.QLabel("Window (ps):"));
        h_set.addWidget(self.sb_win);
        h_set.addWidget(btn_apply);
        right_layout.addLayout(h_set)

        # Plot 1 & ROI
        self.p1 = pg.PlotWidget(title="Link 1");
        self.c1 = self.p1.plot(pen='#00e5ff')
        self.roi1 = pg.LinearRegionItem([0, 0], brush=(255, 255, 0, 40))
        self.roi1.sigRegionChanged.connect(lambda: self.update_sum(1))
        self.p1.addItem(self.roi1)
        self.txt1 = pg.TextItem("Sum: 0", color=(255, 255, 0), anchor=(1, 0));
        self.p1.addItem(self.txt1)

        # Plot 2 & ROI
        self.p2 = pg.PlotWidget(title="Link 2");
        self.c2 = self.p2.plot(pen='#ff4081')
        self.roi2 = pg.LinearRegionItem([0, 0], brush=(255, 255, 0, 40))
        self.roi2.sigRegionChanged.connect(lambda: self.update_sum(2))
        self.p2.addItem(self.roi2)
        self.txt2 = pg.TextItem("Sum: 0", color=(255, 255, 0), anchor=(1, 0));
        self.p2.addItem(self.txt2)

        right_layout.addWidget(self.p1);
        right_layout.addWidget(self.p2);
        layout.addWidget(right_w)

    def browse_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Save Directory", self.le_path.text())
        if folder:
            self.le_path.setText(folder)

    def update_sum(self, idx):
        """计算框选区域内的计数值总和"""
        if self.curr_x is None: return
        roi = self.roi1 if idx == 1 else self.roi2
        data = self.curr_h1 if idx == 1 else self.curr_h2
        txt = self.txt1 if idx == 1 else self.txt2

        low, high = roi.getRegion()
        mask = (self.curr_x >= low) & (self.curr_x <= high)
        total = np.sum(data[mask])

        txt.setText(f"Sum: {int(total):,}")
        txt.setPos(high, np.max(data) * 0.9 if np.max(data) > 0 else 10)

    def request_search(self, idx):
        if not self.worker.running: return
        self.ui_links[idx]['btn'].setEnabled(False);

        self.worker.peak_threshold = self.sb_threshold.value()
        self.worker.trigger_auto_search(idx)

    def on_auto_peak_found(self, idx, raw_delay_ps, counts):
        self.ui_links[idx]['btn'].setEnabled(True)
        new_offset_ns = -(raw_delay_ps / 1000.0)
        self.ui_links[idx]['d'].setValue(new_offset_ns)
        self.apply_settings()

    def apply_settings(self):
        self.worker.setup_global(self.sb_bin.value(), self.sb_win.value())
        with self.worker.config_lock:
            for i in range(2):
                self.worker.configs[i] = {'s': self.ui_links[i]['s'].value(), 'p': self.ui_links[i]['p'].value(),
                                          'off': int(self.ui_links[i]['d'].value() * 1000)}
        num_bins = len(self.worker.hist_acc_1)
        self.curr_x = (np.arange(num_bins) - num_bins // 2) * self.worker.bin_ps
        
        win = self.sb_win.value()
        self.p1.setXRange(-win, win);
        self.p2.setXRange(-win, win)
        if abs(self.roi1.getRegion()[1]) < 1: self.roi1.setRegion([-win / 250, win / 250])
        if abs(self.roi2.getRegion()[1]) < 1: self.roi2.setRegion([-win / 250, win / 250])

    def toggle_start(self):
        if self.worker.running:
            self.worker.running = False;
            self.btn_start.setText("START")
        else:
            self.apply_settings();
            self.worker.mode = 'free' if self.rb_free.isChecked() else 'repeat'
            if self.rb_single.isChecked(): self.worker.mode = 'single'

            self.worker.duration = self.sb_dur.value();
            self.worker.max_cycles = self.sb_cyc.value()
            self.worker.peak_threshold = self.sb_threshold.value()

            self.worker.running = True;
            self.worker.start()
            self.btn_start.setText("STOP")

    def update_ui(self, h1, h2, rates, msg, prog):
        self.lbl_status.setText(msg);
        self.bar.setValue(prog)
        for i in range(4): self.lbl_rates[i].setText(f"{rates[i]:.1f}")
        
        self.curr_h1, self.curr_h2 = h1, h2
        if self.curr_x is not None and len(self.curr_x) == len(h1):
            self.c1.setData(self.curr_x, h1);
            self.c2.setData(self.curr_x, h2)
            self.update_sum(1);
            self.update_sum(2)

    def _write_files(self, save_dir, fname1, fname2, curr_x, h1, h2):
        if curr_x is None: return
        try:
            np.savetxt(
                os.path.join(save_dir, fname1),
                np.column_stack((curr_x, h1)),
                fmt='%d'
            )
            np.savetxt(
                os.path.join(save_dir, fname2),
                np.column_stack((curr_x, h2)),
                fmt='%d'
            )
        except Exception as e:
            print(f"Error saving data: {e}")

    def save_data(self, idx, h1, h2, dur):
        save_dir = self.le_path.text()
        if not save_dir:
            save_dir = DEFAULT_SAVE_DIR

        if not os.path.exists(save_dir):
            try:
                os.makedirs(save_dir)
            except Exception as e:
                print(f"Cannot create dir: {e}")
                return

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        cycle_str = f"Cycle_{idx:03d}"

        fname1 = f"{cycle_str}_Link1_{ts}.txt"
        fname2 = f"{cycle_str}_Link2_{ts}.txt"
        
        curr_x_copy = self.curr_x.copy() if self.curr_x is not None else None
        self.save_pool.submit(self._write_files, save_dir, fname1, fname2, curr_x_copy, h1, h2)

    def on_finished(self):
        self.btn_start.setText("START")
        self.lbl_status.setText("Acquisition Finished")

    def closeEvent(self, e):
        self.worker.running = False;
        self.worker.wait();
        e.accept()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv);
    win = MainWindow();
    win.show();
    sys.exit(app.exec_())