from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, Tuple
from pathlib import Path
import platform
import socket
import os
import shutil
import time
import logging
import traceback
import json
import subprocess

router = APIRouter(prefix="/base", tags=["base"])
logger = logging.getLogger(__name__)

# ---- Models ----
class BaseInfoResponse(BaseModel):
    ok: bool
    ts: int
    error: Optional[str] = None
    hostname: str
    os_name: str
    os_version: str
    arch: str
    uptime_sec: Optional[float] = None
    load_1: Optional[float] = None
    load_5: Optional[float] = None
    load_15: Optional[float] = None
    mem_total_kb: Optional[int] = None
    mem_used_kb: Optional[int] = None
    mem_free_kb: Optional[int] = None
    disk_total_gb: Optional[float] = None
    disk_used_gb: Optional[float] = None
    disk_free_gb: Optional[float] = None
    soc_temp_c: Optional[float] = None

class AuthCheckRequest(BaseModel):
    password: str

class AuthSetRequest(BaseModel):
    enabled: bool
    password: Optional[str] = None

class BaseActionResponse(BaseModel):
    ok: bool
    ts: int
    detail: dict | None = None
    error: str | None = None

# ---- Helper Functions ----
def _get_uptime_sec() -> Optional[float]:
    """从 /proc/uptime 读取开机时长（秒）"""
    try:
        with open("/proc/uptime", "r") as f:
            uptime_str = f.read().strip().split()[0]
            return float(uptime_str)
    except Exception as e:
        logger.warning(f"Failed to read /proc/uptime: {e}")
        return None

def _get_loadavg() -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """获取 1/5/15 分钟 load average"""
    try:
        load_1, load_5, load_15 = os.getloadavg()
        return load_1, load_5, load_15
    except (OSError, AttributeError) as e:
        logger.warning(f"Failed to get load average: {e}")
        return None, None, None

def _get_meminfo_kb() -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """从 /proc/meminfo 解析内存信息（KB）"""
    try:
        mem_total = None
        mem_available = None
        mem_free = None
        
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_available = int(line.split()[1])
                elif line.startswith("MemFree:") and mem_available is None:
                    mem_free = int(line.split()[1])
        
        if mem_total is None:
            logger.warning("MemTotal not found in /proc/meminfo")
            return None, None, None
        
        # 优先使用 MemAvailable，否则使用 MemFree
        mem_free_kb = mem_available if mem_available is not None else mem_free
        if mem_free_kb is None:
            logger.warning("Neither MemAvailable nor MemFree found in /proc/meminfo")
            return None, None, None
        
        mem_used_kb = mem_total - mem_free_kb
        return mem_total, mem_used_kb, mem_free_kb
    except Exception as e:
        logger.warning(f"Failed to read /proc/meminfo: {e}")
        return None, None, None

def _get_disk_usage_gb(path: str = "/") -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """获取磁盘使用情况（GB），保留1位小数"""
    try:
        total, used, free = shutil.disk_usage(path)
        # 转换为 GB，保留1位小数
        total_gb = round(total / (1024 ** 3), 1)
        used_gb = round(used / (1024 ** 3), 1)
        free_gb = round(free / (1024 ** 3), 1)
        return total_gb, used_gb, free_gb
    except Exception as e:
        logger.warning(f"Failed to get disk usage for {path}: {e}")
        return None, None, None

def _get_soc_temp_c() -> Optional[float]:
    """从 /sys/class/thermal/thermal_zone0/temp 读取 SoC 温度（摄氏度）"""
    path = "/sys/class/thermal/thermal_zone0/temp"
    try:
        with open(path, "r") as f:
            raw = f.read().strip()
        if not raw:
            return None
        val = float(raw)
        # 大多数内核是毫度（e.g. 47000 = 47.0°C）
        if val > 1000:
            val = val / 1000.0
        return val
    except Exception as e:
        logger.warning(f"Failed to read SoC temperature from {path}: {e}")
        return None

# ---- Auth Config Helpers ----
def _auth_config_path() -> Path:
    """返回 config/base_auth.json 的绝对路径"""
    project_root = Path(__file__).parent.parent
    return project_root / "config" / "base_auth.json"

def _load_auth_config() -> dict:
    """加载认证配置，不存在时返回默认值"""
    default_config = {"enabled": False, "password": ""}
    config_path = _auth_config_path()
    
    if not config_path.exists():
        return default_config
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # 确保包含必要字段
            if "enabled" not in cfg:
                cfg["enabled"] = False
            if "password" not in cfg:
                cfg["password"] = ""
            return cfg
    except Exception as e:
        logger.warning(f"Failed to load auth config from {config_path}: {e}")
        return default_config

def _save_auth_config(cfg: dict) -> None:
    """保存认证配置到文件"""
    config_path = _auth_config_path()
    # 确保父目录存在
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save auth config to {config_path}: {e}")
        raise

