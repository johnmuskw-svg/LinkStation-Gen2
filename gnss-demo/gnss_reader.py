#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
import serial
import pynmea2

DEVICE_DEFAULT = "/dev/ttyAMA0"
BAUD_DEFAULT = 115200
JSON_PATH = "/tmp/linkstation-gnss-live.json"

# 模块级变量：保存上一轮 --once 模式的卫星数据（用于补丁）
_last_nav_satellites: Optional[Dict] = None


class NavState:
    """导航状态管理器，维护结构化的导航信息"""
    
    def __init__(self):
        self.fix: Dict = {
            "utc": None,          # ISO8601 UTC 时间字符串（来自 GGA/RMC）
            "date": None,         # 日期字符串 YYYY-MM-DD（来自 RMC）
            "lat": None,          # 纬度（度，来自 GGA/RMC）
            "lon": None,          # 经度（度，来自 GGA/RMC）
            "alt": None,          # 海拔（米，来自 GGA）
            "fix_quality": None,  # 定位质量 0=Invalid, 1=GPS, 2=DGPS...（来自 GGA）
            "nav_status": None,   # 导航状态 A=Valid, V=Invalid（来自 RMC）
        }
        self.dop: Dict = {
            "pdop": None,         # 位置精度因子（来自 GSA）
            "hdop": None,         # 水平精度因子（来自 GGA/GSA）
            "vdop": None,         # 垂直精度因子（来自 GSA）
        }
        self.motion: Dict = {
            "speed_kmh": None,    # 速度（公里/小时，来自 RMC）
            "speed_knots": None,  # 速度（节，来自 RMC）
            "course_deg": None,   # 航向角（度，来自 RMC）
        }
        self.satellites: Dict = {
            "in_use": None,       # 当前用于解算的卫星数量（来自 GSA）
            "in_view": None,      # 当前可见卫星数量（来自 GSV 汇总）
            "list": [],           # 卫星详细信息列表（来自 GSV）
        }
        self.raw: Dict = {
            "nmea": [],           # 最近用到的原始 NMEA 行（可选）
        }
        # 内部状态：用于跟踪 GSA 中的在用卫星
        self._used_prns: Set[int] = set()
        # 内部状态：GSV 卫星信息缓存（按 PRN 索引）
        self._sat_cache: Dict[int, Dict] = {}
    
    def to_dict(self) -> Dict:
        """转换为字典格式，用于 JSON 输出"""
        # 判断卫星数据是否有效（有可见卫星）
        satellites_valid = (self.satellites.get("in_view") or 0) > 0
        
        return {
            "fix": self.fix,
            "dop": self.dop,
            "motion": self.motion,
            "satellites": {
                "in_use": self.satellites["in_use"],
                "in_view": self.satellites["in_view"],
                "list": self.satellites["list"],
                "valid": satellites_valid,
            },
            "raw": self.raw,
        }
    
    def is_valid(self) -> bool:
        """检查是否有基本的有效定位信息"""
        return (
            self.fix.get("lat") is not None and
            self.fix.get("lon") is not None and
            self.fix.get("fix_quality") is not None and
            self.fix["fix_quality"] > 0
        )
    
    def _update_satellite_list(self):
        """根据缓存更新卫星列表，标记哪些在使用"""
        sat_list = []
        for prn, sat_info in self._sat_cache.items():
            sat_info["used"] = prn in self._used_prns
            sat_list.append(sat_info)
        # 按 PRN 排序
        sat_list.sort(key=lambda x: x.get("prn", 0))
        self.satellites["list"] = sat_list
        self.satellites["in_view"] = len(sat_list)


def get_talker_system(talker: str) -> str:
    """根据 talker ID 返回系统名称"""
    mapping = {
        "GP": "GPS",
        "GL": "GLONASS",
        "GA": "Galileo",
        "GB": "BDS",
        "GQ": "QZSS",
        "GN": "Multi",  # GN 表示多系统组合
    }
    return mapping.get(talker, "Unknown")


