# Copyright 2026 ETRI. 
# License-identifier:GNU General Public License v3.0 or later
# yssong00@etri.re.kr

# This program is free software: you can redistribute it and/or modify 
# it under the terms of the GNU General Public License as published 
# by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; 
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. 
# See the GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along with this program. 
# If not, see <https://www.gnu.org/licenses/>.

""" Integrated Message for Sender Widnow(Send video-data & BSM) based on Real PDR Data """

import cv2
import psutil
import socket
import sys
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
import packet_header_struct 
import time
import struct
import csv
import os
import traceback
import ntplib
import random
from pygrabber.dshow_graph import FilterGraph
from fastcrc import crc16
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

# ==========================================
# [0] Global Trace & Metrics Initialization
# ==========================================
global trace_array, trace_idx, trace_length, channel_metrics_df, trace_cycle_count
trace_array = []
trace_idx = 0
trace_length = 0
trace_cycle_count = 0 
MAX_CYCLES = 12 # 트랙 반복 횟수 제어 
channel_metrics_df = None

try:
    with open("trace.bin", "rb") as f:
        packed_data = np.frombuffer(f.read(), dtype=np.uint8)
        trace_array = np.unpackbits(packed_data)
        trace_length = len(trace_array)
    print(f"[System] BIN Trace loaded: {trace_length} bits.")
    
    channel_metrics_df = pd.read_csv("channel_metrics.csv")
    print(f"[System] Channel Metrics loaded: {len(channel_metrics_df)} windows.")
except Exception as e:
    print(f"[System Warning] Pre-processed files load failed ({e}). Proceeding without channel emulation.")
    trace_array = []
    trace_length = 0
    channel_metrics_df = None

# ==========================================
# [1] Experiment Configuration
# ==========================================
class Config:
    """  Config for BSM Message (56byte) """
    CURRENT_MODE = "RAW" 
    
    # 56바이트 설정 (K=8, Symbol=7)
    SYMBOL_SIZE = 7  
    K = 8            
    
    MODE_SETTINGS = {
        "RAW":         {"type": "BULK",  "N": 1,  "Repeat": 1}, 
        "REPETITION3": {"type": "BULK",  "N": 1,  "Repeat": 3}, 
        "REPETITION5": {"type": "BULK",  "N": 1,  "Repeat": 5}, 
        "ADAPTIVE_RS": {"type": "SPLIT", "N": 0,  "Repeat": 1}, 
    }
    
    BSM_DEADLINE_MS = 100       
    SENDER_FRAME_MSEC = 100      
    AVG_PACKETS_PER_FRAME = 180 

# ==========================================
# [2] RS Logic (Math)
# ==========================================
POLY = 0x11D 
GF256_EXP = [0] * 512
GF256_LOG = [0] * 256

def init_tables():
    """ init """
    x = 1
    for i in range(255):
        GF256_EXP[i] = x
        GF256_LOG[x] = i
        x <<= 1
        if x & 0x100: x ^= POLY
    for i in range(255, 512):
        GF256_EXP[i] = GF256_EXP[i-255]

init_tables()

def gf_add(a, b): 
	""" Return the bitwise XOR sum of a and b."""
	return a ^ b
def gf_mul(a, b):
    """Multiply two elements """
    if a == 0 or b == 0: return 0
    return GF256_EXP[GF256_LOG[a] + GF256_LOG[b]]
def gf_inv(a):
    """Compute the multiplicative inverse """
    if a == 0: raise ZeroDivisionError
    return GF256_EXP[255 - GF256_LOG[a]]

def vec_lincomb(acc, coef, sym):
    """Compute the linear combination of vectors """
    if coef == 0: return
    if coef == 1:
        for i, v in enumerate(sym): acc[i] ^= v
    else:
        for i, v in enumerate(sym):
            acc[i] ^= gf_mul(coef, v)

class ReedSolomonSimple:
    # 생성자 파라미터 기본값 변경 (7B, K=8)
    """ Update Parameters """
    def __init__(self, symbol_size=7, K=8):
        """ init """
        self.S = symbol_size
        self.K = K

    def _split(self, msg):
        """ split packets """
        target_len = self.K * self.S 
        if len(msg) < target_len:
            msg = msg + b'\x00' * (target_len - len(msg))
        return [msg[i*self.S:(i+1)*self.S] for i in range(self.K)]

    def _get_recipe(self, esi):
        """Generate coefficients """
        if esi < self.K: return None 
        x_val = esi 
        idxs = list(range(self.K))
        coefs = []
        for y_val in range(self.K):
            coefs.append(gf_inv(x_val ^ y_val))
        return list(zip(idxs, coefs))

    def encode(self, msg, esi):
        """ encode """
        src = self._split(msg)
        if esi < self.K: return (esi, src[esi])
        recipe = self._get_recipe(esi)
        acc = bytearray(self.S)
        for idx, coef in recipe:
            vec_lincomb(acc, coef, src[idx])
        return (esi, bytes(acc))

