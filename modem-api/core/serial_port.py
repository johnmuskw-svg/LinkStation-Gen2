# core/serial_port.py
import glob
import logging
import os
import threading
import time
from typing import List, Optional

import serial

# 如果你已在 config.py 里有 SERIAL_PORT / BAUDRATE，就沿用：
from config import SERIAL_PORT, BAUDRATE

# 读写参数：尽量小的块 + 见 OK/ERROR 立即返回
_READ_CHUNK = 1024             # 每次最多读 1KB
_READ_TIMEOUT = 0.10           # 串口底层 read 超时（秒）
_WRITE_TIMEOUT = 0.50          # 写超时（秒）
_DEFAULT_DEADLINE = 1.20       # 单条 AT 最大等待时间（秒），通常 < 300ms 即返回

_OK_TOKENS = (b"\r\nOK\r\n", b"\nOK\r\n", b"\r\nOK\n")
_ERR_TOKENS = (b"\r\nERROR", b"\nERROR", b"+CME ERROR", b"+CMS ERROR")

logger = logging.getLogger(__name__)

def _done(buf: bytes) -> bool:
    if any(tok in buf for tok in _OK_TOKENS):
        return True
    if any(tok in buf for tok in _ERR_TOKENS):
        return True
    return False


class SerialATError(Exception):
    """Raised when AT 指令执行过程中发生串口或超时异常。"""

