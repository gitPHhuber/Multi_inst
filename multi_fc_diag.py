#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-FC MSP diag: опрос всех /dev/ttyACM* и /dev/ttyUSB*,
чтение базовых и расширенных (метры) MSP-пакетов, конверсия в человекочитаемые единицы,
JSON на каждый FC (UID или DEFECT-xxxxx), поддержка запуска под sudo с фиксом прав.

Зависимости: pyserial
  sudo apt-get install -y python3-serial
  # Oracle Linux: sudo dnf install -y python3-pyserial  (или pip install pyserial)
"""
import argparse, glob, json, os, sys, time, math, struct, binascii
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import serial
except Exception:
    print("Установите pyserial: pip install pyserial", file=sys.stderr)
    sys.exit(1)

# ---------------- MSP basics ----------------
MSP_V1_START = b'$M'
DIR_TO_FC = ord('<')   # request
DIR_FROM_FC = ord('>') # response

def msp_v1_frame(payload_len, cmd, data=b''):
    # "$M" + dir '<' + size + cmd + data + csum
    size = payload_len
    head = MSP_V1_START + bytes([DIR_TO_FC, size, cmd])
    csum = 0
    csum ^= size
    csum ^= cmd
    for b in data:
        csum ^= b
    return head + data + bytes([csum & 0xFF])

def read_msp_response(ser, expect_cmd, timeout=0.3, max_payload=256):
    t0 = time.time()
    # ищем преамбулу "$M>"
    while time.time() - t0 < timeout:
        b = ser.read(1)
        if not b:
            continue
        if b == b'$':
            rest = ser.read(2)
            if rest == b'M' + bytes([DIR_FROM_FC]):
                # size, cmd, payload, csum
                sz_b = ser.read(1)
                if not sz_b:
                    continue
                size = sz_b[0]
                cmd_b = ser.read(1)
                if not cmd_b:
                    continue
                cmd = cmd_b[0]
                data = ser.read(size)
                csum = ser.read(1)
                if cmd != expect_cmd:
                    # съели чужой ответ; продолжаем искать
                    continue
                # проверим XOR
                calc = size ^ cmd
                for x in data:
                    calc ^= x
                if not csum or (csum[0] != (calc & 0xFF)):
                    return None, b'','bad_csum'
                return cmd, data, None
            else:
                # не "$M>"
                continue
    return None, b'', 'timeout'

# ---------------- MSP command IDs ----------------
MSP_API_VERSION     = 1
MSP_FC_VARIANT      = 2
MSP_FC_VERSION      = 3
MSP_BOARD_INFO      = 4
MSP_BUILD_INFO      = 5
MSP_STATUS          = 101
MSP_RAW_IMU         = 102
MSP_SERVO           = 103
MSP_MOTOR           = 104
MSP_RC              = 105
MSP_RAW_GPS         = 106
MSP_ATTITUDE        = 108
MSP_ALTITUDE        = 109
MSP_ANALOG          = 110

# Betaflight additions (per-meter telemetry)
MSP_VOLTAGE_METERS  = 128
MSP_CURRENT_METERS  = 129
MSP_BATTERY_STATE   = 130

# ---------------- helpers ----------------
def le_u8(b):  return b[0]
def le_i16(b): return struct.unpack('<h', b)[0]
def le_u16(b): return struct.unpack('<H', b)[0]
def le_i32(b): return struct.unpack('<i', b)[0]
def le_u32(b): return struct.unpack('<I', b)[0]

def hexstr(b: bytes) -> str:
    return binascii.hexlify(b).decode()

def to_deg_from_deci(v):   # 0.1 deg -> deg
    return round(v / 10.0, 1)

# ---------------- parsers (per MSP) ----------------
def parse_status(data: bytes):
    # MultiWii MSP_STATUS: cycleTime u16, i2c_errors u16, sensors u16, flags u32, currentSet u8
    out = {"raw": hexstr(data)}
    if len(data) >= 2: out["cycleTime_us"] = le_u16(data[0:2])
    if len(data) >= 4: out["i2c_errors"]  = le_u16(data[2:4])
    if len(data) >= 6: out["sensors_mask"]= le_u16(data[4:6])
    if len(data) >= 10: out["flags"]      = le_u32(data[6:10])
    # декодируем сенсоры по битам, как в MultiWii: BARO<<1 | MAG<<2 | GPS<<3 | SONAR<<4, а ACC (bit0) присутствует в более новых трактовках
    sensors = []
    m = out.get("sensors_mask", 0)
    if m & (1<<0): sensors.append("ACC")
    if m & (1<<1): sensors.append("BARO")
    if m & (1<<2): sensors.append("MAG")
    if m & (1<<3): sensors.append("GPS")
    if m & (1<<4): sensors.append("SONAR/RANGE")
    out["sensors"] = sensors
    return out  # MSP map: :contentReference[oaicite:6]{index=6}

def parse_attitude(data: bytes):
    # angx i16 (0.1deg), angy i16 (0.1deg), heading i16 (deg)
    out = {}
    if len(data) >= 2:  out["roll_deg"]  = to_deg_from_deci(le_i16(data[0:2]))
    if len(data) >= 4:  out["pitch_deg"] = to_deg_from_deci(le_i16(data[2:4]))
    if len(data) >= 6:  out["yaw_deg"]   = le_i16(data[4:6])
    return out          # :contentReference[oaicite:7]{index=7}

def parse_altitude(data: bytes):
    # EstAlt i32 (cm), vario i16 (cm/s) — в BF/INAV также часто добавляют сырой baro (i32).
    out = {"raw": hexstr(data)}
    if len(data) >= 4:
        est_cm = le_i32(data[0:4])
        out["alt_m"] = round(est_cm / 100.0, 2)
    if len(data) >= 6:
        out["vario_cmps"] = le_i16(data[4:6])
    # если есть ещё 4 байта -> raw baro cm:
    if len(data) >= 10:
        out["baro_alt_m"] = round(le_i32(data[6:10]) / 100.0, 2)
    return out          # :contentReference[oaicite:8]{index=8}

def parse_analog(data: bytes):
    # vbat u8 (0.1V), mAh u16, rssi u16 (0..1023 или %), amperage i16 (0.01A)
    out = {"raw": hexstr(data)}
    if len(data) >= 1:  out["vbat_V"]   = round(data[0] / 10.0, 2)
    if len(data) >= 3:  out["mAh_used"] = le_u16(data[1:3])
    if len(data) >= 5:  out["rssi_raw"] = le_u16(data[3:5])
    if len(data) >= 7:  out["amps_A"]   = round(le_i16(data[5:7]) / 100.0, 3)
    return out          # единицы: :contentReference[oaicite:9]{index=9}

def parse_rc(data: bytes):
    # 16 x u16 (1000..2000)
    ch = []
    for i in range(0, len(data), 2):
        if i+2 <= len(data):
            ch.append(le_u16(data[i:i+2]))
    out = {"channels": ch, "count": len(ch)}
    if ch:
        out["min"] = min(ch); out["max"] = max(ch)
    return out          # :contentReference[oaicite:10]{index=10}

def parse_motors(data: bytes):
    m = []
    for i in range(0, len(data), 2):
        if i+2 <= len(data):
            m.append(le_u16(data[i:i+2]))
    return {"motors": m} # :contentReference[oaicite:11]{index=11}

def parse_voltage_meters(data: bytes):
    # эвристический разбор BF: [count:u8] затем id:u8 + value (обычно u16)
    out = {"raw": hexstr(data), "meters": []}
    if not data:
        return out
    idx = 0
    count = data[0]
    idx = 1
    # попробуем «id:u8 + u16»
    meters = []
    try:
        while idx + 3 <= len(data):
            mid = data[idx]; val = le_u16(data[idx+1:idx+3]); idx += 3
            meters.append({"id": mid, "value_raw": val})
    except Exception:
        pass
    # конверсия в В: чаще всего 0.1В или 0.01В. Если val<=255 — принимаем 0.1В (5V/9V/12V рельсы),
    # иначе 0.01В.
    for m in meters:
        v = m["value_raw"]
        if v <= 255:
            m["voltage_V"] = round(v / 10.0, 3)
            m["unit"] = "V(0.1)"
        else:
            m["voltage_V"] = round(v / 100.0, 3)
            m["unit"] = "V(0.01)"
    out["count_declared"] = count
    out["meters"] = meters
    return out          # наличие и идея «пер-метров» подтверждены заголовками BF/ArduPilot. :contentReference[oaicite:12]{index=12}

def parse_current_meters(data: bytes):
    # формат у разных версий расходится; делаем устойчивый разбор:
    # сначала [count:u8], далее предполагаем id:u8 + amperage (либо i16 0.01А, либо i32 мА).
    out = {"raw": hexstr(data), "meters": []}
    if not data:
        return out
    idx = 0
    count = data[0]; idx = 1
    meters = []
    # попробуем вариант id:u8 + i16:
    temp = []
    i = idx
    while i + 3 <= len(data):
        mid = data[i]
        cur_raw = le_i16(data[i+1:i+3])
        temp.append((mid, cur_raw, 2))
        i += 3
    # если данных «не хватило» или явно видим 32-битные поля, попробуем id:u8 + i32:
    if len(temp) == 0 or (1 + len(temp)*3) != len(data):
        temp = []
        i = idx
        while i + 5 <= len(data):
            mid = data[i]
            cur_raw32 = le_i32(data[i+1:i+5])
            temp.append((mid, cur_raw32, 4))
            i += 5
    # конвертируем
    for mid, raw, sz in temp:
        if sz == 2:
            amps = raw / 100.0  # i16, 0.01A
            meters.append({"id": mid, "amps_A": round(amps, 3), "unit": "A(0.01)"})
        else:
            # считаем это мА (i32), сконвертируем:
            meters.append({"id": mid, "amps_A": round(raw / 1000.0, 3), "unit": "A(1mA)"})
    out["count_declared"] = count
    out["meters"] = meters
    return out          # специфика «пер-метров» подтверждена в кодовой базе MSP. :contentReference[oaicite:13]{index=13}

def parse_battery_state(data: bytes):
    # формат у BF эволюционировал; безопасно вернём сырые и попробуем распознать типичные поля:
    # распространённый вариант: connected:u8, voltage: u16 (0.01V), mAh_used:u32, amperage:u16/i16 (0.01A) и т.п.
    out = {"raw": hexstr(data)}
    # эвристика: если длина >= 7: [conn:u8][v:u16][mAh:u32]
    if len(data) >= 7:
        conn = data[0]
        v = le_u16(data[1:3]) / 100.0
        mah = le_u32(data[3:7])
        out.update({"connected": bool(conn), "voltage_V": round(v, 3), "mAh_used": mah})
        # если хватает на ток:
        if len(data) >= 9:
            amps_raw = le_i16(data[7:9])
            out["amps_A"] = round(amps_raw / 100.0, 3)
    return out          # подтверждение идентификатора и назначения — заголовки MSP. :contentReference[oaicite:14]{index=14}

# ---------------- polling per port ----------------
def handshake(ser):
    # минимальный набор для идентификации
    info = {}
    # API
    ser.write(msp_v1_frame(0, MSP_API_VERSION)); ser.flush()
    _, d, e = read_msp_response(ser, MSP_API_VERSION)
    if e is None and len(d) >= 3:
        info["api_version"] = f"{d[1]}.{d[2]}.{d[0]}"  # BF/INAV: [mspProtoVer, apiMajor, apiMinor] — порядок может меняться; сохраним как сырье тоже
        info["api_raw"] = hexstr(d)
    # FC VARIANT
    ser.write(msp_v1_frame(0, MSP_FC_VARIANT)); ser.flush()
    _, d, e = read_msp_response(ser, MSP_FC_VARIANT)
    if e is None and len(d) >= 4:
        try: info["fc_variant"] = d[:4].decode(errors='ignore')
        except: info["fc_variant_raw"] = hexstr(d)
    # FC VERSION
    ser.write(msp_v1_frame(0, MSP_FC_VERSION)); ser.flush()
    _, d, e = read_msp_response(ser, MSP_FC_VERSION)
    if e is None and len(d) >= 3:
        info["fc_version"] = f"{d[0]}.{d[1]}.{d[2]}"
    # BOARD INFO
    ser.write(msp_v1_frame(0, MSP_BOARD_INFO)); ser.flush()
    _, d, e = read_msp_response(ser, MSP_BOARD_INFO)
    if e is None and len(d) >= 4:
        info["board_id"] = d[:4].decode(errors='ignore')
    # BUILD INFO
    ser.write(msp_v1_frame(0, MSP_BUILD_INFO)); ser.flush()
    _, d, e = read_msp_response(ser, MSP_BUILD_INFO)
    if e is None and len(d) >= 11+8+7:
        build_date = d[0:11].decode(errors='ignore')
        build_time = d[11:19].decode(errors='ignore')
        git_short  = d[19:26].decode(errors='ignore')
        info["build_info"] = f"{build_date} {build_time} {git_short}"
    return info

def collect_once(ser, imu_sec=3.0, status_samples=50):
    out = {}
    # STATUS (jitter, циклы)
    st_samples = []
    for _ in range(status_samples):
        ser.write(msp_v1_frame(0, MSP_STATUS)); ser.flush()
        _, d, e = read_msp_response(ser, MSP_STATUS)
        if e is None:
            st = parse_status(d)
            st_samples.append(st.get("cycleTime_us", None))
        time.sleep(0.01)

    st_valid = [x for x in st_samples if x is not None]
    if st_valid:
        mean = sum(st_valid)/len(st_valid)
        var = sum((x-mean)**2 for x in st_valid)/len(st_valid)
        std = math.sqrt(var)
        out["loop_stats"] = {
            "samples": len(st_valid),
            "cycle_us_mean": round(mean, 2),
            "cycle_us_std": round(std, 3),
            "cycle_us_min": min(st_valid),
            "cycle_us_max": max(st_valid),
            "loop_hz_mean": round(1e6/mean, 2) if mean>0 else None,
        }

    # последний STATUS и его поля
    if st_valid:
        ser.write(msp_v1_frame(0, MSP_STATUS)); ser.flush()
        _, d, e = read_msp_response(ser, MSP_STATUS)
        if e is None:
            out["status"] = parse_status(d)

    # ATTITUDE
    ser.write(msp_v1_frame(0, MSP_ATTITUDE)); ser.flush()
    _, d, e = read_msp_response(ser, MSP_ATTITUDE)
    if e is None:
        out["attitude"] = parse_attitude(d)

    # ALTITUDE
    ser.write(msp_v1_frame(0, MSP_ALTITUDE)); ser.flush()
    _, d, e = read_msp_response(ser, MSP_ALTITUDE)
    if e is None:
        out["altitude"] = parse_altitude(d)

    # ANALOG (напряжение/ток/мАх/RSSI)
    ser.write(msp_v1_frame(0, MSP_ANALOG)); ser.flush()
    _, d, e = read_msp_response(ser, MSP_ANALOG)
    if e is None:
        out["analog"] = parse_analog(d)
        # дублируем удобные короткие поля наверх
        if "vbat_V" in out["analog"]:
            out["vbat_V"] = out["analog"]["vbat_V"]

    # RC
    ser.write(msp_v1_frame(0, MSP_RC)); ser.flush()
    _, d, e = read_msp_response(ser, MSP_RC)
    if e is None and d:
        out["rc"] = parse_rc(d)

    # MOTORS
    ser.write(msp_v1_frame(0, MSP_MOTOR)); ser.flush()
    _, d, e = read_msp_response(ser, MSP_MOTOR)
    if e is None and d:
        out["motors"] = parse_motors(d)

    # расширенные «метры» — опционально
    ser.write(msp_v1_frame(0, MSP_VOLTAGE_METERS)); ser.flush()
    _, d, e = read_msp_response(ser, MSP_VOLTAGE_METERS)
    if e is None and d:
        out["voltage_meters"] = parse_voltage_meters(d)

    ser.write(msp_v1_frame(0, MSP_CURRENT_METERS)); ser.flush()
    _, d, e = read_msp_response(ser, MSP_CURRENT_METERS)
    if e is None and d:
        out["current_meters"] = parse_current_meters(d)

    ser.write(msp_v1_frame(0, MSP_BATTERY_STATE)); ser.flush()
    _, d, e = read_msp_response(ser, MSP_BATTERY_STATE)
    if e is None and d:
        out["battery_state"] = parse_battery_state(d)

    # IMU шумы: читаем «сырые» несколько секунд (для простоты берём ATTITUDE/ANALOG в цикле)
    gyro_buf = []
    accn_buf = []
    t_end = time.time() + imu_sec
    while time.time() < t_end:
        # грубая оценка «шумов» — берём roll/pitch изменения, и норму ускорения из RAW_IMU если доступно
        ser.write(msp_v1_frame(0, MSP_RAW_IMU)); ser.flush()
        _, d, e = read_msp_response(ser, MSP_RAW_IMU, timeout=0.1)
        if e is None and len(d) >= 12:
            # accX,Y,Z i16; gyroX,Y,Z i16
            ax = le_i16(d[0:2]); ay = le_i16(d[2:4]); az = le_i16(d[4:6])
            gx = le_i16(d[6:8]); gy = le_i16(d[8:10]); gz = le_i16(d[10:12])
            # нормируем аксель: шкалы сенсоров отличаются; примем 512 LSB/G (MPU6050 ~512, см. INAV wiki)
            gnorm = math.sqrt((ax/512.0)**2 + (ay/512.0)**2 + (az/512.0)**2)
            accn_buf.append(gnorm)
            # гиры в deg/s (в INAV/BF это уже deg/s), тут оставим как есть — относительная σ
            gyro_buf.append((gx, gy, gz))
        time.sleep(0.01)
    if gyro_buf:
        xs = [x for x,_,_ in gyro_buf]
        ys = [y for _,y,_ in gyro_buf]
        zs = [z for _,_,z in gyro_buf]
        def stdev(v):
            m = sum(v)/len(v)
            return math.sqrt(sum((t-m)**2 for t in v)/len(v))
        out["imu_stats"] = {
            "samples": len(gyro_buf),
            "gyro_std": (round(stdev(xs),3), round(stdev(ys),3), round(stdev(zs),3)),
            "acc_norm_std": round(stdev(accn_buf),3) if accn_buf else None,
        } # шкалы описаны тут. :contentReference[oaicite:15]{index=15}
    return out

def chown_to_sudo_user(path):
    uid = os.getuid()
    if uid == 0 and "SUDO_UID" in os.environ and "SUDO_GID" in os.environ:
        try:
            os.chown(path, int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"]))
        except Exception:
            pass
    try:
        os.chmod(path, 0o664)
    except Exception:
        pass

def diag_port(port, baud, args):
    t0 = time.time()
    res = {
        "port": port,
        "baud": baud,
        "ok": False,
        "reasons": [],
    }
    try:
        ser = serial.Serial(port, baudrate=baud, timeout=0.3)
        # сброс линий, чтобы «разбудить» VCP
        try:
            ser.dtr = False; ser.rts = False; time.sleep(0.05)
            ser.dtr = True;  ser.rts = True;  time.sleep(0.05)
        except Exception:
            pass

        # базовая идентификация
        base = handshake(ser)
        res.update(base)

        # UID — лучше через MSP_BOARD_INFO (часто нет), поэтому дополнительно попробуем MSP_NAME(10) нет, UID нет в MSPv1 стандартно.
        # Многие BF таргеты публикуют UID через CLI/OSD, но тут оставим что есть; если UID нет — сделаем DEFECT.
        # Встречается UID из USB-дескриптора — pyserial не даёт; поэтому оставим как есть.
        uid = base.get("uid") or base.get("board_uid")
        if uid:
            res["uid"] = uid

        # сбор метрик
        data = collect_once(ser, imu_sec=args.imu_sec, status_samples=args.status_samples)
        res.update(data)

        # простые проверки
        att = res.get("attitude", {})
        if not args.ignore_tilt:
            # не лежит ли на боку (> 5° по норме, но у вас USB-питание — можно ослабить)
            roll = abs(att.get("roll_deg", 0))
            pitch = abs(att.get("pitch_deg", 0))
            if max(roll, pitch) > args.max_tilt:
                res["reasons"].append(f"tilt>{args.max_tilt}deg (roll={att.get('roll_deg')},{att.get('pitch_deg')})")

        imu = res.get("imu_stats", {})
        gx, gy, gz = (0,0,0)
        if imu:
            gs = imu.get("gyro_std", (0,0,0))
            gx, gy, gz = gs
            if max(abs(x) for x in (gx, gy, gz)) > args.max_gyro_std:
                res["reasons"].append(f"gyro_std>{args.max_gyro_std} ({gx},{gy},{gz})")

        # bias оценка (для простоты — последние RAW_IMU средние)
        # (быстрый набросок: если есть MOTORS=1000 и лежит неподвижно, среднее по гироскопу ≈ bias)
        # — опционально, не падаем если нет
        # …

        st = res.get("status", {})
        if st and st.get("i2c_errors", 0) > args.max_i2c_errors:
            res["reasons"].append(f"i2c_errors>{args.max_i2c_errors} ({st.get('i2c_errors')})")

        if "loop_stats" in res:
            jitter = res["loop_stats"]["cycle_us_max"] - res["loop_stats"]["cycle_us_min"]
            if jitter > args.max_cyc_jitter:
                res["reasons"].append(f"cycle_jitter>{args.max_cyc_jitter}us ({jitter})")

        res["ok"] = (len(res["reasons"]) == 0)
        ser.close()
    except Exception as e:
        res["error"] = f"{type(e).__name__}: {e}"

    res["duration_s"] = round(time.time() - t0, 3)

    # имя файла
    outdir = args.out
    os.makedirs(outdir, exist_ok=True)
    uid = res.get("uid")
    if uid:
        fname = f"{uid}.json"
    else:
        # DEFECT-xxxxx
        i = 1
        while True:
            candidate = os.path.join(outdir, f"DEFECT-{i:05d}.json")
            if not os.path.exists(candidate):
                fname = os.path.basename(candidate)
                break
            i += 1
    fpath = os.path.join(outdir, fname)

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    chown_to_sudo_user(fpath)

    # краткая строка сводки (для --jsonl тоже пригодится)
    short = {
        "port": port,
        "ok": res["ok"],
        "uid": res.get("uid", "—"),
        "fc": res.get("fc_version"),
        "board": res.get("board_id"),
        "file": fpath,
    }
    if res.get("reasons"):
        short["reasons"] = res["reasons"]
    return res, short

def list_candidate_ports():
    ports = sorted(set(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")))
    return ports

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="./out", help="каталог для JSON")
    ap.add_argument("--workers", type=int, default=4, help="число потоков")
    ap.add_argument("--baud", type=int, default=1_000_000, help="скорость MSP (обычно 115200 или 1000000)")
    ap.add_argument("--imu-sec", type=float, default=3.0, help="секунд сбора для IMU статистики")
    ap.add_argument("--status-samples", type=int, default=50, help="сколько раз читать MSP_STATUS")
    ap.add_argument("--jsonl", action="store_true", help="печать кратких строк JSONL в stdout")
    # пороги
    ap.add_argument("--max-gyro-std", type=float, default=6.0)
    ap.add_argument("--max-cyc-jitter", type=int, default=10)
    ap.add_argument("--max-i2c-errors", type=int, default=0)
    ap.add_argument("--max-tilt", type=float, default=5.0)
    ap.add_argument("--ignore-tilt", action="store_true")
    args = ap.parse_args()

    ports = list_candidate_ports()
    if not ports:
        print("портов /dev/ttyACM* или /dev/ttyUSB* не найдено", file=sys.stderr)
        sys.exit(2)

    summaries = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(diag_port, p, args.baud, args): p for p in ports}
        for fut in as_completed(futs):
            res, short = fut.result()
            if args.jsonl:
                print(json.dumps(short, ensure_ascii=False))
            else:
                print(f"[{short['port']}] ok={short['ok']} uid={short['uid']} file={short['file']}")
            summaries.append(short)

    # общий сводный файл (опционально)
    summary_path = os.path.join(args.out, "_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summaries, f, ensure_ascii=False, indent=2)
    chown_to_sudo_user(summary_path)

if __name__ == "__main__":
    main()