# ==========================================
# [3] Emergency Channel Manager
# ==========================================
class EmergencyChannelManager:
    
    """ Send BSM - Channel Manager """
    def __init__(self, interval=0.1):
	    """ init """
        self.interval = interval 
        self.last_check_time = 0
        self.chunks_to_send = [] 
        
        self.K = Config.K
        self.S = Config.SYMBOL_SIZE
        self.rs = ReedSolomonSimple(symbol_size=self.S, K=self.K) 
        
        self.current_sim_pdr = 100.0
        self.current_N = 32
        self.current_interleaving_iv = 0 
        self.current_strategy = {} 
        self.msg_seq = -1 
        self.total_generated_msgs = 0 
        
        # 모드 전환 시 환경 완전 초기화
        global trace_idx, trace_cycle_count
        trace_idx = 0
        trace_cycle_count = 0
        print(f"\n[Mgr] 🔄 시스템 초기화 완료 ({Config.CURRENT_MODE} 모드 시작)")

    def _adaptive_logic_from_metrics(self):
        
        """ Adjust size (N) based on PDR """
        global trace_idx, channel_metrics_df
        
        if channel_metrics_df is None or len(channel_metrics_df) == 0:
            self.current_N = 32
            self.current_interleaving_iv = 0 
            return

        window_idx = min(trace_idx // 100, len(channel_metrics_df) - 1)
        row = channel_metrics_df.iloc[window_idx]
        
        pdr = float(row['PDR'])
        max_burst = int(row['Max_Burst'])
        
        if pdr < 0.45 or max_burst >= 20:
            mapped_N = 64; mapped_G = 2
        elif pdr < 0.55 or max_burst >= 15:
            mapped_N = 59; mapped_G = 2
        elif pdr < 0.65 or max_burst >= 10:
            mapped_N = 64; mapped_G = 1
        elif pdr < 0.75 or max_burst >= 5:
            mapped_N = 62; mapped_G = 1
        elif pdr < 0.85 or max_burst >= 3:
            mapped_N = 58; mapped_G = 1
        else:
            mapped_N = 58; mapped_G = 0
        
        self.current_N = mapped_N
        self.current_interleaving_iv = mapped_G
        self.current_sim_pdr = pdr * 100.0

    def check_update(self):
	    """ 실도로 HIL and Processing """
        global trace_cycle_count, MAX_CYCLES
        
        # 12번 순환 완료 시 모드 종료
        if trace_cycle_count >= MAX_CYCLES:
            print(f"[Mgr] 🏁 {Config.CURRENT_MODE} 모드 {MAX_CYCLES}주기 완료. 다음 모드로 전환합니다.")
            return True 
            
        if self.chunks_to_send: return False
        if time.time() - self.last_check_time < self.interval: return False

        self.last_check_time = time.time()
        try:
            self.msg_seq = (self.msg_seq + 1) % 4
            self.total_generated_msgs += 1
            
            global TIME_OFFSET
            now = datetime.now() + timedelta(milliseconds=TIME_OFFSET)
            time_str = f"{now.minute:02d}{now.second:02d}{now.microsecond // 1000:03d}"
            
            text_bytes = f"_SEQ:{self.total_generated_msgs:06d}_".encode('utf-8') 
            full_payload = time_str.encode('utf-8') + text_bytes
            target_len = self.K * self.S # 56 바이트
            
            if len(full_payload) < target_len:
                full_payload = full_payload.ljust(target_len, b'*')
            
            setting = Config.MODE_SETTINGS.get(Config.CURRENT_MODE, Config.MODE_SETTINGS["RAW"])
            
            if setting["type"] == "BULK":
                self.chunks_to_send = [(0, full_payload)] 
                self.current_strategy = {"type": "BULK", "repeat": setting["Repeat"]}
                self.current_interleaving_iv = 0  
                
            else: 
                if Config.CURRENT_MODE == "ADAPTIVE_RS":
                    self._adaptive_logic_from_metrics()
                    n_val = self.current_N
                else:
                    n_val = setting["N"]
                    self.current_interleaving_iv = 0 
                
                encoded_batch = []
                for i in range(n_val):
                    encoded_batch.append(self.rs.encode(full_payload, i))
                self.chunks_to_send = encoded_batch
                self.current_strategy = {"type": "SPLIT", "repeat": setting["Repeat"]}

        except BaseException as e:
            print(f"[Mgr Error] {e}")
            print(traceback.format_exc())
        
        return False 

    def get_package(self):
        """ Make Integrated Message """
        payload_data = None
        header_bytes = b'\x00' * 8
        strategy = {"type": "NONE", "repeat": 1}
        
        if self.chunks_to_send:
            idx, data = self.chunks_to_send.pop(0)
            strategy = self.current_strategy
            
            if strategy["type"] == "BULK":
                payload_data = data
                header_bytes = b'\x00' * 8
            else:
                payload_data = None
                header_byte = ((self.msg_seq & 0x03) << 6) | (idx & 0x3F)
                
                if len(data) < 7: data = data + b'\x00' * (7 - len(data))
                header_bytes = header_byte.to_bytes(1, 'big') + data
                
        return payload_data, header_bytes, strategy, self.current_interleaving_iv

    def has_pending_chunks(self):
        """ Pending Data Check """
        return len(self.chunks_to_send) > 0

# ==========================================
# [4] Send Logic & Channel Emulation
# ==========================================
WIN_SIZE_H, WIN_SIZE_W = 800, 600
DEVICE_ADDR, DEVICE_PORT = '192.168.1.11', 12345
SOCKET_SEND_DELAY = 0.001
SLEEP_PARAMS = 50
SEND_FRAME_WIDTH, SEND_FRAME_HEIGHT = 300, 300
MAX_FRAME_SIZE = 1400 
NET_IF = None
pkt_seq_num = 0
extensible_seq = 0
camera_list = {}
TIME_OFFSET = 0 

def resource_path(p): return os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))), p)
def rescale_frame(f, w, h): return cv2.resize(f, (w, h), interpolation=cv2.INTER_AREA)
def find_camera_list(): 
    global camera_list
    camera_list = {}
    try:
        devices = FilterGraph().get_input_devices()
        for i, n in enumerate(devices): camera_list[i] = n
    except BaseException: pass

