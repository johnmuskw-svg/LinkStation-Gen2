# core/state.py
from typing import Any, Dict, Optional
import threading
import copy
import time

class _State:
    def __init__(self):
        self._lock = threading.Lock()
        self._live: Optional[Dict[str, Any]] = None
        self._ts: float = 0.0

    def set_live(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._live = payload
            self._ts = time.time()

    def get_live(self) -> Dict[str, Any]:
        with self._lock:
            if self._live is None:
                # 初始空壳，结构与现有返回一致
                return {"ok": True, "data": {
                    "operator": {"name": None, "mccmnc": None},
                    "rat": None,
                    "reg": {"eps": None, "nr5g": None},
                    "cell": {"pci": None, "tac": None, "cell_id": None, "band": None, "arfcn": None},
                    "signal": {"rssi": None, "rsrp": None, "rsrq": None, "sinr": None},
                    "thermal": {"bb": None, "pa": None, "pa5g": None, "board": None},
                    "netdev": {"iface": None, "state": None, "ipv4": None, "rx_bytes": None, "tx_bytes": None},
                }, "raw": {}}
            return copy.deepcopy(self._live)

state = _State()