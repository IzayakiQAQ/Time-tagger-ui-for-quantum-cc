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

try:
    import Swabian.TimeTagger
except ImportError:
    class MockSwabian:
        TimeTagger = None
    Swabian = MockSwabian()

CH_PPS = 5
CH_START_DEF = 1
CH_STOP_DEF = 2

STYLE_SHEET = """
QMainWindow { background-color: #2b2b2b; color: #e0e0e0; }
QWidget { background-color: #2b2b2b; color: #e0e0e0; font-family: "Segoe UI", sans-serif; }
QGroupBox { border: 1px solid #444; border-radius: 4px; margin-top: 10px; padding-top: 10px; font-weight: bold; color: #00bcd4; }
QPushButton { background-color: #3c3c3c; border: 1px solid #555; border-radius: 3px; padding: 6px; color: #fff; font-weight: bold; }
QPushButton:hover { background-color: #4c4c4c; border-color: #00bcd4; }
QPushButton#btn_start { background-color: #2e7d32; font-size: 12pt; }
QPushButton#btn_stop { background-color: #c62828; font-size: 12pt; }
QPushButton#btn_auto { background-color: #f57f17; color: #000; font-weight: bold; }
QLabel { color: #bbb; }
QLineEdit, QSpinBox, QDoubleSpinBox { background-color: #1e1e1e; border: 1px solid #444; border-radius: 2px; padding: 4px; color: #00e5ff; font-family: "Consolas", monospace; font-size: 11pt; }
QComboBox { background-color: #1e1e1e; border: 1px solid #444; color: #00e5ff; padding: 4px; }
QProgressBar { height: 6px; border: none; background: #333; margin-top: 5px; }
QProgressBar::chunk { background: #00bcd4; }
QLabel#monitor_val { color: #fff; font-weight: bold; font-family: "Consolas", monospace; font-size: 10pt; }
QLabel#monitor_head { color: #888; font-size: 9pt; }
QLabel#signature { color: #666; font-style: italic; font-size: 9pt; margin-bottom: 5px; }
"""

class HardwareInterface:
    def __init__(self):
        self.ttA = None
        self.ttB = None

    def initialize(self, serial_a, serial_b):
        if Swabian.TimeTagger is None: return False, "TimeTagger Library Missing"
        try:
            self.ttA = Swabian.TimeTagger.createTimeTagger(serial_a) if serial_a else None
            self.ttB = Swabian.TimeTagger.createTimeTagger(serial_b) if serial_b else None
            return True, "Initialized TimeTaggers"
        except Exception as e:
            return False, str(e)

hw = HardwareInterface()