def send_5g(send_sock, video_data, inttime, header_bytes=b'\x00'*8, extra_payload=None, repeat_count=1):
    global pkt_seq_num
    global extensible_seq
    global trace_idx, trace_array, trace_length, trace_cycle_count
    
    final_payload = video_data
    if extra_payload:
        final_payload = video_data + b'BSM:' + extra_payload 
        
    pkt_seq_num_temp = pkt_seq_num.to_bytes(4, byteorder='big')
    extensible_seq_temp = extensible_seq.to_bytes(2, byteorder='big')
    extensible_seq = (extensible_seq+1) % 10000
    
    send_data = b'\x03\x01' + pkt_seq_num_temp + final_payload
    pkt_seq_num = (pkt_seq_num + 1) % 1000000

    _unDeviceId  = int.from_bytes(header_bytes[0:4], 'big')
    _eServiceId  = int.from_bytes(header_bytes[4:6], 'big')
    _eActionType = int.from_bytes(header_bytes[6:8], 'big')

    SSOV_p = packet_header_struct.SSOV(
        eDeviceType=0x0001, eTeleCommType=0x0002, 
        unDeviceId=_unDeviceId,   
        ulTimeStamp=pkt_seq_num, 
        eServiceId=_eServiceId,   
        eActionType=_eActionType, 
        eRegionId=0x0004,
        ePayloadType=0x000b, eCommId=0x0001, usDbVer=0x0001, usHwVer=0x0111,
        usSwVer=0x0001, ulPayloadLength=len(send_data), Reserved=inttime            
    )
    SSOV_data = bytes(SSOV_p) + send_data
    TLVC_SSOV_p = packet_header_struct.TLVC_Extensible(Type=0xe36e, Length=40+len(send_data)+2, data=SSOV_data)
    CRC_SSOV = crc16.xmodem(bytes(TLVC_SSOV_p))
    SSOV_pack = bytes(TLVC_SSOV_p) + bytes.fromhex(hex(CRC_SSOV)[2:].zfill(4))
    
    TLVC_overall_p = packet_header_struct.TLVC_overall(
        Type=0xe36c, Length=0x000a, magic_num="EMOP", version=0x01, 
        follow_package_n=0x01, len_follow_packet=len(SSOV_pack)
    )
    CRC_Overall = crc16.xmodem(bytes(TLVC_overall_p))
    serialized = bytes(TLVC_overall_p)+ bytes.fromhex(hex(CRC_Overall)[2:].zfill(4)) + SSOV_pack
    WS_Header = b"\x35\x47\x56\x58" + (len(serialized)+10).to_bytes(2, byteorder='big') + extensible_seq_temp+ b"\x00\x10\x00\x00\xE3\x58"
    CRC_Header = crc16.xmodem(WS_Header[4:]+serialized)
    final_packet = WS_Header + serialized + bytes.fromhex(hex(CRC_Header)[2:].zfill(4))

    try:
        for r in range(repeat_count):
            should_send = True
            
            if trace_length > 0 and trace_cycle_count < MAX_CYCLES:
                current_status = trace_array[trace_idx]
                if current_status == 0:
                    should_send = False 
                
                trace_idx += 1
                if trace_idx >= trace_length:
                    trace_idx = 0
                    trace_cycle_count += 1
                    print(f"   ➔ [System] Trace Cycle: {trace_cycle_count}/{MAX_CYCLES} 완료")
                
            if should_send:
                send_sock.send(final_packet)
    except BaseException:
        print(traceback.format_exc())
    
    if pkt_seq_num % SLEEP_PARAMS == 0:
        time.sleep(SOCKET_SEND_DELAY)

