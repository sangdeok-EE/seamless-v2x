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

""" Receiver Widnow for Video data & BSM Message """
#버전: 1.0
#최종 수정일: 2026-02-12

import os
import csv
import json
import time
import math
import numpy
#import pickle
import struct
import psutil
import requests
import haversine
import datetime as dt
from socket import *
from scapy.all import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from collections import deque
from screeninfo import get_monitors
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5.QtWebEngineWidgets import QWebEngineView
from datetime import datetime
#from PyQt5.QtWebEngineWidgets import QWebEngineScript
import ntplib
import cv2


# PyQT Windows Size
monitor_size_width = get_monitors()[0].width
monitor_size_height = get_monitors()[0].height
BLANK_SPACE = 15
GRAPH_WIN_SIZE_W = monitor_size_width - BLANK_SPACE*2
GRAPH_WIN_SIZE_H = int(monitor_size_height / 2) - BLANK_SPACE
VIDEO_WIN_SIZE_W = int(monitor_size_width / 2) - BLANK_SPACE
VIDEO_WIN_SIZE_H = int(monitor_size_height / 2) - BLANK_SPACE*3
NAVIGATION_WIN_SIZE_W = int(monitor_size_width / 2) - BLANK_SPACE
NAVIGATION_WIN_SIZE_H = int(monitor_size_height / 2) - BLANK_SPACE*3

# Socket Value
DEVICE_ADDR = '10.254.52.18'
DEVICE_PORT = 12345 #47347

# Packet Value
MAX_FRAME_SIZE = 1400  #2300, 1460
# Camera Capture Size
RECV_FRAME_WIDTH = 300
RECV_FRAME_HEIGHT = 300

MAX_PDR_G = 100
MAX_Latency_G = 500
MAX_Throughput_G = 50
MAX_Distance_G = 400 #meter default =100m

# Log Cycle
HEADER_LOG_CYCLE = 60  # Seconds

# Packet Variable
WS_REQ = b"\x35\x47\x56\x58\x00\x0b\x00\x00\x00\x12\x00\x00\x00\xE3\x58\xf4\x5c\x00"

WS_RESP_MAGIC_NUM = b'\x35\x47\x56\x58' #5GVX
MAGIC_NUM = b'\x00\x00\xe3\x6e'         #58222

VIDEO_DATA_INDICATOR = b'\x03\x01' 

# Graph Data Variable
NET_IF = "ethernet"

# Navigation HTML File Path
HTML_FILE_PATH = './resource/Tmap.html'

# Bad Condition Data Variable
WEATHER_API_URL = 'http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst'
WEATHER_API_SERVICE_KEY = 'QEPmvbFk9szqqPD8q9+s2ezoOOoY7VcAt4Rt1QPseyZ5LQucie5H9OjnJj/GO4H1I41QrmGWQxhCF9FGp42ZQA=='
WEATHER_CONDITION_WAIT_TIMER = 5
WEATHER_CONDITION_ERROR_RESEND_TIMER = 10
WEATHER_CONDITION_RESEND_TIMER = 600
ROAD_API_URL = 'https://apis.openapi.sk.com/tmap/traffic'
ROAD_API_SERVICE_KEY = 'fOsIyENUEf8ArejvlqGDU4p66eOsMRjB5kII22do'
ROAD_CONDITION_WAIT_TIMER = 5
ROAD_CONDITION_RESEND_TIMER = 600 # Receive traffic data per 10 minute

#PACKET DEFINE
PCK_MAGIC = 0           # "5GVX", 0x35475658
PCK_HEADER_LEN =  4 
PCK_HEADER_SEQ =  6
PCK_HEADER_ID =  8      # payload Tx-0x0010, Rx-0x0011
PCK_HEADER_TYPE = 10    # PSID=58200(V2V), 0xE358
PCK_RCPI = 14           # Only Rxmsg
PCK_OVERALL_TYPE = 15   # 58220, 0xE36C
PCK_OVERALL_LEN = 19    # value = 10, "EMOP"(4, 0x454d4f50) + version(1) + Package Num(1) + Package len(2) + CRC(2)

PCK_SSOV_TYPE = 31      #58222, 0xE36E
PCK_SSOV_LEN = 35
PCK_SSOV_HEADER = 37
PCK_SSOV_DATA = 77

PCK_SSOV_MIN_LEN = 42

PCK_STATUS_TYPE = 26    #OBU TX Package(26)
PCK_STATUS_TX = 26 + 16 #OBU TX Package(26) + T(4, 58223, 0xE36F ) + L(2) + Txtimestamp(10)
PCK_STATUS_TX_LAT = 26 + 16 + 14 #OBU Package(26)+ T(4) + L(2) + ...
PCK_STATUS_TX_LON = 26 + 16 + 14 + 4 #OBU Package(26)+ T(4) + L(2) + ...

PCK_STATUS_RX = 26 + 40 + 16 #OBU Package(26) + TXMODEM(4+2+32+2) + T(4) + L(2) + Txtimestamp(10)
PCK_STATUS_RX_LAT = 26 + 40 + 16 + 10
PCK_STATUS_RX_LON = 26 + 40 + 16 + 10 + 4

VOD_INDICATOR = 0
VOD_SEQ = 2
VOD_LINE_NUM = 6
VOD_LINE_DATA = 8

sender_latitude = 37.570286992195
sender_longitude = 126.98361037914
latitude = 37.570286992195
longitude = 126.98361037914
road_condition = 0
weather_condition = 0
pdr_result = 0.0
throughput_result = 0.0
latency_result = 0.0
distance_result = 0.0
# 화면 표시용 (1초 평균 latency 버퍼)
latency_buffer = deque()
result_queue = deque()
webView = 0
wes_tag = True
video_frame = numpy.zeros((RECV_FRAME_HEIGHT* RECV_FRAME_WIDTH* 3), numpy.uint8)
sendt=0
rect=0 


# ==========================================
# [FIXED] GF(256) Arithmetic Engine
# ==========================================
POLY = 0x11D 
GF256_EXP = [0] * 512
GF256_LOG = [0] * 256

def init_tables():
    x = 1
    for i in range(255):
        GF256_EXP[i] = x
        GF256_LOG[x] = i
        x <<= 1
        if x & 0x100: x ^= POLY
    for i in range(255, 512):
        GF256_EXP[i] = GF256_EXP[i-255]

init_tables()

def gf_add(a, b): return a ^ b

def gf_mul(a, b):
    if a == 0 or b == 0: return 0
    return GF256_EXP[GF256_LOG[a] + GF256_LOG[b]]

def gf_inv(a):
    if a == 0: raise ZeroDivisionError
    return GF256_EXP[255 - GF256_LOG[a]]