def parse_nmea_line(line: str, nav_state: NavState) -> None:
    """
    解析单行 NMEA，更新 NavState
    支持：GGA, RMC, GSA, GSV
    """
    try:
        msg = pynmea2.parse(line)
    except Exception:
        # 解析失败直接跳过
        return
    
    # 获取 talker ID（GP/GL/GA/GB/GQ/GN）
    talker = ""
    if hasattr(msg, "talker"):
        talker = msg.talker
    elif hasattr(msg, "sentence_type"):
        # 从 sentence_type 提取（如 "GPGGA" -> "GP"）
        st = msg.sentence_type
        if len(st) >= 2:
            talker = st[:2]
    
    # 保存原始 NMEA 行（可选，限制数量）
    if len(nav_state.raw["nmea"]) < 10:
        nav_state.raw["nmea"].append(line.strip())
    
    # GGA：位置 + 海拔 + 卫星数 + 精度（来自 GGA）
    if isinstance(msg, pynmea2.types.talker.GGA):
        # UTC 时间
        if msg.timestamp:
            now = datetime.now(timezone.utc)
            dt = datetime.combine(now.date(), msg.timestamp, tzinfo=timezone.utc)
            nav_state.fix["utc"] = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            nav_state.fix["date"] = dt.strftime("%Y-%m-%d")
        
        # 位置
        if msg.latitude is not None and msg.longitude is not None:
            nav_state.fix["lat"] = float(msg.latitude)
            nav_state.fix["lon"] = float(msg.longitude)
        
        # 海拔
        if msg.altitude is not None:
            try:
                nav_state.fix["alt"] = float(msg.altitude)
            except (TypeError, ValueError):
                pass
        
        # 定位质量
        if msg.gps_qual is not None:
            try:
                nav_state.fix["fix_quality"] = int(msg.gps_qual)
            except (TypeError, ValueError):
                pass
        
        # 卫星数量（GGA 中的可见卫星数）
        if msg.num_sats is not None:
            try:
                # 注意：GGA 的 num_sats 是可见卫星数，不是 in_use
                pass  # 这里不更新 in_use，等 GSA 来更新
            except (TypeError, ValueError):
                pass
        
        # HDOP
        if msg.horizontal_dil is not None:
            try:
                nav_state.dop["hdop"] = float(msg.horizontal_dil)
            except (TypeError, ValueError):
                pass
    
    # RMC：推荐最小导航信息（来自 RMC）
    elif isinstance(msg, pynmea2.types.talker.RMC):
        # UTC 时间和日期
        if msg.datestamp and msg.timestamp:
            dt = datetime.combine(msg.datestamp, msg.timestamp, tzinfo=timezone.utc)
            nav_state.fix["utc"] = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            nav_state.fix["date"] = dt.strftime("%Y-%m-%d")
        
        # 位置
        if msg.latitude is not None and msg.longitude is not None:
            nav_state.fix["lat"] = float(msg.latitude)
            nav_state.fix["lon"] = float(msg.longitude)
        
        # 导航状态
        if msg.status:
            nav_state.fix["nav_status"] = msg.status  # 'A' 或 'V'
        
        # 速度：节 => km/h
        if msg.spd_over_grnd is not None:
            try:
                spd_kn = float(msg.spd_over_grnd)
                nav_state.motion["speed_knots"] = spd_kn
                nav_state.motion["speed_kmh"] = spd_kn * 1.852
            except (TypeError, ValueError):
                pass
        
        # 航向角
        if msg.true_course is not None:
            try:
                nav_state.motion["course_deg"] = float(msg.true_course)
            except (TypeError, ValueError):
                pass
    
    # GSA：DOP 和卫星 ID（来自 GSA）
    # 注意：需要处理所有 talker 的 GSA（GPGSA / BDGSA / GLGSA / GAGSA / QZGSA / GNGSA 等）
    elif isinstance(msg, pynmea2.types.talker.GSA):
        # DOP 值（使用最新的 GSA 消息中的 DOP 值）
        if msg.pdop is not None:
            try:
                nav_state.dop["pdop"] = float(msg.pdop)
            except (TypeError, ValueError):
                pass
        
        if msg.hdop is not None:
            try:
                nav_state.dop["hdop"] = float(msg.hdop)
            except (TypeError, ValueError):
                pass

        if msg.vdop is not None:
            try:
                nav_state.dop["vdop"] = float(msg.vdop)
            except (TypeError, ValueError):
                pass
        
        # 累积在用卫星 PRN 列表（不清空，累积所有 GSA 消息中的卫星号）
        # GSA 消息中的卫星 ID 字段：sv_id01 到 sv_id12
        for i in range(1, 13):
            sv_attr = f"sv_id{i:02d}"
            if hasattr(msg, sv_attr):
                sv_id = getattr(msg, sv_attr, None)
                if sv_id is not None:
                    try:
                        # 尝试转换为整数
                        sv_id_str = str(sv_id).strip()
                        if sv_id_str and sv_id_str.isdigit():
                            nav_state._used_prns.add(int(sv_id_str))
                    except (TypeError, ValueError):
                        pass
        
        # 更新 in_use 数量（累积所有 GSA 中的卫星）
        nav_state.satellites["in_use"] = len(nav_state._used_prns)
        
        # 更新卫星列表的 used 标记
        nav_state._update_satellite_list()
        
    # GSV：卫星可见信息（来自 GSV）
    elif isinstance(msg, pynmea2.types.talker.GSV):
        # GSV 可能分多条发送，每条包含最多 4 颗卫星的信息
        # 获取当前消息中的卫星数据
        if hasattr(msg, "sv_prn_num_1") and msg.sv_prn_num_1:
            _parse_gsv_satellite(msg, 1, talker, nav_state)
        if hasattr(msg, "sv_prn_num_2") and msg.sv_prn_num_2:
            _parse_gsv_satellite(msg, 2, talker, nav_state)
        if hasattr(msg, "sv_prn_num_3") and msg.sv_prn_num_3:
            _parse_gsv_satellite(msg, 3, talker, nav_state)
        if hasattr(msg, "sv_prn_num_4") and msg.sv_prn_num_4:
            _parse_gsv_satellite(msg, 4, talker, nav_state)
        
        # 更新可见卫星数量
        nav_state._update_satellite_list()