# ==========================================
# [5] Capture Worker
# ==========================================
class CaptureWorker(QThread):
    """ from video-data to frame data """
    cycle_finished_signal = pyqtSignal()

    def __init__(self, sock, cap, label):
        """ init """
        super().__init__()
        self.video_cap = cap
        self.video_label = label
        self.sock = sock
        self.trig = True
        self.em_manager = EmergencyChannelManager()
        self.packet_counter = 0 

    def run(self):
        """ capture video """
        while self.trig:
            is_cycle_complete = self.em_manager.check_update()
            if is_cycle_complete:
                print("[Worker] Cycle Finished! Switching Mode...")
                self.cycle_finished_signal.emit() 
                self.trig = False
                break

            time.sleep(Config.SENDER_FRAME_MSEC / 1000.0)
            
            ret, frame = self.video_cap.read()
            if ret:
                now = datetime.now() + timedelta(milliseconds=TIME_OFFSET)
                t_int = (now.minute * 100000) + (now.second * 1000) + int(now.microsecond / 1000)
                
                try:                  
                    np_frame = rescale_frame(frame, SEND_FRAME_WIDTH, SEND_FRAME_HEIGHT)
                    if self.video_label:
                        frame_disp = cv2.cvtColor(np_frame, cv2.COLOR_BGR2RGB)
                        image = QImage(frame_disp, frame_disp.shape[1], frame_disp.shape[0], QImage.Format_RGB888)
                        self.video_label.setPixmap(QPixmap.fromImage(image).scaled(self.video_label.width(), self.video_label.height(), Qt.KeepAspectRatio))
                except: pass

                try:
                    frame_data = np_frame.flatten().tobytes()
                    i, ptr = 0, 0
                    
                    while True:
                        segment_num = struct.pack(">h", i)
                        self.packet_counter += 1
                        
                        payload_data = None
                        header_val = b'\x00' * 8 
                        strategy = {"repeat": 1}
                        
                        if self.em_manager.has_pending_chunks():
                            current_iv = self.em_manager.current_interleaving_iv
                            if self.packet_counter % (current_iv + 1) == 0:
                                payload_data, header_val, strategy, _ = self.em_manager.get_package()
                        
                        current_extra = payload_data
                        current_max_video = MAX_FRAME_SIZE
                        if current_extra:
                            overhead = len(current_extra) + len(b'BSM:')
                            current_max_video -= overhead
                        
                        if ptr + current_max_video < len(frame_data):
                            data = frame_data[ptr : ptr + current_max_video]
                            send_5g(self.sock, segment_num + data, t_int, 
                                    header_bytes=header_val, 
                                    extra_payload=current_extra,
                                    repeat_count=strategy["repeat"])
                            ptr += current_max_video 
                            i += 1
                        else:
                            data = frame_data[ptr:]
                            send_5g(self.sock, segment_num + data, t_int, 
                                    header_bytes=header_val, 
                                    extra_payload=current_extra,
                                    repeat_count=strategy["repeat"])
                            break 
                except BaseException: print(traceback.format_exc())
        
        if self.video_label: self.video_label.setPixmap(QPixmap(resource_path('resource/stop_icons.png')))
        self.video_cap.release()
    
    def stop(self):
        """ stop """
        self.trig = False
        self.quit()
        self.wait(100)