# ==========================================
# [Logic] Reed-Solomon Decoder (K=10)
# ==========================================
class ReedSolomonSimple:
    """ Reed Solomon Deciding """
    # [수정 1] 기본값 변경: symbol_size=7 (7바이트), K=8 (8개 조각)
    def __init__(self, symbol_size=7, K=8):
        """ init """
        self.S = symbol_size
        self.K = K

    def _get_recipe(self, esi):
        """
        Cauchy Matrix 기반의 인코딩 계수 생성 (송신부와 로직 동일해야 함)
        Repair Packet (ESI >= K)에 대한 계수를 계산합니다.
        """
        if esi < self.K: return None 
        
        # Cauchy Matrix Coefficient: 1 / (x_row ^ y_col)
        # x_val = ESI (행 인덱스)
        x_val = esi 
        idxs = list(range(self.K))
        coefs = []
        
        for y_val in range(self.K):
            # 주의: 송신부(Tx)에서도 동일하게 1 / (esi ^ col) 로직을 써야 함
            coefs.append(gf_inv(x_val ^ y_val))
            
        return list(zip(idxs, coefs))

    def decode(self, received_items):
        """
        received_items: list of (esi, bytes_payload)
        리스트 길이는 최소 K 이상이어야 함.
        """
        K = self.K
        
        # 1. 개수 부족 시 즉시 실패
        if len(received_items) < K: 
            return None
        
        # 2. 앞에서부터 딱 K개만 사용 (과다 정보는 버림)
        subset = received_items[:K]
        
        # 3. 행렬 구성 (Matrix Construction)
        # A: 인코딩 매트릭스 (K x K), B: 데이터 매트릭스 (K x S)
        A = []
        B = []
        
        for esi, payload in subset:
            row = [0] * K
            
            # (1) 원본 데이터 패킷인 경우 (Identity Row)
            if esi < K:
                row[esi] = 1
            # (2) 복구용 패킷인 경우 (Cauchy Row)
            else:
                for idx, coef in self._get_recipe(esi):
                    row[idx] = coef
            
            A.append(row)
            B.append(list(payload))

        # 4. 가우스 소거법 (Gaussian Elimination)
        try:
            for i in range(K):
                # 피벗(Pivot) 찾기: 대각 성분이 0이면 아래 행과 교체
                if A[i][i] == 0:
                    for j in range(i+1, K):
                        if A[j][i] != 0:
                            A[i], A[j] = A[j], A[i]
                            B[i], B[j] = B[j], B[i]
                            break
                    else:
                        # 피벗을 못 찾으면 복구 불가능 (특이 행렬)
                        return None 

                # 피벗 정규화 (1로 만들기)
                inv = gf_inv(A[i][i])
                A[i] = [gf_mul(x, inv) for x in A[i]]
                B[i] = [gf_mul(x, inv) for x in B[i]]
                
                # 다른 행들의 해당 열 소거 (0으로 만들기)
                for j in range(K):
                    if i != j and A[j][i] != 0:
                        factor = A[j][i]
                        A[j] = [gf_add(x, gf_mul(y, factor)) for x, y in zip(A[j], A[i])]
                        B[j] = [gf_add(x, gf_mul(y, factor)) for x, y in zip(B[j], B[i])]
            
            # 5. 결과 직렬화 (Matrix to Bytes)
            out = bytearray()
            for i in range(K): 
                out.extend(B[i])
            return bytes(out)

        except BaseException:
            # 수학적 예외 발생 시 안전하게 None 리턴
            return None

def resource_path(relative_path):
    """ resource(icon, png) path """
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

def create_log_folder():
    """ 5g-nr Video & BSM Performance log file """
    now = dt.datetime.now() 
    try: 
        if not os.path.exists(now.strftime('%Y.%m.%d')): 
            os.makedirs(now.strftime('%Y.%m.%d')) 
    except OSError: 
        print('Error:Cannot creat directory.' + now.strftime('%Y.%m.%d')) 
    return now.strftime('%Y.%m.%d')

# ==========================================
# [Logic] Receiver Emergency Manager
# ==========================================
class RxEmergencyManager:
    """ Rx Parameter Setting """
    # [수정 2] 초기화 파라미터 변경 (K=8, symbol_size=7)
    def __init__(self, K: int = 8, symbol_size: int = 7):
        """ init """
        self.K = K
        self.rs = ReedSolomonSimple(symbol_size, K)
        
        self.buffer: Dict[int, bytes] = {} 
        self.current_seq: int = -1       
        self.is_completed: bool = False

    def process_packet(self, header_bytes: bytes) -> Optional[str]:
        """ Header(BSM) Packet Processing """
        # header_bytes: 8바이트 (unDeviceId 4B + eServiceId 2B + eActionType 2B)
        
        # 1. 비트 파싱 (8바이트 중 첫 1바이트는 헤더, 나머지 7바이트는 데이터)
        if len(header_bytes) != 8:
            return None
            
        header_byte = header_bytes[0] # 첫 번째 바이트가 RS Header
        payload_bytes = header_bytes[1:] # 나머지 7바이트가 데이터
        
        msg_seq = (header_byte >> 6) & 0x03
        esi = header_byte & 0x3F
        
        # [초기 상태]
        if self.current_seq == -1:
            self.current_seq = msg_seq
            self.is_completed = False
            self.buffer[esi] = payload_bytes
            return None 

        # 2. 시퀀스 검사
        diff = (msg_seq - self.current_seq + 4) % 4

        if diff == 0:
            pass 
        elif diff == 1 or diff == 2:
            self.buffer.clear()
            self.current_seq = msg_seq
            self.is_completed = False
        else: 
            return None

        if self.is_completed:
            return None

        # 3. 버퍼링
        if esi not in self.buffer:
            self.buffer[esi] = payload_bytes

        # 4. 복구 시도 (K=8개 모이면)
        if len(self.buffer) >= self.K:
            return self._decode_current()
        
        return None

    def _decode_current(self) -> Optional[str]:
        """ check decoding paket size """
        try:
            chunks = list(self.buffer.items())
            decoded_bytes = self.rs.decode(chunks)
            
            if decoded_bytes:
                # 56바이트 데이터에서 뒤쪽 패딩('*') 제거
                msg = decoded_bytes.rstrip(b'*').decode('utf-8', errors='ignore')
                
                self.is_completed = True
                self.buffer.clear() 
                return msg
        except BaseException:
            pass
        return None