class ExperimentWorker(QtCore.QThread):
    status_update = QtCore.pyqtSignal(object, object, object, object, str, int)
    cycle_finished = QtCore.pyqtSignal(int, object, object, float, str)
    acq_finished = QtCore.pyqtSignal()
    peak_found = QtCore.pyqtSignal(int, float, float)

    def __init__(self):
        super().__init__()
        self.config_lock = threading.Lock()
        self.running = False
        self.mode = 'repeat'
        self.duration = 1.0
        self.cycles = 100
        self.current_cycle = 0
        self.configs = [{}, {}]
        self.bin_ps = 100
        self.window_ps = 100000

        self.pps_offset_A = None
        self.pps_offset_B = None
        self.is_synced = False
        self.search_request_idx = None
        self.search_thresh = 5
        self.save_dir = r"E:\lzy"

        self.buf_A = deque()
        self.buf_B = deque()

        self.hist_acc_1 = None
        self.hist_acc_2 = None
        self.axis_bins = None

        self.monitor_A = None
        self.monitor_B = None
        self.integ_time_s = 0.5

    def update_link_config(self, link_idx, start_dev, start_ch, stop_dev, stop_ch, manual_offset_ns):
        with self.config_lock:
            self.configs[link_idx] = {
                'start_dev': start_dev,
                'start_ch': start_ch,
                'stop_dev': stop_dev,
                'stop_ch': stop_ch,
                'offset_ps': int(manual_offset_ns * 1000)
            }

    def setup_global(self, bin_ps, win_ps):
        self.bin_ps = int(bin_ps)
        self.window_ps = int(win_ps)
        num_bins = int((2 * self.window_ps) / self.bin_ps)
        self.hist_acc_1 = np.zeros(num_bins, dtype=np.int32)
        self.hist_acc_2 = np.zeros(num_bins, dtype=np.int32)
        self.axis_bins = np.linspace(-self.window_ps, self.window_ps, num_bins + 1)

        integ_ps = int(self.integ_time_s * 1e12)
        if hw.ttA: self.monitor_A = Swabian.TimeTagger.Counter(hw.ttA, [1, 2, 3, 4], integ_ps, 1)
        if hw.ttB: self.monitor_B = Swabian.TimeTagger.Counter(hw.ttB, [1, 2, 3, 4], integ_ps, 1)

    def trigger_auto_search(self, link_idx):
        self.search_request_idx = link_idx

    def start_acquisition(self, mode, duration, cycles, save_dir, search_thresh):
        self.mode = mode
        self.duration = duration
        self.cycles = cycles
        self.current_cycle = 1
        with self.config_lock:
            self.save_dir = save_dir
            self.search_thresh = search_thresh
        self.running = True
        self.is_synced = False
        self.pps_offset_A = None
        self.pps_offset_B = None
        self.buf_A.clear()
        self.buf_B.clear()
        if self.hist_acc_1 is not None: self.hist_acc_1.fill(0)
        if self.hist_acc_2 is not None: self.hist_acc_2.fill(0)
        self.start()

    def stop_acquisition(self):
        self.running = False

    def run(self):
        if not hw.ttA and not hw.ttB: return

        ch_set_A = {CH_PPS}
        ch_set_B = {CH_PPS}

        need_pps_sync = False
        with self.config_lock:
            local_configs = [c.copy() for c in self.configs if c]
            
        for cfg in local_configs:
            if not cfg: continue
            if cfg['start_dev'] != cfg['stop_dev']:
                need_pps_sync = True

            if cfg['start_dev'] == 0: ch_set_A.add(cfg['start_ch'])
            else: ch_set_B.add(cfg['start_ch'])

            if cfg['stop_dev'] == 0: ch_set_A.add(cfg['stop_ch'])
            else: ch_set_B.add(cfg['stop_ch'])

        streamA = Swabian.TimeTagger.TimeTagStream(hw.ttA, 500000, list(ch_set_A)) if hw.ttA else None
        streamB = Swabian.TimeTagger.TimeTagStream(hw.ttB, 500000, list(ch_set_B)) if hw.ttB else None
        if streamA: streamA.start()
        if streamB: streamB.start()

        self.start_time = time.time()
        last_ui_update = time.time()

        while self.running:
            now = time.time()
            tsA_raw, chA_raw = np.array([]), np.array([])
            tsB_raw, chB_raw = np.array([]), np.array([])
            
            if streamA:
                dataA = streamA.getData()
                tsA_raw = dataA.getTimestamps()
                chA_raw = dataA.getChannels()

            if streamB:
                dataB = streamB.getData()
                tsB_raw = dataB.getTimestamps()
                chB_raw = dataB.getChannels()

            if not self.is_synced:
                if need_pps_sync and streamA and streamB:
                    if self.pps_offset_A is None and CH_PPS in chA_raw:
                        self.pps_offset_A = tsA_raw[np.where(chA_raw == CH_PPS)[0][0]]
                    if self.pps_offset_B is None and CH_PPS in chB_raw:
                        self.pps_offset_B = tsB_raw[np.where(chB_raw == CH_PPS)[0][0]]

                    if self.pps_offset_A is not None and self.pps_offset_B is not None:
                        self.is_synced = True
                        self.start_time = time.time()
                        self.buf_A.clear()
                        self.buf_B.clear()
                    else:
                        if now - last_ui_update > 0.25:
                            self._emit_status("Syncing PPS...", 0, None, None)
                            last_ui_update = now
                        time.sleep(0.002)
                        continue
                else:
                    self.pps_offset_A = 0
                    self.pps_offset_B = 0
                    self.is_synced = True
                    self.start_time = time.time()
                    self.buf_A.clear()
                    self.buf_B.clear()

            if len(tsA_raw) > 0: self.buf_A.append((tsA_raw - self.pps_offset_A, chA_raw))
            if len(tsB_raw) > 0: self.buf_B.append((tsB_raw - self.pps_offset_B, chB_raw))

            if self.search_request_idx is not None:
                total_ev = sum(len(x[0]) for x in self.buf_A) + sum(len(x[0]) for x in self.buf_B)
                if total_ev > 20000:
                    self._perform_auto_search(self.search_request_idx)
                    self.search_request_idx = None
                else:
                    time.sleep(0.002)
                    continue
            else:
                self._process_all_links()

            elapsed = now - self.start_time
            progress = min(100, int((elapsed / self.duration) * 100))

            if now - last_ui_update > 0.25:
                h1 = self.hist_acc_1.copy() if self.hist_acc_1 is not None else None
                h2 = self.hist_acc_2.copy() if self.hist_acc_2 is not None else None
                self._emit_status(f"Cycle {self.current_cycle}", progress, h1, h2)
                last_ui_update = now

            if self.mode != 'free' and elapsed >= self.duration:
                ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                save_d = self.save_dir
                self.cycle_finished.emit(self.current_cycle,
                                         self.hist_acc_1.copy(),
                                         self.hist_acc_2.copy(),
                                         self.duration, ts_str)

                if self.mode == 'single' or (self.mode == 'repeat' and self.current_cycle >= self.cycles):
                    self.running = False
                    self.acq_finished.emit()
                else:
                    self.current_cycle += 1
                    self.start_time = time.time()
                    self.hist_acc_1.fill(0)
                    self.hist_acc_2.fill(0)

            time.sleep(0.001)

        if streamA: streamA.stop()
        if streamB: streamB.stop()

    def _merge(self, buf):
        if not buf: return np.array([]), np.array([])
        return np.concatenate([x[0] for x in buf]), np.concatenate([x[1] for x in buf])

    def _process_all_links(self):
        if not self.buf_A and not self.buf_B: return

        tsA, chA = self._merge(self.buf_A)
        tsB, chB = self._merge(self.buf_B)

        if len(tsA) == 0 and len(tsB) == 0: return

        mins, maxs = [], []
        if len(tsA) > 0: mins.append(tsA[0]); maxs.append(tsA[-1])
        if len(tsB) > 0: mins.append(tsB[0]); maxs.append(tsB[-1])

        if not mins: return
        t_min, t_max = max(mins), min(maxs)

        if t_max < t_min:
            if len(tsA) > 0 and len(tsB) > 0:
                if tsA[-1] < tsB[-1]: self.buf_A.clear()
                else: self.buf_B.clear()
            return

        self._calc_link(0, tsA, chA, tsB, chB, t_min, t_max, self.hist_acc_1)
        self._calc_link(1, tsA, chA, tsB, chB, t_min, t_max, self.hist_acc_2)

        self.buf_A.clear()
        self.buf_B.clear()

    def _calc_link(self, idx, tsA, chA, tsB, chB, t_min, t_max, accumulator):
        with self.config_lock:
            cfg = self.configs[idx].copy() if self.configs[idx] else {}
        if not cfg: return

        if cfg['start_dev'] == 0:
            mask = (tsA >= t_min) & (tsA <= t_max) & (chA == cfg['start_ch'])
            t_start = tsA[mask]
        else:
            mask = (tsB >= t_min) & (tsB <= t_max) & (chB == cfg['start_ch'])
            t_start = tsB[mask]

        if cfg['stop_dev'] == 0:
            mask = (tsA >= t_min) & (tsA <= t_max) & (chA == cfg['stop_ch'])
            t_stop = tsA[mask]
        else:
            mask = (tsB >= t_min) & (tsB <= t_max) & (chB == cfg['stop_ch'])
            t_stop = tsB[mask]

        if len(t_start) == 0 or len(t_stop) == 0: return
        t_stop_shifted = t_stop + cfg['offset_ps']
        idx_arr = np.searchsorted(t_stop_shifted, t_start)
        diffs = []

        valid = idx_arr < len(t_stop_shifted)
        if np.any(valid):
            d = t_stop_shifted[idx_arr[valid]] - t_start[valid]
            diffs.append(d[d < self.window_ps])

        valid_prev = idx_arr > 0
        if np.any(valid_prev):
            d = t_stop_shifted[idx_arr[valid_prev] - 1] - t_start[valid_prev]
            diffs.append(d[d > -self.window_ps])

        if diffs:
            all_diffs = np.concatenate(diffs)
            if len(all_diffs) > 0:
                counts, _ = np.histogram(all_diffs, bins=self.axis_bins)
                accumulator += counts.astype(np.int32)

    def _perform_auto_search(self, link_idx):
        tsA, chA = self._merge(self.buf_A)
        tsB, chB = self._merge(self.buf_B)

        with self.config_lock:
            cfg = self.configs[link_idx].copy() if self.configs[link_idx] else {}
            search_thresh = self.search_thresh

        if cfg['start_dev'] == 0: t_start = tsA[chA == cfg['start_ch']]
        else: t_start = tsB[chB == cfg['start_ch']]

        if cfg['stop_dev'] == 0: t_stop = tsA[chA == cfg['stop_ch']]
        else: t_stop = tsB[chB == cfg['stop_ch']]

        if len(t_start) == 0 or len(t_stop) == 0:
            self.buf_A.clear(); self.buf_B.clear()
            return

        wide_win = 500000000
        idx = np.searchsorted(t_stop, t_start)
        candidates = []

        valid = idx < len(t_stop)
        if np.any(valid):
            d = t_stop[idx[valid]] - t_start[valid]
            candidates.append(d[d < wide_win])

        valid_prev = idx > 0
        if np.any(valid_prev):
            d = t_stop[idx[valid_prev] - 1] - t_start[valid_prev]
            candidates.append(d[d > -wide_win])

        if not candidates:
            self.buf_A.clear(); self.buf_B.clear()
            return

        all_d = np.concatenate(candidates)
        if len(all_d) < 10: return

        bins = np.arange(-wide_win, wide_win, 10000)
        counts, edges = np.histogram(all_d, bins=bins)
        max_idx = np.argmax(counts)
        peak_cnt = counts[max_idx]
        mean_noise = np.mean(counts)
        peak_pos = (edges[max_idx] + edges[max_idx + 1]) / 2

        if peak_cnt > search_thresh and peak_cnt > mean_noise * 3:
            self.peak_found.emit(link_idx, -peak_pos, peak_cnt)

        self.buf_A.clear(); self.buf_B.clear()

    def _emit_status(self, msg, progress, h1, h2):
        monA, monB = [0.0]*4, [0.0]*4
        if self.monitor_A:
            d = self.monitor_A.getData()
            monA = [(d[i][0] / self.integ_time_s) / 1000.0 for i in range(4)]
        if self.monitor_B:
            d = self.monitor_B.getData()
            monB = [(d[i][0] / self.integ_time_s) / 1000.0 for i in range(4)]

        self.status_update.emit(h1, h2, monA, monB, msg, progress)

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QTWTT Lab Master (Dual Independent Links)")
        self.resize(1300, 950)
        self.setStyleSheet(STYLE_SHEET)

        self.worker = ExperimentWorker()
        self.worker.status_update.connect(self.update_ui)
        self.worker.cycle_finished.connect(self.save_data)
        self.worker.acq_finished.connect(self.on_finished)
        self.worker.peak_found.connect(self.on_peak_found)

        self.save_pool = ThreadPoolExecutor(max_workers=2)
        self.lbls_mon_A = []
        self.lbls_mon_B = []

        self._init_ui()

    def _init_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)

        sidebar = QtWidgets.QWidget()
        sidebar.setFixedWidth(420)
        side_layout = QtWidgets.QVBoxLayout(sidebar)
        side_layout.setSpacing(10)

        # Device Setup
        gb_dev = QtWidgets.QGroupBox("DEVICE SETUP")
        v_dev = QtWidgets.QVBoxLayout()
        h_devA = QtWidgets.QHBoxLayout()
        h_devA.addWidget(QtWidgets.QLabel("TDC A Serial:"))
        self.le_serialA = QtWidgets.QLineEdit("225000138V")
        h_devA.addWidget(self.le_serialA)
        v_dev.addLayout(h_devA)
        
        h_devB = QtWidgets.QHBoxLayout()
        h_devB.addWidget(QtWidgets.QLabel("TDC B Serial:"))
        self.le_serialB = QtWidgets.QLineEdit("22440012ZN")
        h_devB.addWidget(self.le_serialB)
        v_dev.addLayout(h_devB)
        
        self.btn_connect = QtWidgets.QPushButton("Connect Devices")
        self.btn_connect.clicked.connect(self.connect_devices)
        v_dev.addWidget(self.btn_connect)
        gb_dev.setLayout(v_dev)
        side_layout.addWidget(gb_dev)

        self.grp_link1, self.ui_link1 = self._create_link_group("LINK 1", 1)
        side_layout.addWidget(self.grp_link1)

        self.grp_link2, self.ui_link2 = self._create_link_group("LINK 2", 2)
        side_layout.addWidget(self.grp_link2)

        btn_apply = QtWidgets.QPushButton("Apply All Configs")
        btn_apply.clicked.connect(self.apply_config)
        side_layout.addWidget(btn_apply)

        gb_acq = QtWidgets.QGroupBox("ACQUISITION")
        v_acq = QtWidgets.QVBoxLayout()
        
        h_save = QtWidgets.QHBoxLayout()
        self.le_save_dir = QtWidgets.QLineEdit(r"E:\lzy\2025.12.16 2TDC test12h uitimetamp")
        btn_browse = QtWidgets.QPushButton("Browse")
        btn_browse.clicked.connect(self.browse_save_dir)
        h_save.addWidget(self.le_save_dir)
        h_save.addWidget(btn_browse)
        v_acq.addLayout(h_save)

        self.rb_free = QtWidgets.QRadioButton("Free Run")
        self.rb_single = QtWidgets.QRadioButton("Single Shot")
        self.rb_repeat = QtWidgets.QRadioButton("Repeated")
        self.rb_repeat.setChecked(True)
        h_mode = QtWidgets.QHBoxLayout()
        h_mode.addWidget(self.rb_free); h_mode.addWidget(self.rb_single); h_mode.addWidget(self.rb_repeat)
        v_acq.addLayout(h_mode)

        self.sb_dur = QtWidgets.QDoubleSpinBox(); self.sb_dur.setValue(1.0); self.sb_dur.setSuffix(" s")
        self.sb_cyc = QtWidgets.QSpinBox(); self.sb_cyc.setValue(100); self.sb_cyc.setRange(1, 9999)
        self.sb_search_thresh = QtWidgets.QSpinBox(); self.sb_search_thresh.setValue(5); self.sb_search_thresh.setRange(1, 10000)
        
        v_acq.addWidget(self._row(QtWidgets.QLabel("Duration:"), self.sb_dur))
        v_acq.addWidget(self._row(QtWidgets.QLabel("Cycles:"), self.sb_cyc))
        v_acq.addWidget(self._row(QtWidgets.QLabel("Search Thresh:"), self.sb_search_thresh))

        self.btn_start = QtWidgets.QPushButton("START")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.setMinimumHeight(40)
        self.btn_start.clicked.connect(self.toggle_start)
        self.btn_start.setEnabled(False)
        v_acq.addWidget(self.btn_start)

        self.lbl_status = QtWidgets.QLabel("Ready (Please Connect Devices)")
        self.lbl_status.setAlignment(QtCore.Qt.AlignCenter)
        v_acq.addWidget(self.lbl_status)
        self.bar = QtWidgets.QProgressBar(); self.bar.setValue(0); self.bar.setTextVisible(False)
        v_acq.addWidget(self.bar)
        gb_acq.setLayout(v_acq)
        side_layout.addWidget(gb_acq)

        gb_mon = QtWidgets.QGroupBox("MONITOR (kHz)")
        g_mon = QtWidgets.QGridLayout()
        g_mon.setHorizontalSpacing(10); g_mon.setVerticalSpacing(5)
        for i in range(4):
            l = QtWidgets.QLabel(f"CH {i + 1}")
            l.setObjectName("monitor_head")
            l.setAlignment(QtCore.Qt.AlignCenter)
            g_mon.addWidget(l, 0, i + 1)
        g_mon.addWidget(QtWidgets.QLabel("TDC A"), 1, 0)
        g_mon.addWidget(QtWidgets.QLabel("TDC B"), 2, 0)
        for i in range(4):
            lA = QtWidgets.QLabel("0.0")
            lA.setObjectName("monitor_val")
            lA.setAlignment(QtCore.Qt.AlignRight)
            self.lbls_mon_A.append(lA)
            g_mon.addWidget(lA, 1, i + 1)
            lB = QtWidgets.QLabel("0.0")
            lB.setObjectName("monitor_val")
            lB.setAlignment(QtCore.Qt.AlignRight)
            self.lbls_mon_B.append(lB)
            g_mon.addWidget(lB, 2, i + 1)
        gb_mon.setLayout(g_mon)
        side_layout.addWidget(gb_mon)

        side_layout.addStretch()
        lbl_signature = QtWidgets.QLabel("By Zhi-Yang Liu")
        lbl_signature.setObjectName("signature")
        lbl_signature.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom)
        side_layout.addWidget(lbl_signature)

        layout.addWidget(sidebar)

        right_w = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_w)

        h_set = QtWidgets.QHBoxLayout()
        self.sb_bin = QtWidgets.QSpinBox(); self.sb_bin.setValue(100); self.sb_bin.setSuffix(" ps"); self.sb_bin.setRange(1, 10000)
        self.sb_win = QtWidgets.QSpinBox(); self.sb_win.setValue(100000); self.sb_win.setSuffix(" ps"); self.sb_win.setRange(100, 100000000)

        btn_axis = QtWidgets.QPushButton("Set Axis")
        btn_axis.clicked.connect(self.apply_config)
        h_set.addWidget(QtWidgets.QLabel("Bin:")); h_set.addWidget(self.sb_bin)
        h_set.addWidget(QtWidgets.QLabel("Window:")); h_set.addWidget(self.sb_win)
        h_set.addWidget(btn_axis)
        h_set.addStretch()
        right_layout.addLayout(h_set)

        self.plot1 = pg.PlotWidget(title="Link 1 Coincidence")
        self.plot1.setBackground('#1e1e1e')
        self.plot1.setLabel('bottom', 'Time Difference (ps)')
        self.curve1 = self.plot1.plot(pen=pg.mkPen('#00e5ff', width=2), brush=(0, 229, 255, 50), fillLevel=0)
        self.roi1 = pg.LinearRegionItem([0, 0], brush=pg.mkBrush(255, 255, 0, 30))
        self.roi1.sigRegionChanged.connect(lambda: self.update_roi(1))
        self.plot1.addItem(self.roi1)
        self.lbl_roi1 = pg.TextItem("Sum: 0", anchor=(1, 0), color=(255, 255, 0))
        self.plot1.addItem(self.lbl_roi1)
        right_layout.addWidget(self.plot1)

        self.plot2 = pg.PlotWidget(title="Link 2 Coincidence")
        self.plot2.setBackground('#1e1e1e')
        self.plot2.setLabel('bottom', 'Time Difference (ps)')
        self.curve2 = self.plot2.plot(pen=pg.mkPen('#ff4081', width=2), brush=(255, 64, 129, 50), fillLevel=0)
        self.roi2 = pg.LinearRegionItem([0, 0], brush=pg.mkBrush(255, 255, 0, 30))
        self.roi2.sigRegionChanged.connect(lambda: self.update_roi(2))
        self.plot2.addItem(self.roi2)
        self.lbl_roi2 = pg.TextItem("Sum: 0", anchor=(1, 0), color=(255, 255, 0))
        self.plot2.addItem(self.lbl_roi2)
        right_layout.addWidget(self.plot2)

        layout.addWidget(right_w)
        
        self.curr_x = None

    def connect_devices(self):
        serA = self.le_serialA.text().strip()
        serB = self.le_serialB.text().strip()
        ok, msg = hw.initialize(serA, serB)
        if not ok:
            QtWidgets.QMessageBox.critical(self, "Error", msg)
        else:
            QtWidgets.QMessageBox.information(self, "Connected", "Devices initialized successfully.")
            self.lbl_status.setText("Ready")
            self.btn_start.setEnabled(True)
            self.apply_config()

    def browse_save_dir(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Save Directory", self.le_save_dir.text())
        if d: self.le_save_dir.setText(d)
        
    def _create_link_group(self, title, idx):
        gb = QtWidgets.QGroupBox(title)
        fl = QtWidgets.QFormLayout()
        fl.setSpacing(5)

        cb_start_dev = QtWidgets.QComboBox()
        cb_start_dev.addItems(["TDC A", "TDC B"])
        sb_start_ch = QtWidgets.QSpinBox()
        sb_start_ch.setRange(1, 8)
        sb_start_ch.setValue(1 if idx == 1 else 3)

        cb_stop_dev = QtWidgets.QComboBox()
        cb_stop_dev.addItems(["TDC A", "TDC B"])
        cb_stop_dev.setCurrentIndex(1)
        sb_stop_ch = QtWidgets.QSpinBox()
        sb_stop_ch.setRange(1, 8)
        sb_stop_ch.setValue(2 if idx == 1 else 4)

        sb_delay = QtWidgets.QDoubleSpinBox()
        sb_delay.setRange(-1e12, 1e12)
        sb_delay.setSuffix(" ns")
        sb_delay.valueChanged.connect(lambda: self.manual_delay_change(idx))

        btn_search = QtWidgets.QPushButton("Auto Search")
        btn_search.clicked.connect(lambda: self.do_auto_search(idx))

        fl.addRow("Start:", self._row(cb_start_dev, sb_start_ch))
        fl.addRow("Stop:", self._row(cb_stop_dev, sb_stop_ch))
        fl.addRow("Delay:", sb_delay)
        fl.addRow(btn_search)

        gb.setLayout(fl)
        ui_objs = {
            'start_dev': cb_start_dev, 'start_ch': sb_start_ch,
            'stop_dev': cb_stop_dev, 'stop_ch': sb_stop_ch,
            'delay': sb_delay, 'btn_search': btn_search
        }
        return gb, ui_objs

    def _row(self, w1, w2):
        w = QtWidgets.QWidget()
        l = QtWidgets.QHBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(w1, 1); l.addWidget(w2, 1)
        return w

    def apply_config(self):
        self.worker.setup_global(self.sb_bin.value(), self.sb_win.value())
        self.curr_x = np.linspace(-self.sb_win.value(), self.sb_win.value(), int(2*self.sb_win.value()/self.sb_bin.value()) + 1)

        self.worker.update_link_config(0,
                                       self.ui_link1['start_dev'].currentIndex(), self.ui_link1['start_ch'].value(),
                                       self.ui_link1['stop_dev'].currentIndex(), self.ui_link1['stop_ch'].value(),
                                       self.ui_link1['delay'].value())
        self.worker.update_link_config(1,
                                       self.ui_link2['start_dev'].currentIndex(), self.ui_link2['start_ch'].value(),
                                       self.ui_link2['stop_dev'].currentIndex(), self.ui_link2['stop_ch'].value(),
                                       self.ui_link2['delay'].value())

        win = self.sb_win.value()
        self.plot1.setXRange(-win, win)
        self.plot2.setXRange(-win, win)

        for roi in [self.roi1, self.roi2]:
            cr = roi.getRegion()
            if abs(cr[1] - cr[0]) < 1e-3: roi.setRegion([-win / 4, win / 4])

    def manual_delay_change(self, idx_1based):
        ui = self.ui_link1 if idx_1based == 1 else self.ui_link2
        self.worker.update_link_config(idx_1based - 1,
                                       ui['start_dev'].currentIndex(), ui['start_ch'].value(),
                                       ui['stop_dev'].currentIndex(), ui['stop_ch'].value(),
                                       ui['delay'].value())

    def toggle_start(self):
        if self.worker.running:
            self.worker.stop_acquisition()
            self.btn_start.setText("START")
            self.btn_start.setObjectName("btn_start")
            self.btn_start.setStyle(self.btn_start.style())
        else:
            self.apply_config()
            mode = 'free' if self.rb_free.isChecked() else ('single' if self.rb_single.isChecked() else 'repeat')
            self.worker.start_acquisition(mode, self.sb_dur.value(), self.sb_cyc.value(), self.le_save_dir.text(), self.sb_search_thresh.value())
            self.btn_start.setText("STOP")
            self.btn_start.setObjectName("btn_stop")
            self.btn_start.setStyle(self.btn_start.style())

    def do_auto_search(self, idx_1based):
        if not self.worker.running:
            QtWidgets.QMessageBox.warning(self, "Warning", "Please START acquisition first!")
            return
        ui = self.ui_link1 if idx_1based == 1 else self.ui_link2
        ui['btn_search'].setEnabled(False)
        ui['btn_search'].setText("Searching...")
        self.worker.trigger_auto_search(idx_1based - 1)

    def on_peak_found(self, link_idx, offset_ps, counts):
        ui = self.ui_link1 if link_idx == 0 else self.ui_link2
        ui['btn_search'].setEnabled(True)
        ui['btn_search'].setText("Auto Search")

        curr_ns = ui['delay'].value()
        add_ns = offset_ps / 1000.0
        new_val = curr_ns + add_ns

        ui['delay'].blockSignals(True)
        ui['delay'].setValue(new_val)
        ui['delay'].blockSignals(False)
        self.manual_delay_change(link_idx + 1)
        QtWidgets.QMessageBox.information(self, "Peak Found", f"Link {link_idx + 1} Peak Found!\nCounts: {counts}\nAdjusted Offset: {add_ns:.3f} ns")

    def update_ui(self, h1, h2, monA, monB, msg, progress):
        self.lbl_status.setText(msg)
        self.bar.setValue(progress)

        for i in range(4):
            self.lbls_mon_A[i].setText(f"{monA[i]:.1f}")
            self.lbls_mon_B[i].setText(f"{monB[i]:.1f}")

        if h1 is not None and len(h1) > 0 and hasattr(self, 'curr_x') and len(self.curr_x) == len(h1):
            self.curve1.setData(self.curr_x, h1)
            self.curr_h1_x = self.curr_x; self.curr_h1_y = h1
            self.update_roi(1)

        if h2 is not None and len(h2) > 0 and hasattr(self, 'curr_x') and len(self.curr_x) == len(h2):
            self.curve2.setData(self.curr_x, h2)
            self.curr_h2_x = self.curr_x; self.curr_h2_y = h2
            self.update_roi(2)

    def update_roi(self, idx):
        if idx == 1:
            if not hasattr(self, 'curr_h1_y'): return
            roi, lbl, x_data, y_data = self.roi1, self.lbl_roi1, self.curr_h1_x, self.curr_h1_y
        else:
            if not hasattr(self, 'curr_h2_y'): return
            roi, lbl, x_data, y_data = self.roi2, self.lbl_roi2, self.curr_h2_x, self.curr_h2_y

        min_x, max_x = roi.getRegion()
        mask = (x_data >= min_x) & (x_data <= max_x)
        if len(y_data[mask]) > 0:
            total = np.sum(y_data[mask])
            lbl.setText(f"Sum: {int(total):,}")
            lbl.setPos(max_x, np.max(y_data) * 0.9)
        else:
            lbl.setText("Sum: 0")

    def on_finished(self):
        self.btn_start.setText("START")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.setStyle(self.btn_start.style())
        self.lbl_status.setText("Finished")
        self.bar.setValue(100)

    def save_data(self, idx, h1, h2, dur, ts):
        save_d = self.le_save_dir.text().strip()
        if not os.path.exists(save_d):
            try: os.makedirs(save_d)
            except: pass
        
        self.save_pool.submit(self._write_file, f"{save_d}/Cycle_{idx:03d}_Link1_{ts}.txt", h1, self.worker.bin_ps, self.worker.window_ps, dur)
        self.save_pool.submit(self._write_file, f"{save_d}/Cycle_{idx:03d}_Link2_{ts}.txt", h2, self.worker.bin_ps, self.worker.window_ps, dur)

    @staticmethod
    def _write_file(path, hist, bin_ps, win_ps, dur):
        try:
            x = np.linspace(-win_ps, win_ps, len(hist))
            hdr = f"Duration: {dur}\nBin: {bin_ps}"
            np.savetxt(path, np.column_stack((x, hist)), fmt="%.1f\t%d", header=hdr)
        except Exception as e:
            print(f"Failed to write data {path}: {e}")

    def closeEvent(self, e):
        self.worker.stop_acquisition()
        self.worker.wait()
        e.accept()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