def _parse_gsv_satellite(msg: pynmea2.types.talker.GSV, idx: int, talker: str, nav_state: NavState):
    """解析 GSV 消息中的单颗卫星信息"""
    try:
        # 获取 PRN
        prn_attr = f"sv_prn_num_{idx}"
        prn = getattr(msg, prn_attr, None)
        if not prn:
            return
        
        prn = int(prn)
        
        # 获取仰角
        elev_attr = f"elevation_deg_{idx}"
        elev = getattr(msg, elev_attr, None)
        elev = int(elev) if elev is not None else None
        
        # 获取方位角
        azim_attr = f"azimuth_{idx}"
        azim = getattr(msg, azim_attr, None)
        azim = int(azim) if azim is not None else None
        
        # 获取信噪比
        snr_attr = f"snr_{idx}"
        snr = getattr(msg, snr_attr, None)
        snr = int(snr) if snr is not None else None
        
        # 确定系统
        system = get_talker_system(talker)
        
        # 更新缓存
        nav_state._sat_cache[prn] = {
            "prn": prn,
            "system": system,
            "elev": elev,
            "azim": azim,
            "snr": snr,
            "used": prn in nav_state._used_prns,
        }
    except (TypeError, ValueError, AttributeError):
        pass


def configure_gnss_rate(ser: serial.Serial, rate_hz: int = 5) -> bool:
    """
    配置 GNSS 模块的 NMEA 输出频率
    
    对于 Quectel LC29H/LC79H 系列，使用 AT+QGPSCFG="nmeasrc",<rate>
    rate: 1, 5, 10 等（Hz）
    
    返回: True 如果配置成功，False 如果失败
    """
    try:
        # 发送 AT 命令配置输出频率
        # 对于 Quectel LC29H/LC79H: AT+QGPSCFG="nmeasrc",<rate>
        cmd = f'AT+QGPSCFG="nmeasrc",{rate_hz}\r\n'
        ser.write(cmd.encode('ascii'))
        time.sleep(0.2)  # 等待响应
        
        # 读取响应（非阻塞，只读取可用数据）
        response = b""
        start_time = time.time()
        while time.time() - start_time < 0.5:  # 最多等待 0.5 秒
            if ser.in_waiting > 0:
                response += ser.read(ser.in_waiting)
                if b"OK" in response or b"ERROR" in response:
                    break
            time.sleep(0.05)
        
        # 检查是否成功
        if b"OK" in response:
            return True
        else:
            # 如果设备不支持 AT 命令（可能是纯 GNSS 接收器），静默失败
            # 这种情况下，设备可能已经配置好或者需要其他方式配置
            return False
    except Exception:
        # 配置失败不影响主流程，静默返回 False
        return False