class SaveUrgentWorker(QThread):
    """ save receive message log : Urgent_Log """
    def __init__(self, emergency_q):
        """ init """
        super().__init__()
        self.emergency_q = emergency_q
        self.trig = True

    def run(self):
        """ create log file and save """
        # 1. 파일 이름 생성 (날짜/시간 포함)
        now = dt.datetime.now()
        folder_name = create_log_folder() 
        file_name = f"Urgent_Log_{now.strftime('%Y.%m.%d.%H.%M')}.csv"
        file_path = os.path.join(folder_name, file_name)

        # 2. 파일 열기 및 헤더 작성
        try:
            f = open(file_path, 'w', encoding='utf-8', newline='')
            wr = csv.writer(f)
            wr.writerow(['Rx_Timestamp', 'Message_Content', 'Note'])
            f.flush()
        except BaseException:
            print(traceback.format_exc())
            return

        while self.trig:
            try:
                while len(self.emergency_q) > 0:
                    data = self.emergency_q.popleft()

                    timestamp_str = data[0].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    msg_content = data[1]
                    wr.writerow([timestamp_str, msg_content, "Urgent"])
                    
                f.flush()

                time.sleep(HEADER_LOG_CYCLE)

            except BaseException:
                print(traceback.format_exc())
                time.sleep(1)
        if f:
            while len(self.emergency_q) > 0:
                try:
                    data = self.emergency_q.popleft()
                    wr.writerow([data[0].strftime('%Y-%m-%d %H:%M:%S'), data[1], "Urgent_Last"])
                except BaseException:
                    pass
            f.close()

    def stop(self):
        self.trig = False
        self.quit()
        self.wait(10)