# ---- Routes ----
@router.get("/info")
def get_base_info():
    """获取主机系统信息"""
    ts = int(time.time() * 1000)
    
    try:
        # 获取基础系统信息（这些通常不会失败）
        hostname = socket.gethostname()
        os_name = platform.system()
        os_version = platform.release()
        arch = platform.machine()
        
        # 获取可选的系统信息（失败时返回 None）
        uptime_sec = _get_uptime_sec()
        load_1, load_5, load_15 = _get_loadavg()
        mem_total_kb, mem_used_kb, mem_free_kb = _get_meminfo_kb()
        disk_total_gb, disk_used_gb, disk_free_gb = _get_disk_usage_gb()
        soc_temp_c = _get_soc_temp_c()
        
        return BaseInfoResponse(
            ok=True,
            ts=ts,
            error=None,
            hostname=hostname,
            os_name=os_name,
            os_version=os_version,
            arch=arch,
            uptime_sec=uptime_sec,
            load_1=load_1,
            load_5=load_5,
            load_15=load_15,
            mem_total_kb=mem_total_kb,
            mem_used_kb=mem_used_kb,
            mem_free_kb=mem_free_kb,
            disk_total_gb=disk_total_gb,
            disk_used_gb=disk_used_gb,
            disk_free_gb=disk_free_gb,
            soc_temp_c=soc_temp_c,
        )
    except Exception as exc:
        logger.error(f"Failed to get base info: {exc}")
        traceback.print_exc()
        return BaseInfoResponse(
            ok=False,
            ts=ts,
            error=f"base info failed: {exc}",
            hostname="",
            os_name="",
            os_version="",
            arch="",
            uptime_sec=None,
            load_1=None,
            load_5=None,
            load_15=None,
            mem_total_kb=None,
            mem_used_kb=None,
            mem_free_kb=None,
            disk_total_gb=None,
            disk_used_gb=None,
            disk_free_gb=None,
            soc_temp_c=None,
        )

@router.post("/auth/check", response_model=BaseActionResponse)
def check_auth(req: AuthCheckRequest):
    """检查密码是否正确"""
    ts = int(time.time() * 1000)
    
    try:
        cfg = _load_auth_config()
        
        if not cfg.get("enabled", False):
            # 未启用认证，默认放行
            return BaseActionResponse(
                ok=True,
                ts=ts,
                error=None,
                detail={
                    "enabled": False,
                    "matched": True,
                    "note": "auth not enabled"
                }
            )
        
        # 启用认证，检查密码
        matched = (req.password == cfg.get("password", ""))
        
        return BaseActionResponse(
            ok=matched,
            ts=ts,
            error=None if matched else "invalid password",
            detail={
                "enabled": True,
                "matched": matched
            }
        )
    except Exception as e:
        logger.error(f"Failed to check auth: {e}")
        traceback.print_exc()
        return BaseActionResponse(
            ok=False,
            ts=ts,
            error=str(e),
            detail={"enabled": None, "matched": False}
        )

@router.post("/auth/set", response_model=BaseActionResponse)
def set_auth(req: AuthSetRequest):
    """设置或关闭认证密码"""
    ts = int(time.time() * 1000)
    
    try:
        if not req.enabled:
            # 关闭认证，清空密码
            cfg = {"enabled": False, "password": ""}
            _save_auth_config(cfg)
            return BaseActionResponse(
                ok=True,
                ts=ts,
                error=None,
                detail={"enabled": False}
            )
        
        # 启用认证，要求密码非空
        if not req.password or req.password.strip() == "":
            return BaseActionResponse(
                ok=False,
                ts=ts,
                error="password required when enabling auth",
                detail={"enabled": None}
            )
        
        # 保存配置
        cfg = {"enabled": True, "password": req.password}
        _save_auth_config(cfg)
        
        return BaseActionResponse(
            ok=True,
            ts=ts,
            error=None,
            detail={"enabled": True}
        )
    except Exception as e:
        logger.error(f"Failed to set auth: {e}")
        traceback.print_exc()
        return BaseActionResponse(
            ok=False,
            ts=ts,
            error=str(e),
            detail={"enabled": None}
        )

@router.post("/reboot", response_model=BaseActionResponse)
def base_reboot():
    """系统重启"""
    ts = int(time.time() * 1000)
    
    try:
        # 使用 Popen 异步执行，不阻塞
        subprocess.Popen(["sudo", "systemctl", "reboot"])
        logger.info("Reboot command executed")
        return BaseActionResponse(
            ok=True,
            ts=ts,
            error=None,
            detail={"action": "reboot"}
        )
    except Exception as e:
        logger.error(f"Failed to execute reboot: {e}")
        traceback.print_exc()
        return BaseActionResponse(
            ok=False,
            ts=ts,
            error=str(e),
            detail={"action": "reboot_failed"}
        )

@router.post("/shutdown", response_model=BaseActionResponse)
def base_shutdown():
    """系统关机"""
    ts = int(time.time() * 1000)
    
    try:
        # 使用 Popen 异步执行，不阻塞
        subprocess.Popen(["sudo", "systemctl", "poweroff"])
        logger.info("Shutdown command executed")
        return BaseActionResponse(
            ok=True,
            ts=ts,
            error=None,
            detail={"action": "shutdown"}
        )
    except Exception as e:
        logger.error(f"Failed to execute shutdown: {e}")
        traceback.print_exc()
        return BaseActionResponse(
            ok=False,
            ts=ts,
            error=str(e),
            detail={"action": "shutdown_failed"}
        )