class SerialAT:
    """单例串口 + 互斥，调用 send('AT...') -> List[str]（含原始回显行）"""

    def __init__(self, port: str, baudrate: int):
        self._preferred_port = port  # 用户配置（可能不存在）
        self._current_port: Optional[str] = None  # 实际正在使用的串口
        self._baudrate = baudrate
        self._ser = None
        self._mu = threading.Lock()
        self._interface_id: Optional[str] = None  # 形如 2-1:1.2
        self._interface_syspath: Optional[str] = None
        self._expected_interface_suffix = ":1.2"  # Quectel AT 接口默认
        self._open()

    # ======= 设备解析 & 自动恢复 =======
    def _port_label(self) -> str:
        """返回当前活跃串口（若无则返回用户配置）"""
        return self._current_port or self._preferred_port

    def _interface_id_from_device(self, device: str) -> Optional[str]:
        """从指定 tty 设备解析接口 ID"""
        tty_name = os.path.basename(device)
        sysfs_path = os.path.join("/sys/class/tty", tty_name)
        if not os.path.exists(sysfs_path):
            return None
        real_path = os.path.realpath(sysfs_path)
        interface_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(real_path))
        )
        interface_id = os.path.basename(interface_dir)
        return interface_id if interface_id and ":1." in interface_id else None

    def _remember_interface(self, device: str) -> None:
        """根据 /sys/class/tty 记录接口 ID，方便后续重新匹配"""
        interface_id = self._interface_id_from_device(device)
        if not interface_id:
            return
        if interface_id and ":1." in interface_id:
            self._interface_id = interface_id
            self._interface_syspath = os.path.join("/sys/bus/usb/devices", interface_id)
            suffix_idx = interface_id.find(":1.")
            if suffix_idx != -1:
                self._expected_interface_suffix = interface_id[suffix_idx:]
            logger.debug(
                "Remembered interface %s for %s (sysfs: %s)",
                interface_id,
                device,
                self._interface_syspath,
            )

    def _find_port_by_interface(self) -> Optional[str]:
        """通过接口 ID 查找最新的 ttyUSB 节点"""
        if not self._interface_id:
            return None
        interface_path = self._interface_syspath or os.path.join(
            "/sys/bus/usb/devices", self._interface_id
        )
        if not os.path.isdir(interface_path):
            return None
        candidates = sorted(glob.glob(os.path.join(interface_path, "ttyUSB*")))
        for tty_path in candidates:
            dev_name = os.path.basename(tty_path)
            candidate = os.path.join("/dev", dev_name)
            if os.path.exists(candidate):
                logger.info(
                    "Resolved interface %s to %s", self._interface_id, candidate
                )
                return candidate
        return None

    def _scan_for_expected_interface(self) -> Optional[str]:
        """当不存在首选接口信息时，根据接口后缀（如 :1.2）扫描 ttyUSB"""
        suffix = self._expected_interface_suffix
        if not suffix:
            return None
        for dev in sorted(glob.glob("/dev/ttyUSB*")):
            interface_id = self._interface_id_from_device(dev)
            if not interface_id:
                continue
            if interface_id.endswith(suffix):
                self._interface_id = interface_id
                self._interface_syspath = os.path.join(
                    "/sys/bus/usb/devices", interface_id
                )
                logger.info(
                    "Auto-detected interface %s via %s based on suffix %s",
                    interface_id,
                    dev,
                    suffix,
                )
                return dev
        return None

    def _resolve_port_path(self) -> str:
        """确定当前可用的串口路径"""
        if os.path.exists(self._preferred_port):
            return self._preferred_port
        alt = self._find_port_by_interface()
        if alt:
            return alt
        alt = self._scan_for_expected_interface()
        if alt:
            return alt
        raise SerialATError(
            f"Serial device {self._preferred_port} not found and interface could not be resolved."
        )

    def _open(self, wait_for_device: float = 0.0):
        """打开串口；可选等待 wait_for_device 秒以等待 USB 重新枚举"""
        deadline = time.time() + wait_for_device if wait_for_device else None
        last_exc: Optional[Exception] = None
        while True:
            try:
                port_to_use = self._resolve_port_path()
                self._ser = serial.Serial(
                    port=port_to_use,
                    baudrate=self._baudrate,
                    timeout=_READ_TIMEOUT,
                    write_timeout=_WRITE_TIMEOUT,
                )
                self._current_port = port_to_use
                self._remember_interface(port_to_use)
                logger.info(
                    f"Serial port opened: {port_to_use} @ {self._baudrate}"
                )
                return
            except Exception as exc:
                last_exc = exc if isinstance(exc, SerialATError) else SerialATError(
                    f"Failed to open serial port {self._preferred_port}: {exc}"
                )
            if deadline and time.time() < deadline:
                time.sleep(1.0)
                continue
            raise last_exc  # type: ignore[misc]

    def reset(self):
        """主动重置：关闭当前串口句柄，下次 send 时会重新 _open()"""
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None
        logger.info(f"Serial port reset: {self._port_label()}")

    def _read_until_done(self, deadline: float) -> List[str]:
        """从串口读取直到看到 OK/ERROR 或超时"""
        if self._ser is None:
            raise OSError("Serial port not open")
        t0 = time.time()
        buf = bytearray()
        done = False
        while True:
            chunk = self._ser.read(_READ_CHUNK)
            if chunk:
                buf.extend(chunk)
                if _done(buf):
                    done = True
                    break
            # 超时保护
            if time.time() - t0 >= deadline:
                break
            if not chunk:
                time.sleep(0.01)  # 轻微让步，降 CPU
        if not buf:
            raise TimeoutError("no response from modem")
        if not done:
            raise TimeoutError("AT response incomplete or timed out")
        # 转行（保留所有原始行）
        text = buf.decode(errors="ignore")
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        # 去掉末尾可能的空行
        while lines and lines[-1] == "":
            lines.pop()
        return lines

    def _execute_at(self, cmd: str, deadline: float) -> List[str]:
        """内部方法：执行单次 AT 命令（不包含重连逻辑）"""
        if self._ser is None:
            self._open()
        # 清掉历史残留
        try:
            self._ser.reset_input_buffer()
        except Exception:
            pass
        # 写入
        data = (cmd.rstrip() + "\r\n").encode()
        self._ser.write(data)
        self._ser.flush()
        # 读取
        lines = self._read_until_done(deadline)
        if not lines:
            raise SerialATError(f"{cmd} returned empty response")
        return lines

    def send(self, cmd: str, deadline: float = _DEFAULT_DEADLINE) -> List[str]:
        """发送一条 AT 并在看到 OK/ERROR 就立刻返回原始回显行
        
        如果遇到 I/O 错误，会自动重连一次再重试。
        """
        with self._mu:
            try:
                return self._execute_at(cmd, deadline)
            except TimeoutError as exc:
                # 超时错误不重连，直接抛出
                raise SerialATError(f"{cmd} timeout: {exc}") from exc
            except (OSError, IOError, serial.SerialException) as e:
                logger.warning(
                    "Serial I/O error on %s while executing %s: %s. Attempting reconnect...",
                    self._port_label(),
                    cmd,
                    e,
                )
                self.reset()
                wait_plan = [2.0, 5.0, 10.0]
                last_error: Optional[Exception] = None
                for wait_seconds in wait_plan:
                    try:
                        self._open(wait_for_device=wait_seconds)
                        logger.info(
                            "Serial port reconnected on %s after wait %.1fs, retrying %s...",
                            self._port_label(),
                            wait_seconds,
                            cmd,
                        )
                        return self._execute_at(cmd, deadline)
                    except Exception as reconnect_exc:
                        last_error = reconnect_exc
                        logger.warning(
                            "Reconnect attempt after %.1fs failed: %s",
                            wait_seconds,
                            reconnect_exc,
                        )
                        self.reset()
                        continue
                raise SerialATError(
                    f"Serial I/O error after reconnect attempts on {self._port_label()}: {last_error}"
                ) from last_error or e

# 模块级单例，供其它模块直接 import 使用
serial_at = SerialAT(SERIAL_PORT, BAUDRATE)