def save_state(nav_state: NavState) -> None:
    """把最新的状态写到 JSON 文件"""
    try:
        with open(JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(nav_state.to_dict(), f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # 静默失败，不影响主流程


def run(device: str, baud: int, once: bool = False, rate_hz: int = 5) -> None:
    """主运行函数
    
    Args:
        device: 串口设备路径
        baud: 波特率
        once: 是否只读取一次后退出
        rate_hz: GNSS 输出频率（Hz），默认 5Hz
    """
    global _last_nav_satellites
    
    if not once:
        print(f"[GNSS] Opening {device} @ {baud} ...", file=sys.stderr)
    
    try:
        ser = serial.Serial(device, baudrate=baud, timeout=1)
    except serial.SerialException as e:
        if not once:
            print(f"[ERROR] Failed to open serial port: {e}", file=sys.stderr)
            print(f"[INFO] Please check:", file=sys.stderr)
            print(f"  1. Device {device} exists and is accessible", file=sys.stderr)
            print(f"  2. No other process is using the port", file=sys.stderr)
            print(f"  3. GNSS device is properly connected", file=sys.stderr)
        return
    
    # 配置 GNSS 输出频率为 5Hz
    if not once:
        print(f"[GNSS] Configuring output rate to {rate_hz}Hz...", file=sys.stderr)
    if configure_gnss_rate(ser, rate_hz):
        if not once:
            print(f"[GNSS] Successfully configured to {rate_hz}Hz", file=sys.stderr)
    else:
        if not once:
            print(f"[GNSS] Rate configuration skipped (device may not support AT commands)", file=sys.stderr)
    
    nav_state = NavState()
    error_count = 0
    max_errors = 10
    lines_processed = 0
    
    # --once 模式：使用总超时时间，持续读取直到超时
    if once:
        # 从环境变量读取超时时间，默认 1.2 秒（5Hz 时，1.2秒可以收到约6帧数据，足够收集完整信息）
        read_timeout = float(os.getenv("GNSS_ONCE_TIMEOUT", "1.2"))
        start_time = time.monotonic()
        gsv_received = False  # 标记是否收到过 GSV 消息
        
        try:
            while True:
                # 检查是否超时
                elapsed = time.monotonic() - start_time
                if elapsed >= read_timeout:
                    break
                
                try:
                    # 设置剩余超时时间
                    remaining_timeout = read_timeout - elapsed
                    if remaining_timeout > 0:
                        ser.timeout = min(remaining_timeout, 1.0)
                    line_bytes = ser.readline()
                except serial.SerialException as e:
                    error_count += 1
                    if error_count >= max_errors:
                        break
                    time.sleep(0.05)
                    continue
                
                error_count = 0
                
                if not line_bytes:
                    continue
                
                try:
                    line = line_bytes.decode("ascii", errors="ignore").strip()
                except Exception:
                    continue
                
                if not line.startswith("$"):
                    continue
                
                # 检查是否是 GSV 消息
                if "$GPGSV" in line or "$GLGSV" in line or "$GBGSV" in line or "$GAGSV" in line or "$GQGSV" in line or "$GNGSV" in line:
                    gsv_received = True
                
                parse_nmea_line(line, nav_state)
                lines_processed += 1
            
            # 超时后处理：在输出前确保更新所有卫星的 used 标记和 in_use 计数
            nav_state.satellites["in_use"] = len(nav_state._used_prns)
            nav_state._update_satellite_list()
            
            # 如果这轮没收到 GSV，使用上一轮的卫星数据
            if not gsv_received and _last_nav_satellites is not None:
                nav_state.satellites["in_view"] = _last_nav_satellites.get("in_view")
                nav_state.satellites["list"] = _last_nav_satellites.get("list", [])
                # 但保留当前计算的 in_use（基于 GSA 消息）
                # 同时需要更新上一轮卫星列表中的 used 标记
                if nav_state.satellites["list"]:
                    for sat in nav_state.satellites["list"]:
                        sat["used"] = sat.get("prn") in nav_state._used_prns
            else:
                # 有 GSV 数据，确保 in_use 正确
                nav_state.satellites["in_use"] = len(nav_state._used_prns)
            
            # 输出结果
            result_dict = nav_state.to_dict()
            
            # 如果这轮有有效的卫星数据，更新缓存
            sats = result_dict.get("satellites", {})
            if sats.get("valid", False) and sats.get("in_view", 0) > 0:
                _last_nav_satellites = {
                    "in_use": sats.get("in_use"),
                    "in_view": sats.get("in_view"),
                    "list": sats.get("list", []),
                }
            
            json_str = json.dumps(result_dict, ensure_ascii=False)
            print(json_str, flush=True)
        
        except KeyboardInterrupt:
            pass
        finally:
            ser.close()
        return
    
    # 持续模式：原有逻辑
    try:
        while True:
            try:
                line_bytes = ser.readline()
            except serial.SerialException as e:
                error_count += 1
                if error_count <= max_errors:
                    print(f"[WARN] Serial read error ({error_count}/{max_errors}): {e}", file=sys.stderr)
                if error_count >= max_errors:
                    print(f"[ERROR] Too many serial errors, exiting...", file=sys.stderr)
                break
                time.sleep(0.5)
                continue
            
            error_count = 0
            
            if not line_bytes:
                continue
            
            try:
                line = line_bytes.decode("ascii", errors="ignore").strip()
            except Exception:
                continue
            
            if not line.startswith("$"):
                continue
            
            parse_nmea_line(line, nav_state)
            lines_processed += 1
            
            # 保存状态到文件
            save_state(nav_state)
            
            # 持续模式：当有有效位置时，打印精简信息
            if nav_state.is_valid():
                info = {
                    "utc": nav_state.fix.get("utc"),
                    "lat": round(nav_state.fix["lat"], 7) if nav_state.fix["lat"] else None,
                    "lon": round(nav_state.fix["lon"], 7) if nav_state.fix["lon"] else None,
                    "alt": nav_state.fix.get("alt"),
                    "sat": nav_state.satellites.get("in_use"),
                    "hdop": nav_state.dop.get("hdop"),
                    "spd_kmh": round(nav_state.motion.get("speed_kmh", 0.0), 2) if nav_state.motion.get("speed_kmh") else None,
                }
                print(json.dumps(info, ensure_ascii=False), flush=True)
    
    except KeyboardInterrupt:
        if not once:
            print("\n[INFO] Interrupted by user", file=sys.stderr)
    finally:
        ser.close()
        if not once:
            print("[GNSS] Serial port closed", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="LinkStation GNSS reader")
    parser.add_argument("--device", default=DEVICE_DEFAULT, help="Serial device path")
    parser.add_argument("--baud", type=int, default=BAUD_DEFAULT, help="Baud rate")
    parser.add_argument(
        "--once", action="store_true",
        help="Read until first valid fix then output JSON and exit"
    )
    parser.add_argument(
        "--rate", type=int, default=5,
        help="GNSS output rate in Hz (default: 5)"
    )
    args = parser.parse_args()
    run(device=args.device, baud=args.baud, once=args.once, rate_hz=args.rate)


if __name__ == "__main__":
    main()
