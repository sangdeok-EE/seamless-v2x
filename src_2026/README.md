# V2X Sender/Receiver (Reed-Solomon 기반 통합합메시지 전송)

## 1. 개요
- 본 소스는 **V2X 환경에서 영상 데이터 + 안전 메시지(BSM, SDSM 등)**를 함께 송수신하는 PyQt5 기반 GUI 프로그램입니다.
- 안전 메시지는 **56바이트 고정 페이로드(K=8, Symbol=7)** 기준으로 구성되며, Reed-Solomon 방식(적응형 포함)으로 인코딩/디코딩됩니다.
- 송신 측은 CSV 시나리오(`scenario_v2x_56.csv`)를 순차 읽기하여 메시지와 환경 PDR을 반영하고, 수신 측은 복원된 메시지를 UI/로그에 표시합니다.

## 2. 주요 파일
- `select_window.py`
  - 시작 진입점(메인 런처)
  - Sender/Receiver 창 선택
- `sender_window.py`
  - 영상 캡처(카메라/파일) + 패킷 분할 전송
  - 안전 메시지 RS 인코딩 및 삽입
  - Gilbert-Elliot 채널 모델 기반 손실 시뮬레이션
- `receiver_window.py`
  - 패킷 수신/파싱, 영상 복원
  - 안전 메시지 복원(RS 디코딩 포함)
  - PDR/Throughput/Latency/Distance 그래프, 지도/기상/도로 정보 UI
  - 헤더 로그/긴급메시지 로그 저장
- `packet_header_struct.py`
  - TLVC/SSOV 패킷 구조 정의(Scapy Packet)
- `scenario_v2x_56.csv`
  - 송신 시나리오(메시지, 환경 PDR 등)
- `resource/*`
  - 아이콘/지도 HTML/상태 이미지 리소스

## 3. 동작 구조 요약
- 송신
  - 프레임(300x300)을 바이트로 변환 후 최대 크기 기준으로 세그먼트 전송
  - 안전 메시지는 CSV에서 읽어 56바이트로 패딩 후 RS 인코딩(현재 기본 모드: `ADAPTIVE_RS`)
  - 영상 페이로드 뒤에 `BSM:` 구분자로 메시지를 붙이거나, 8바이트 헤더 필드를 통해 조각 전송
- 수신
  - 수신 패킷에서 SSOV/영상/메시지 구간 파싱
  - `BSM:` 직접 문자열 또는 RS 조각(헤더 1B + 데이터 7B) 방식 처리
  - 복원 성공 시 긴급메시지 UI 표시 및 CSV 로그 기록
  - 그래프 창/지도 창에서 성능 및 상황 정보 시각화

## 4. 실행 환경
- OS: Windows 권장 (`cv2.CAP_DSHOW`, `pygrabber` 사용)
- Python: 3.9 ~ 3.11 권장
- 네트워크: TCP 대상 장비(OBU/중계 장치)와 통신 가능한 환경
- 기본 포트: `12345`

## 5. 의존성 설치
아래 패키지가 필요합니다.

- `PyQt5`
- `PyQtWebEngine`
- `opencv-python`
- `numpy`
- `psutil`
- `scapy`
- `requests`
- `haversine`
- `screeninfo`
- `matplotlib`
- `ntplib`
- `pygrabber`
- `fastcrc`

설치 예시:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install PyQt5 PyQtWebEngine opencv-python numpy psutil scapy requests haversine screeninfo matplotlib ntplib pygrabber fastcrc
```

## 6. 구동 방법
### 6.1 공통 시작
```powershell
python select_window.py
```

실행 후 `Sender Window` 또는 `Receiver Window`를 선택합니다.

### 6.2 Receiver 실행
1. `Receiver Window` 선택
2. 네트워크 인터페이스와 대상 IP 입력
3. `Receive` 버튼으로 수신 시작
4. `Pause` 버튼으로 중지

실행 시 비디오 창과 함께 그래프 창(PDR/Throughput/Latency/Distance), 내비게이션 창(지도/기상/도로)이 함께 동작합니다.

### 6.3 Sender 실행
1. `Sender Window` 선택
2. 네트워크 인터페이스와 대상 IP 입력
3. 입력 소스 선택
   - 카메라
   - `Saved Video` 선택 후 파일 경로 입력
4. `START CSV AUTOMATION` 클릭

송신은 `scenario_v2x_56.csv`를 순차 소비하며, 마지막 행까지 처리하면 자동 종료 흐름으로 넘어갑니다.

## 7. 시나리오 파일 형식
- 파일: `scenario_v2x_56.csv`
- 예시 컬럼:
  - `Index`
  - `Payload` (안전 메시지 원문)
  - `Note`
  - `Env_PDR` (환경 PDR, 적응형 RS 파라미터 결정에 사용)
  - `Env_AoI`

`Payload`는 내부에서 56바이트 프레임에 맞게 잘리거나 패딩됩니다.

## 8. 로그/산출물
- 수신 로그는 실행 날짜 폴더(`YYYY.MM.DD`) 아래 생성됩니다.
- 주요 로그:
  - `Urgent_Log_*.csv` (긴급메시지 로그)
  - `ETRI_OBU_01(RX)_*.csv` (헤더/성능 로그)

## 9. 참고 사항
- 코드 상 기본 연결 IP:
  - 송신: `192.168.1.11`
  - 수신: `10.254.52.18`
  - 실제 실행 시 UI 입력값으로 변경 가능합니다.
- `receiver_window.py`는 단독 실행 진입점(`if __name__ == "__main__":`)이 없으므로, `select_window.py`에서 실행하는 방식을 권장합니다.
- 외부 API(기상/도로)와 지도 표시를 사용하므로 네트워크 상태에 따라 일부 UI는 갱신 지연이 발생할 수 있습니다.

## 10. 라이선스
- 소스 헤더 기준: **GNU General Public License v3.0 or later**
