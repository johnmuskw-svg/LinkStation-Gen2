# core/poller.py
import threading, time, re
from typing import Dict, List, Any, Optional
from core.serial_port import serial_at
from core.state import state

_POLL_INTERVAL = 1.0  # 秒

def _send(cmd: str, deadline: float = 1.2) -> List[str]:
    return serial_at.send(cmd, deadline=deadline)

def _parse_cereg(lines: List[str]) -> Optional[int]:
    for ln in lines:
        m = re.search(r"\+CEREG:\s*\d\s*,\s*(\d+)", ln)
        if m: return int(m.group(1))
    return None

def _parse_c5greg(lines: List[str]) -> Optional[int]:
    for ln in lines:
        m = re.search(r"\+C5GREG:\s*\d\s*,\s*(\d+)", ln)
        if m: return int(m.group(1))
    return None

def _parse_cops(lines: List[str]) -> Optional[str]:
    # +COPS: 0,0,"CHINA MOBILE",13
    for ln in lines:
        m = re.search(r'\+COPS:\s*\d+,\s*\d+,\s*"([^"]+)"', ln)
        if m: return m.group(1)
    return None

def _parse_qtemp(lines: List[str]) -> Dict[str, Optional[int]]:
    def pick(name: str) -> Optional[int]:
        for ln in lines:
            if name in ln:
                m = re.search(r'"%s"\s*,\s*"(-?\d+)"' % re.escape(name), ln)
                if m: return int(m.group(1))
        return None
    return {
        "bb":    pick("soc-thermal"),
        "pa":    pick("pa-thermal"),
        "pa5g":  pick("pa5g-thermal"),
        "board": pick("board-thermal"),
    }

_running = False
_thread: Optional[threading.Thread] = None

def _loop():
    global _running
    while _running:
        try:
            qeng   = _send('AT+QENG="servingcell"', 1.2)
            cereg  = _send('AT+CEREG?', 0.8)
            c5greg = _send('AT+C5GREG?', 0.8)
            cops   = _send('AT+COPS?', 0.8)
            qtemp  = _send('AT+QTEMP', 1.2)

            payload: Dict[str, Any] = {
                "ok": True,
                "data": {
                    "operator": {"name": _parse_cops(cops), "mccmnc": None},
                    "rat": None,  # 由前端/后续解析决定
                    "reg": {"eps": _parse_cereg(cereg), "nr5g": _parse_c5greg(c5greg)},
                    "cell": {"pci": None, "tac": None, "cell_id": None, "band": None, "arfcn": None},
                    "signal": {"rssi": None, "rsrp": None, "rsrq": None, "sinr": None},
                    "thermal": _parse_qtemp(qtemp),
                    "netdev": {"iface": None, "state": None, "ipv4": None, "rx_bytes": None, "tx_bytes": None},
                },
                "raw": {
                    'AT+QENG="servingcell"': qeng,
                    "AT+CEREG?": cereg,
                    "AT+C5GREG?": c5greg,
                    "AT+COPS?": cops,
                    "AT+QTEMP": qtemp,
                }
            }
            state.set_live(payload)
        except Exception:
            # 出错也不影响下一轮
            pass
        time.sleep(_POLL_INTERVAL)

def start_poller():
    global _running, _thread
    if _running: return
    _running = True
    _thread = threading.Thread(target=_loop, name="live-poller", daemon=True)
    _thread.start()

def stop_poller():
    global _running, _thread
    _running = False
    if _thread and _thread.is_alive():
        _thread.join(timeout=1.0)
    _thread = None