class SaveHeaderWorker(QThread):
    """ Add Message Header to log """
    info_signal = pyqtSignal(str)
    global sendt
    def __init__(self, info_box, header_q):
        super().__init__()

        #self.info_box = info_box
        self.header_q = header_q
        self.trig = True

    def run(self):
        """ update logfile """
        global result_queue
        i = 0
        mileage_log = 0
        weather_condition_log_pre = 1
        while self.trig:
            num_header = len(self.header_q)
            if num_header > 0:
                try:
                    now = dt.datetime.now()
                    past = now - dt.timedelta(minutes=1)
                    file_name = ("ETRI_OBU_01(RX))_" + past.strftime('%Y.%m.%d.%H.%M') + "_"
                                 + now.strftime('%Y.%m.%d.%H.%M') + "_" + str(HEADER_LOG_CYCLE) + "seconds.csv")
                    folder_name = create_log_folder()
                    file_path = './'+folder_name+'/'+file_name
                    f = open(file_path, 'w', encoding='utf-8', newline='')
                    wr = csv.writer(f)
                    header_list = ['No.', 'eDeviceType', 'eTeleCommType', 'unDeviceId', 'ulTimeStamp',
                                   'eServiceId', 'eActionType', 'eRegionId', 'ePayloadType', 'eCommId', 'usDbVer',
                                   'usHwVer', 'usSwVer', 'ulPayloadLength', 'Reserved',
                                   'E2ELatency', 'nothing',
                                   'PDR', 'Throughput', 'Latency', 'Distance', 'rx_latitude', 'rx_longitude', 'tx_latitude',
                                   'tx_longitude', 'tx_time', 'rx_time', 'Mileage','Viewtime']
                    wr.writerow(header_list)

                    i = 0
                    while True:
                        try:
                            header_log = self.header_q.popleft()
                            # SSOV (length = 40)
                            eDeviceType = struct.unpack(">H", header_log[0][0:2])[0]
                            eTeleCommType = struct.unpack(">H", header_log[0][2:4])[0]
                            unDeviceId = struct.unpack(">i", header_log[0][4:8])[0]
                            ulTimeStamp = struct.unpack(">q", header_log[0][8:16])[0]
                            eServiceId = struct.unpack(">H", header_log[0][16:18])[0]
                            eActionType = struct.unpack(">H", header_log[0][18:20])[0]
                            eRegionId = struct.unpack(">H", header_log[0][20:22])[0]
                            ePayloadType = struct.unpack(">H", header_log[0][22:24])[0]
                            eCommId = struct.unpack(">H", header_log[0][24:26])[0]
                            usDbVer = struct.unpack(">H", header_log[0][26:28])[0]
                            usHwVer = struct.unpack(">H", header_log[0][28:30])[0]
                            usSwVer = struct.unpack(">H", header_log[0][30:32])[0]
                            ulPayloadLength = struct.unpack(">i", header_log[0][32:36])[0]
                            Reserved = struct.unpack(">i", header_log[0][36:40])[0]
                            
                            ####################### e2e latency 계산로직
                            r_total = header_log[1]

                            s_total = (((Reserved >> 24) & 0xFF) * 60000) + \
                            (((Reserved >> 16) & 0xFF) * 1000) + \
                            (Reserved & 0xFFFF)
                            
                            latency = r_total - s_total
                            
                            Reserved = 0
                            road_condition_log = latency
                            weather_condition_log = header_log[2]
                            
                            #######################  여기 밑에 좀 이상하게 값 넣음.
                            pdr_result_log = header_log[3]
                            if pdr_result_log > 100 or pdr_result_log < 0:
                                continue     
                            throughput_result_log = header_log[4]
                            if throughput_result_log > 100 or throughput_result_log < 0:
                                continue                                 
                            latency_result_log = header_log[5]
      
                            distance_result_log = header_log[6]
                            rx_latitude = header_log[7]
                            if rx_latitude > 39 or rx_latitude < 29:
                                continue
                            rx_longitude = header_log[8]
                            if rx_longitude > 132 or rx_longitude < 124:
                                continue
                            tx_latitude = header_log[9]
                            if tx_latitude > 39 or tx_latitude < 29:
                                continue
                            tx_longitude = header_log[10]
                            if tx_longitude > 132 or tx_longitude < 124:
                                continue
                            tx_time = int.from_bytes(header_log[11])
                            if tx_time < 0:
                                continue
                            rx_time = int.from_bytes(header_log[12])
                            if rx_time < 0:
                                continue
                            if i == 0:
                                mileage_log = 0
                                before_latitude = header_log[7]
                                before_longitude = header_log[8]
                            else:
                                mileage_log = mileage_log + haversine.haversine((before_latitude, before_longitude),
                                                                                (header_log[7], header_log[8]), unit='m')
                                before_latitude = header_log[7]
                                before_longitude = header_log[8]
                            log = [
                                i,
                                eDeviceType,
                                eTeleCommType,
                                unDeviceId,
                                ulTimeStamp,
                                eServiceId,
                                eActionType,
                                eRegionId,
                                ePayloadType,
                                eCommId,
                                usDbVer,
                                usHwVer,
                                usSwVer,
                                ulPayloadLength,
                                Reserved,
                                road_condition_log,
                                weather_condition_log,
                                pdr_result_log,
                                throughput_result_log,
                                latency_result_log,
                                distance_result_log,
                                rx_latitude,
                                rx_longitude,
                                tx_latitude,
                                tx_longitude,
                                tx_time,
                                rx_time,
                                mileage_log,
                            ]
                            if now < header_log[13]:
                                print("now error")
                                break
                            else:
                                wr.writerow(log)
                                i = i+1
                        except BaseException:
                            break
                    f.close()
                    self.info_signal.emit(dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S') + "\n - Saving Log File\n(" + file_name + ")\n - Mileage : " + str(mileage_log))
                    time.sleep(HEADER_LOG_CYCLE)
                except BaseException:
                    print(traceback.format_exc())

    def stop(self):
        """ stop logfile """
        self.trig = False
        self.quit()
        self.wait(10)


class ViewWorker(QThread):
    """ View receive video-data """
    def __init__(self, frame, label):
        """ init """
        super().__init__()
        self.frame = frame
        self.video_label = label
        self.trig = True
        global video_frame
    def run(self):
        """ show frame """
        while self.trig:
            try:
                video = video_frame.reshape(RECV_FRAME_WIDTH,RECV_FRAME_HEIGHT,3)
                #show_frame = cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB)
                show_frame = cv2.cvtColor(video, cv2.COLOR_BGR2RGB)
                image = QImage(show_frame, show_frame.shape[1], show_frame.shape[0], QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(image)
                self.video_label.setPixmap(pixmap)    
            except BaseException:
                print(traceback.format_exc())
            time.sleep(0.1)
        self.video_label.setPixmap(QPixmap(resource_path('./resource/stop_icons.png')))

    def stop(self):
        """ stop video """
        self.trig = False
        self.quit()
        self.wait(10) 

class ReceiveWorker(QThread):
    """ Receive Message Processing """
    def __init__(self, sock, frame, pkt_num_q, header_q, emergency_q ):
        """ init """
        super().__init__()
        global DEVICE_ADDR
        global DEVICE_PORT
        global RECV_FRAME_WIDTH
        global RECV_FRAME_HEIGHT
        global WS_RESP_MAGIC_NUM
        global VIDEO_DATA_INDICATOR
        
        self.show_frame = frame
        self.pkt_num_q = pkt_num_q
        self.header_q = header_q
        self.sock = sock
        self.trig = True
        self.emergency_q = emergency_q
        
        # 56바이트 설정 (K=8, Symbol=7)
        self.rx_manager = RxEmergencyManager(K=8, symbol_size=7)
        
        self.OFFSET_DEVICE_ID = PCK_SSOV_HEADER + 4

    def run(self):
        """ Receive packet and processing """
        global sender_latitude
        global sender_longitude
        global latitude
        global longitude        
        global latency_result
        global video_frame
        
        # E2E Latency 측정 설정
        ENABLE_LATENCY_METRIC = True 
        global TIME_OFFSET
        TIME_OFFSET = 0
        
        if ENABLE_LATENCY_METRIC:
            try:
                client = ntplib.NTPClient()
                response = client.request('pool.ntp.org', timeout=1)
                TIME_OFFSET = int(response.offset * 1000) 
            except BaseException:
                print("NTP Sync Failed. Using Local Time.")
        
        while self.trig:
            try:
                packet = self.sock.recv(1024 * 12)
            except BaseException:
                print(traceback.format_exc())
                continue
            
            packet_ptr = 0
            packet_len = len(packet)
            
            while True:
                try:
                    if packet[packet_ptr + PCK_MAGIC :packet_ptr + PCK_MAGIC + 4] == WS_RESP_MAGIC_NUM:
                        packet_header_id = packet[packet_ptr+PCK_HEADER_ID:packet_ptr+PCK_HEADER_ID+2]
                        
                        if packet_header_id == b'\x00\x11': # RX Message
                            ssov_len = int.from_bytes(packet[packet_ptr+PCK_SSOV_LEN:packet_ptr+PCK_SSOV_LEN+2], "big")
                            
                            current_pkt_len = PCK_SSOV_DATA + ssov_len - PCK_SSOV_MIN_LEN
                            if packet_ptr + current_pkt_len > packet_len:
                                break 
                            
                            now = dt.datetime.now()
                            ssov_data_raw = packet[packet_ptr+PCK_SSOV_DATA : packet_ptr+PCK_SSOV_DATA+ssov_len-PCK_SSOV_MIN_LEN]
                            
                            # =========================================================
                            # 8바이트 헤더 추출 (unDeviceId + eServiceId + eActionType)
                            # =========================================================

                            dev_id_pos = packet_ptr + PCK_SSOV_HEADER + 4   # unDeviceId (4 Bytes)
                            svc_id_pos = packet_ptr + PCK_SSOV_HEADER + 16  # eServiceId (2 Bytes)
                            act_id_pos = packet_ptr + PCK_SSOV_HEADER + 18  # eActionType (2 Bytes)
                            
                            b_unDevice = packet[dev_id_pos : dev_id_pos + 4]
                            b_eService = packet[svc_id_pos : svc_id_pos + 2]
                            b_eAction  = packet[act_id_pos : act_id_pos + 2]

                            header_bytes_8b = b_unDevice + b_eService + b_eAction
                            urgent_msg = None
                            video_payload = ssov_data_raw 
                            
                            # (A) RS 계열은 이쪽으로
                            bsm_index = ssov_data_raw.find(b'BSM:')
                            
                            if bsm_index != -1:
                                video_payload = ssov_data_raw[:bsm_index] 
                                raw_text = ssov_data_raw[bsm_index + 4:]  
                                try:
                                    urgent_msg = raw_text.decode('utf-8', errors='ignore')
                                except BaseException:
                                    pass
                                    
                            # (B) RAW/REP들은 이쪽으로
                            elif header_bytes_8b != b'\x00'*8:
                                urgent_msg = self.rx_manager.process_packet(header_bytes_8b)

                            # (C) 메시지 UI 표시 및 저장
                            if urgent_msg:
                                self.emergency_signal.emit(urgent_msg)
                                offsettime = dt.datetime.now() + dt.timedelta(milliseconds=TIME_OFFSET)
                                self.emergency_q.append([offsettime, urgent_msg])
                            # =========================================================
                            
                            # 4. 영상 처리 (원본 그대로)
                            if len(video_payload) > 2 and video_payload[VOD_INDICATOR:VOD_INDICATOR+2] == VIDEO_DATA_INDICATOR:
                                self.pkt_num_q.append(int.from_bytes(video_payload[VOD_SEQ :VOD_SEQ +4], "big"))
                                try:
                                    if(len(video_payload) >= VOD_LINE_NUM+2) :
                                        frame_line_num = struct.unpack(">h", video_payload[VOD_LINE_NUM:VOD_LINE_NUM+2])[0]
                                    else: 
                                        frame_line_num = 0
                                    
                                    frame_line_data = numpy.frombuffer(video_payload[VOD_LINE_DATA:], dtype=numpy.uint8)
                                    start_pos = frame_line_num * MAX_FRAME_SIZE
                                    end_pos = start_pos + len(frame_line_data)
                                    
                                    if end_pos <= len(video_frame):
                                        video_frame[start_pos : end_pos] = frame_line_data
                                
                                    # Latency 계산
                                    r_total = (now.minute * 60000) + (now.second * 1000) + (now.microsecond // 1000) + TIME_OFFSET
                                    p_start = packet_ptr + PCK_SSOV_HEADER + 36
                                    s_val = int.from_bytes(packet[p_start : p_start+4], 'big')
                                    s_total = (((s_val >> 24) & 0xFF) * 60000) + (((s_val >> 16) & 0xFF) * 1000) + (s_val & 0xFFFF)

                                    status_offset = PCK_STATUS_TYPE
                                    packet_end_offset = packet_ptr + PCK_SSOV_DATA + ssov_len - PCK_SSOV_MIN_LEN + 2
                                    
                                    if len(packet) > (packet_end_offset + status_offset + 4):
                                        if packet[packet_end_offset + status_offset : packet_end_offset + status_offset + 4] == b'\x00\x00\xe3\x6f':
                                            tx_base = packet_end_offset + PCK_STATUS_TX
                                            rx_base = packet_end_offset + PCK_STATUS_RX
                                            try:
                                                sender_latitude = int.from_bytes(packet[packet_end_offset + PCK_STATUS_TX_LAT : packet_end_offset + PCK_STATUS_TX_LAT+4], 'big')/1000000
                                                sender_longitude = int.from_bytes(packet[packet_end_offset + PCK_STATUS_TX_LON : packet_end_offset + PCK_STATUS_TX_LON+4], 'big')/1000000
                                                latitude = int.from_bytes(packet[packet_end_offset + PCK_STATUS_RX_LAT : packet_end_offset + PCK_STATUS_RX_LAT+4], 'big')/1000000
                                                longitude = int.from_bytes(packet[packet_end_offset + PCK_STATUS_RX_LON : packet_end_offset + PCK_STATUS_RX_LON+4], 'big')/1000000
                                                
                                                tx_time = packet[tx_base : tx_base+8] 
                                                rx_time = packet[rx_base : rx_base+8] 
                                                
                                                latency_result = r_total - s_total
                                                if 0 <= latency_result <= MAX_Latency_G:
                                                    latency_buffer.append(latency_result)
                                                
                                                self.header_q.append([
                                                    packet[packet_ptr+PCK_SSOV_HEADER:packet_ptr+PCK_SSOV_HEADER+40], 
                                                    r_total, weather_condition, pdr_result, throughput_result, 
                                                    latency_result, distance_result, latitude, longitude, 
                                                    sender_latitude, sender_longitude, tx_time, rx_time, dt.datetime.now()
                                                ])
                                            except BaseException:
                                                pass
                                except BaseException:
                                    print(traceback.format_exc())
                                    
                            packet_ptr = packet_ptr + 1
                            if packet_ptr >= len(packet): break
                        else:
                            pass # Wrong Payload ID
                    
                    packet_ptr = packet_ptr + 1
                    if packet_ptr >= len(packet): break

                except BaseException:
                    print(traceback.format_exc())
                    continue

    def stop(self):
        """ stop receive data """
        self.trig = False
        self.quit()
        self.wait(10)


class ReceiverVideoWindow(QWidget):
    """ Receive Video Window  """
    def __init__(self):
        """ init  """
        super().__init__()
        self.show_frame = numpy.zeros((RECV_FRAME_HEIGHT, RECV_FRAME_WIDTH, 3), numpy.uint8)
        self.pkt_num_q = deque()
        self.header_q = deque()
        
        # 긴급 메시지 로그용 큐
        self.emergency_q = deque()

        global NET_IF
        global DEVICE_ADDR

        interfaces = psutil.net_if_addrs().keys()

        interface, ok = QInputDialog.getItem(self, 'Select Interface', 'Choose a network interface:', 
                                             interfaces, 0, False)
        default_txt ="10.254.52.18"
        if ok and interface:
            ip, ok = QInputDialog.getText(self, 'Set IP Address', 'Enter an IP address (e.g., 10.254.52.18):', text=default_txt)
            
            if ok:
                try:
                    ip_parts = list(map(int, ip.split('.')))
                    if len(ip_parts) == 4 and all(0 <= part < 256 for part in ip_parts):
                        NET_IF = interface
                        DEVICE_ADDR = ip
                        print(f"Selected Interface: {NET_IF}, IP Address: {DEVICE_ADDR}")
                    else:
                        raise ValueError
                except ValueError:
                    QMessageBox.warning(self, "Invalid IP", "Please enter a valid IP address.")

        while True:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((DEVICE_ADDR, DEVICE_PORT))
                print("socket connect")
                break
            except BaseException:
                print("socket error")
                print(traceback.format_exc())

        self.label = QLabel()
        self.label.setScaledContents(True)
        self.label.setPixmap(QPixmap(resource_path('./resource/stop_icons.png')))
        self.button_play = QPushButton("Receive")
        self.button_play.clicked.connect(self.play_receive_video)
        self.button_pause = QPushButton("Pause")
        self.button_pause.clicked.connect(self.pause_video)
        self.button_pause.setDisabled(True)
        self.info_box = QTextEdit()
        self.info_box.setReadOnly(True)

        # UI Arrangement
        self.layout = QGridLayout()
        self.left_layout = QVBoxLayout()
        self.right_layout = QVBoxLayout()
        self.left_layout.addWidget(self.button_play)
        self.left_layout.addWidget(self.button_pause)
        self.left_layout.addWidget(self.info_box)
        self.right_layout.addWidget(self.label)
        self.layout.setColumnStretch(0, 2)
        self.layout.setColumnStretch(1, 4)
        self.layout.addLayout(self.left_layout, 0, 0)
        self.layout.addLayout(self.right_layout, 0, 1)
        # Final UI Layout Arrangement
        self.setLayout(self.layout)
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setFixedSize(VIDEO_WIN_SIZE_W, VIDEO_WIN_SIZE_H)
        self.move(BLANK_SPACE, int(monitor_size_height/2) + BLANK_SPACE)
        # Receiver Graph Window Setting
        self.receiver_graph_window = ReceiverGraphWindow(self.pkt_num_q)
        self.receiver_graph_window.show()
        # Receiver Navigation Window Setting
        self.navigation_window = NavigationWindow()
        self.navigation_window.show()


    def play_receive_video(self):
        """ play video & thread start  """
        self.show_frame = numpy.zeros((RECV_FRAME_HEIGHT, RECV_FRAME_WIDTH, 3), numpy.uint8)
        self.pkt_num_q.clear()
        self.header_q.clear()
        self.emergency_q.clear()
        self.info_box.append(dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S') + " : Start Receiving")
        self.rec_th = ReceiveWorker(self.sock, self.show_frame, self.pkt_num_q, self.header_q, self.emergency_q) 
        self.rec_th.emergency_signal.connect(self.display_urgent_message)
        self.view_th = ViewWorker(self.show_frame, self.label)
        
        
        self.save_header_th = SaveHeaderWorker(self.info_box, self.header_q)
        self.save_header_th.info_signal.connect(self.update_infobox)
        self.save_urgent_th = SaveUrgentWorker(self.emergency_q)
        self.rec_th.start()
        self.view_th.start()
        
        self.save_header_th.start()
        self.save_urgent_th.start()
        self.button_play.setDisabled(True)
        self.button_pause.setDisabled(False)

    def pause_video(self):
        """ stop video & thread """
        self.info_box.append(dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S') + " : Stop Receiving")
        self.rec_th.stop()
        self.view_th.stop()
        self.save_header_th.stop()
        self.save_urgent_th.stop()
        self.button_play.setDisabled(False)
        self.button_pause.setDisabled(True)

    def update_infobox(self, log):
        """ update log text  """
        self.info_box.setText(log)
        
    def display_urgent_message(self, msg):
        timestamp = dt.datetime.now().strftime('%H:%M:%S')
        formatted_msg = f"<font color='red'><b>[URGENT {timestamp}] {msg}</b></font>"
        self.info_box.append(formatted_msg)

    def closeEvent(self, event):
        """ cose Receive video window """
        event.accept()



class PDRWorker(QThread):
    """ Display PDR Graph """
    def __init__(self, pkt_num_q, pdr_subplot, pdr_graph_canvas):
        """ init  """
        super().__init__()
        self.pkt_num_q = pkt_num_q
        self.pdr_subplot = pdr_subplot
        self.pdr_graph_canvas = pdr_graph_canvas
        self.pdr_data = []
        self.current_time = []
        self.trig = True

    def run(self):
        """ PDR Graph processing """
        global pdr_result

        while self.trig:
            try:
                pkt_count = 0
                start_num = 0
                end_num = 0
                if len(self.pkt_num_q) != 0:
                    pkt_count = 1
                    start_num = self.pkt_num_q.popleft()
                    end_num = start_num
                while True:
                    if len(self.pkt_num_q) == 0:
                        break
                    end_num = self.pkt_num_q.popleft()
                    pkt_count = pkt_count + 1
                if end_num < start_num:
                    end_num = end_num + 1000000
                pdr_result = (pkt_count * 100) / (end_num - start_num + 1)

                if len(self.pdr_data) == 60:
                    del self.pdr_data[0]
                    del self.current_time[0]
                self.pdr_data.append(pdr_result)
                self.current_time.append(dt.datetime.now())

                self.pdr_subplot.clear()
                self.pdr_subplot.set_ylim(0, MAX_PDR_G)
                self.pdr_subplot.plot(self.current_time, self.pdr_data)
                self.pdr_subplot.text(dt.datetime.now() - dt.timedelta(seconds=0.01), pdr_result + 2,
                                      "{:.3f}%".format(pdr_result))

                self.pdr_subplot.set_ylabel("Packet Delivery Ratio(%)")
                self.pdr_subplot.fill_between(self.current_time, self.pdr_data, alpha=0.5)

                self.pdr_graph_canvas.draw()
            except BaseException:
                print(traceback.format_exc())
            time.sleep(1)

    def stop(self):
        """ stop PDR Grapn  """
        self.trig = False
        self.quit()
        self.wait(10)


class ThroughputWorker(QThread):
    """ Display Throughput Graph """
    def __init__(self, throughput_subplot, throughput_graph_canvas):
        """ init """
        super().__init__()
        self.throughput_subplot = throughput_subplot
        self.throughput_graph_canvas = throughput_graph_canvas
        self.throughput_data = []
        self.current_time = []
        self.trig = True

    def run(self):
        """ Throughput Graph processing"""
        global throughput_result

        while self.trig:
            try:
                initial_stats = psutil.net_io_counters(pernic=True)

                # Wait for the specified interval
                time.sleep(1)

                # Get the updated network statistics
                updated_stats = psutil.net_io_counters(pernic=True)

                for interface, initial in initial_stats.items():
                    if interface == NET_IF:
                        updated = updated_stats[interface]
                        throughput_result = updated.bytes_recv - initial.bytes_recv
                        break
                    throughput_result = 0.0
                throughput_result = float(throughput_result / 125000)

                if len(self.throughput_data) == 60:
                    del self.throughput_data[0]
                    del self.current_time[0]
                self.throughput_data.append(throughput_result)
                self.current_time.append(dt.datetime.now())

                self.throughput_subplot.clear()
                self.throughput_subplot.set_ylim(0, MAX_Throughput_G)
                self.throughput_subplot.plot(self.current_time, self.throughput_data)
                self.throughput_subplot.text(dt.datetime.now() - dt.timedelta(seconds=0.01), throughput_result + 2,
                                             "{:.3f}Mbps".format(throughput_result))

                self.throughput_subplot.set_ylabel("Throughput(Mbps)")
                self.throughput_subplot.fill_between(self.current_time, self.throughput_data, alpha=0.5)

                self.throughput_graph_canvas.draw()
            except BaseException:
                print(traceback.format_exc())

    def stop(self):
        """ stop Throughput Graph """
        self.trig = False
        self.quit()
        self.wait(10)


class DistanceWorker(QThread):
    """ Display Dsitance Graph """
    def __init__(self, distance_subplot, distance_graph_canvas):
        """ init """
        super().__init__()

        self.distance_subplot = distance_subplot
        self.distance_graph_canvas = distance_graph_canvas
        self.distance_data = []
        self.current_time = []
        self.trig = True

    def run(self):
        """ Calculate V2V distance """
        global sender_latitude
        global sender_longitude
        global latitude
        global longitude
        global distance_result
        self.d_result = 0

        while self.trig:
            try:
                # Fix distance csv value = 0, add by neuron, 2025.01
                self.d_result = haversine.haversine((sender_latitude, sender_longitude),
                                                      (latitude, longitude), unit='m')
                # Fix High value in distance graph one-times
                if ((self.d_result >= 0) and (self.d_result < MAX_Distance_G)):
                    distance_result = self.d_result 
                    
                if len(self.distance_data) == 60:
                    del self.distance_data[0]
                    del self.current_time[0]
                self.distance_data.append(distance_result)
                self.current_time.append(dt.datetime.now())

                self.distance_subplot.clear()
                self.distance_subplot.set_ylim(0, MAX_Distance_G)
                self.distance_subplot.plot(self.current_time, self.distance_data)
                self.distance_subplot.text(dt.datetime.now() - dt.timedelta(seconds=0.01), distance_result + 2,
                                           "{:.3f}m".format(distance_result))

                self.distance_subplot.set_ylabel("Distance(Meters)")
                self.distance_subplot.fill_between(self.current_time, self.distance_data, alpha=0.5)

                self.distance_graph_canvas.draw()
            except BaseException:
                print(traceback.format_exc())
            time.sleep(1)

    def stop(self):
        """ stop distance graph """
        self.trig = False
        self.quit()
        self.wait(10)


class LatencyWorker(QThread):
    """ Display Latency Graph """
    def __init__(self, latency_subplot, latency_graph_canvas):
        """ init """
        super().__init__()
        self.latency_subplot = latency_subplot
        self.latency_graph_canvas = latency_graph_canvas
        self.latency_data = []
        self.current_time = []
        self.trig = True

    def run(self):
        global latency_buffer

        while self.trig:
            try:
                # 1초 동안 수신된 latency 평균 계산
                if len(latency_buffer) > 0:
                    avg_latency = sum(latency_buffer) / len(latency_buffer)
                    latency_buffer.clear()
                else:
                    avg_latency = 0.0

                if len(self.latency_data) == 60:
                    del self.latency_data[0]
                    del self.current_time[0]

                self.latency_data.append(avg_latency)
                self.current_time.append(dt.datetime.now())

                self.latency_subplot.clear()
                self.latency_subplot.set_ylim(0, MAX_Latency_G)
                self.latency_subplot.plot(self.current_time, self.latency_data)
                self.latency_subplot.text(
                    dt.datetime.now() - dt.timedelta(seconds=0.01),
                    avg_latency + 2,
                    "{:.3f}ms".format(avg_latency)
                )
                self.latency_subplot.set_ylabel("Latency(ms)")
                self.latency_subplot.fill_between(self.current_time, self.latency_data, alpha=0.5)

                self.latency_graph_canvas.draw()
            except BaseException:
                print(traceback.format_exc())

            time.sleep(1)

    def stop(self):
        """ stop latency Graph """
        self.trig = False
        self.quit()
        self.wait(10)


class ReceiverGraphWindow(QWidget):
    """ Receive Window Configuration """
    def __init__(self, pkt_num_q):
        """ init """
        super().__init__()
        self.pkt_num_q = pkt_num_q
        style = dict(ha='center', va='center', fontsize=28, color='Gray')

        # UI declaration
        self.pdr_graph_figure = Figure()
        self.pdr_graph_figure.text(0.5, 0.5, 'PDR', style)
        self.pdr_graph_canvas = FigureCanvas(self.pdr_graph_figure)
        self.pdr_subplot = self.pdr_graph_figure.add_subplot()

        self.throughput_graph_figure = Figure()
        self.throughput_graph_figure.text(0.5, 0.5, 'Throughput', style)
        self.throughput_graph_canvas = FigureCanvas(self.throughput_graph_figure)
        self.throughput_subplot = self.throughput_graph_figure.add_subplot()

        self.latency_graph_figure = Figure()
        self.latency_graph_figure.text(0.5, 0.5, 'Latency', style)
        self.latency_graph_canvas = FigureCanvas(self.latency_graph_figure)
        self.latency_subplot = self.latency_graph_figure.add_subplot()

        self.distance_graph_figure = Figure()
        self.distance_graph_figure.text(0.5, 0.5, 'Distance', style)
        self.distance_graph_canvas = FigureCanvas(self.distance_graph_figure)
        self.distance_subplot = self.distance_graph_figure.add_subplot()

        # UI Arrangement
        self.layout = QGridLayout()
        self.layout.addWidget(self.pdr_graph_canvas, 0, 0)
        self.layout.addWidget(self.throughput_graph_canvas, 0, 1)
        self.layout.addWidget(self.latency_graph_canvas, 1, 0)
        self.layout.addWidget(self.distance_graph_canvas, 1, 1)

        # Final UI Layout Arrangement
        self.setLayout(self.layout)
        self.setWindowTitle("V2X Performance Analysis")
        icon_path = 'resource/etri.ico'  
        self.setWindowIcon(QIcon(icon_path))
        self.setFixedSize(GRAPH_WIN_SIZE_W, GRAPH_WIN_SIZE_H)
        self.move(BLANK_SPACE, BLANK_SPACE)

        # Init Graph Window
        self.init_graph()

    def init_graph(self):
        """ init graph """
        self.pdr_subplot.set_ylim(0, MAX_PDR_G)
        self.pdr_subplot.set_ylabel("Packet Delivery Ratio(%)")

        self.throughput_subplot.set_ylim(0, MAX_Throughput_G)
        self.throughput_subplot.set_ylabel("Throughput(Mbps)")

        self.latency_subplot.set_ylim(0, MAX_Latency_G)
        self.latency_subplot.set_ylabel("Latency(ms)")

        self.distance_subplot.set_ylim(0, MAX_Distance_G)
        self.distance_subplot.set_ylabel("Distance(Meters)")

        self.pdr_worker_th = PDRWorker(self.pkt_num_q, self.pdr_subplot, self.pdr_graph_canvas)
        self.pdr_worker_th.start()

        self.distance_worker_th = DistanceWorker(self.distance_subplot, self.distance_graph_canvas)
        self.distance_worker_th.start()

        self.latency_worker_th = LatencyWorker(self.latency_subplot, self.latency_graph_canvas)
        self.latency_worker_th.start()

        self.throughput_worker_th = ThroughputWorker(self.throughput_subplot, self.throughput_graph_canvas)
        self.throughput_worker_th.start()


class NavigatioWorker(QThread):
    """ Display Vehicle on the map"""
    def __init__(self, label):
        """ init """
        super().__init__()
        global webView
        global latitude
        global longitude
        global sender_latitude
        global sender_longitude

    def run(self):
        """ Vehicle position on the map"""
        global webView
        global latitude
        global longitude
        global sender_latitude
        global sender_longitude

        while True:
            try:
                script = f"receiving({latitude},{longitude},{sender_latitude},{sender_longitude})"
                webView.page().runJavaScript(script)
            except BaseException:
                print(traceback.format_exc())
            time.sleep(1)


class WeatherWorker(QThread):
    """ Display Weather Condition """
    def __init__(self, label):
        """ init """
        super().__init__()
        global weather_condition
        self.condition_label = label

        self.trig = True
        while True:
            try:
                weather_condition = 0
                self.weather_img = QPixmap(resource_path('./resource/weather_0.png'))
                self.condition_label.setPixmap(self.weather_img)
                break
            #except:
            except BaseException:
                print(traceback.format_exc())

    def run(self):
        """ Weather API Processing """
        global latitude
        global longitude
        global weather_condition

        while self.trig:
            try:
                base_date = time.strftime('%Y%m%d')
                base_time = time.strftime('%H%M')
                params = {
                    'serviceKey': WEATHER_API_SERVICE_KEY,
                    'pageNo': '1',
                    'numOfRows': '1000',
                    'dataType': 'JSON',
                    'base_date': base_date,
                    'base_time': base_time,
                    'nx': int(latitude),
                    'ny': int(longitude)
                }
            except BaseException:
                continue

            try:
                response = requests.get(WEATHER_API_URL, params=params, timeout=WEATHER_CONDITION_WAIT_TIMER)
            except BaseException:
                time.sleep(WEATHER_CONDITION_ERROR_RESEND_TIMER)
                continue
            try:
                result = str(response.content, 'utf-8')
                result = json.loads(result)

                if (result['response']['header']['resultCode'] == '00'):
                    for i in result['response']['body']['items']['item']:
                        if i.get('category') == 'PTY':
                            weather_condition = int(i.get('obsrValue'))
                            if weather_condition == 1:
                                self.weather_img = QPixmap(resource_path('./resource/weather_1.png'))
                            elif weather_condition == 2:
                                self.weather_img = QPixmap(resource_path('./resource/weather_2.png'))
                            elif weather_condition == 3:
                                self.weather_img = QPixmap(resource_path('./resource/weather_3.png'))
                            elif weather_condition == 5:
                                self.weather_img = QPixmap(resource_path('./resource/weather_5.png'))
                            elif weather_condition == 6:
                                self.weather_img = QPixmap(resource_path('./resource/weather_6.png'))
                            elif weather_condition == 7:
                                self.weather_img = QPixmap(resource_path('./resource/weather_7.png'))
                            else:
                                self.weather_img = QPixmap(resource_path('./resource/weather_0.png'))
                            while True:
                                try:
                                    self.condition_label.setPixmap(self.weather_img)
                                    break
                                except BaseException:
                                    print("Retry to change image")
                            break
                elif (result['response']['header']['resultCode'] == '03'):
                    print("No API data")
                else:
                    print(result['response']['header']['resultCode'] + ' Content Error')
            except BaseException:
                continue
            time.sleep(WEATHER_CONDITION_RESEND_TIMER)

    def stop(self):
        """ stop weather """
        self.trig = False
        self.quit()
        self.wait(100)


class RoadWorker(QThread):
    def __init__(self, label):
        """ init """
        super().__init__()
        global road_condition
        self.road_label = label

        self.trig = True
        while True:
            try:
                road_condition = 0
                self.road_img = QPixmap(resource_path('./resource/road_0.png'))
                self.road_label.setPixmap(self.road_img)
                break
            except BaseException:
                print(traceback.format_exc())

    def run(self):
        """ Road Traffic API Processing """
        global latitude
        global longitude
        global road_condition

        congestion_degree = 0
        congestion_counter = 0
        headers = {
            "appKey": ROAD_API_SERVICE_KEY
        }

        while self.trig:
            try:
                congestion_degree = 0
                congestion_counter = 0
                params = {
                    "version": "1",
                    "format": "json",
                    "reqCoordType": "WGS84GEO",
                    "resCoordType": "WGS84GEO",
                    "zoomLevel": 17,
                    "trafficType": "AUTO",
                    "centerLon": longitude,
                    "centerLat": latitude
                }

                try:
                    response = requests.get(ROAD_API_URL, headers=headers, params=params, timeout=ROAD_CONDITION_WAIT_TIMER)
                except BaseException:
                    continue
                if response.status_code == 200:
                    data = response.json()

                    for feature in data["features"]:
                        properties = feature["properties"]
                        if feature["geometry"]["type"] == "LineString":
                            for Coordinates in feature["geometry"]["coordinates"]:
                                if haversine.haversine((latitude, longitude), (Coordinates[1], Coordinates[0]), unit='m') <= 50:
                                    congestion_counter = congestion_counter + 1
                                    congestion_degree = congestion_degree + properties["congestion"]

                    if congestion_counter != 0:
                        congestion_degree = math.ceil(congestion_degree / congestion_counter)

                    if congestion_degree == 0:
                        self.road_img = QPixmap(resource_path('./resource/road_0.png'))
                    elif congestion_degree == 1:
                        self.road_img = QPixmap(resource_path('./resource/road_1.png'))
                    elif congestion_degree == 2:
                        self.road_img = QPixmap(resource_path('./resource/road_2.png'))
                    elif congestion_degree == 3:
                        self.road_img = QPixmap(resource_path('./resource/road_3.png'))
                    elif congestion_degree == 4:
                        self.road_img = QPixmap(resource_path('./resource/road_4.png'))
                    self.road_label.setPixmap(self.road_img)
                time.sleep(ROAD_CONDITION_RESEND_TIMER)
            except BaseException:
                continue

    def stop(self):
        """ stop road condition """
        self.trig = False
        self.quit()
        self.wait(100)


class NavigationWindow(QWidget):
    """ MAP + Road Condtion + Weather Condition """
    def __init__(self):
        super().__init__()
        global webView
        global latitude
        global longitude

        # UI declaration
        self.weather_label = QLabel()
        self.weather_label.setAlignment(Qt.AlignCenter)
        self.road_label = QLabel()
        self.road_label.setAlignment(Qt.AlignCenter)
        webView = QWebEngineView()
        webView.load(QUrl.fromLocalFile(resource_path(HTML_FILE_PATH)))

        # UI Arrangement
        self.layout = QGridLayout()
        self.layout.addWidget(webView, 0, 0, 2, 1)
        self.layout.addWidget(self.weather_label, 0, 1, 1, 1)
        self.layout.addWidget(self.road_label, 1, 1, 1, 1)

        # Final UI Layout Arrangement
        self.setLayout(self.layout)
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setFixedSize(NAVIGATION_WIN_SIZE_W, NAVIGATION_WIN_SIZE_H)
        self.move(int(monitor_size_width/2), int(monitor_size_height/2) + BLANK_SPACE)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.receiving)
        self.timer.start(1000)  # Cycle : 1 second

        # Weather Condition Thread
        self.weather_worker_th = WeatherWorker(self.weather_label)
        self.weather_worker_th.start()

        # Road Condition Thread
        self.road_worker_th = RoadWorker(self.road_label)
        self.road_worker_th.start()

    def receiving(self):
        """ Current Position """
        global webView
        global latitude
        global longitude
        global sender_latitude
        global sender_longitude

        script = f"receiving({latitude},{longitude},{sender_latitude},{sender_longitude})"
        try:
            webView.page().runJavaScript(script)
        except BaseException:
            print(traceback.format_exc())