# ==========================================
# [6] GUI Main Window
# ==========================================
class SenderWindow(QWidget):
    """ Sender Window configuration  """
    def __init__(self):
        """ init """
        super().__init__()
        self.experiment_modes = ["ADAPTIVE_RS"]
        self.current_mode_idx = 0
        self.is_auto_running = False
        
        global NET_IF, DEVICE_ADDR, TIME_OFFSET
        try: TIME_OFFSET = int(ntplib.NTPClient().request('pool.ntp.org', timeout=1).offset * 1000)
        except BaseException: TIME_OFFSET = 0
        
        interfaces = psutil.net_if_addrs().keys()
        interface, ok = QInputDialog.getItem(self, 'Select Interface', 'Choose IF:', interfaces, 0, False)
        default_txt="192.168.1.11"
        if ok:
             ip, ok = QInputDialog.getText(self, 'Set IP', 'IP:', text=default_txt)
             if ok: DEVICE_ADDR = ip

        while True:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((DEVICE_ADDR, DEVICE_PORT))
                break
            except BaseException: time.sleep(1) 
            
        self.initUI()

    def initUI(self):
        """ Ui Init """
        self.label = QLabel("Ready for CSV-Based Automation")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("font-size: 20px; font-weight: bold; color: blue;")
        
        self.status_label = QLabel(f"Next Mode Queue: {self.experiment_modes}")
        self.status_label.setWordWrap(True)
        
        self.button_auto_start = QPushButton(f"START AUTOMATION")
        self.button_auto_start.setStyleSheet("background-color: red; color: white; font-weight: bold; padding: 10px;")
        self.button_auto_start.clicked.connect(self.start_automation)
        
        self.button_stop = QPushButton("Force Stop")
        self.button_stop.clicked.connect(self.force_stop)
        self.button_stop.setDisabled(True)
        
        self.type_combo = QComboBox(self)
        find_camera_list()
        for i in camera_list: self.type_combo.addItem(camera_list[i])
        self.type_combo.addItem("Saved Video")
        self.video_file_address = QLineEdit()
        self.video_file_address.setPlaceholderText("Video path (if Saved Video selected)")

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.video_file_address)
        layout.addWidget(self.type_combo)
        layout.addWidget(self.button_auto_start)
        layout.addWidget(self.button_stop)
        self.setLayout(layout)
        self.setWindowTitle("V2X Sender - Automation")

    def start_automation(self):
        """ start automation """
        self.is_auto_running = True
        self.current_mode_idx = 0
        self.button_auto_start.setDisabled(True)
        self.button_stop.setDisabled(False)
        self.type_combo.setDisabled(True)
        print(f"[System] Starting Automation.")
        self.run_next_mode()

    def run_next_mode(self):
        """ run Next Mode """
        if not self.is_auto_running: return
        if hasattr(self, 'cap_th') and self.cap_th.isRunning():
            self.cap_th.stop()
            self.cap_th.wait()
            time.sleep(2) 

        if self.current_mode_idx >= len(self.experiment_modes):
            self.finish_experiment()
            return

        next_mode = self.experiment_modes[self.current_mode_idx]
        Config.CURRENT_MODE = next_mode
        self.label.setText(f"RUNNING: {next_mode} ({self.current_mode_idx + 1}/{len(self.experiment_modes)})")
        self.setWindowTitle(f"Sender - {next_mode}")
        print(f"\n[System] SWITCHING MODE -> {next_mode}")

        if self.type_combo.currentText() == "Saved Video":
            self.video_cap = cv2.VideoCapture(self.video_file_address.text())
        else:
            for i in camera_list:
                if self.type_combo.currentText() == camera_list[i]:
                    self.video_cap = cv2.VideoCapture(cv2.CAP_DSHOW+i); break
        
        self.cap_th = CaptureWorker(self.sock, self.video_cap, self.label)
        self.cap_th.cycle_finished_signal.connect(self.run_next_mode)
        self.cap_th.start()
        self.current_mode_idx += 1

    def finish_experiment(self):
        """ ALL Task is Finished  """
        self.label.setText("ALL EXPERIMENTS COMPLETED!")
        self.button_stop.setDisabled(True)
        self.is_auto_running = False

    def force_stop(self):
        """ cap_th Stop  """
        self.is_auto_running = False
        if hasattr(self, 'cap_th'): self.cap_th.stop()
        self.label.setText("Stopped")
        self.button_auto_start.setDisabled(False)
        self.button_stop.setDisabled(True)
        self.type_combo.setDisabled(False)

    def closeEvent(self, e):
        """ close event """
        self.force_stop()
        e.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SenderWindow()
    window.show()
    sys.exit(app.exec_())