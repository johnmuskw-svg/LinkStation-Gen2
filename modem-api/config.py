import os
from typing import List
from dotenv import load_dotenv

load_dotenv()  # 读取 .env

def _get_int(name: str, default: int) -> int:
    try: return int(os.getenv(name, str(default)))
    except: return default

def _get_float(name: str, default: float) -> float:
    try: return float(os.getenv(name, str(default)))
    except: return default

def _get_list(name: str, default_csv: str) -> List[str]:
    raw = os.getenv(name, default_csv)
    if not raw: return []
    return [x.strip() for x in raw.split(",") if x.strip()]

API_TITLE   = os.getenv("API_TITLE", "LinkStation Modem API")
API_PREFIX  = os.getenv("API_PREFIX", "/v1")

SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/ttyUSB2")
BAUDRATE    = _get_int("BAUDRATE", 115200)

POLL_INTERVAL = _get_float("POLL_INTERVAL", 1.0)
INFO_TTL      = _get_int("INFO_TTL", 30)
LIVE_TTL      = _get_int("LIVE_TTL", 2)

CORS_ORIGINS  = _get_list("CORS_ORIGINS", "")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "changeme")
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "0").lower() in ("1", "true", "yes", "on")

# 对外端口（若以后用 uvicorn 内置读取）
HOST = os.getenv("HOST", "0.0.0.0")
PORT = _get_int("PORT", 8000)

# Step-3: 控制类 API 安全开关
def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name, "").lower()
    if val in ("1", "true", "yes", "on"):
        return True
    elif val in ("0", "false", "no", "off"):
        return False
    return default

CTRL_ENABLE = _get_bool("LINKSTATION_CTRL_ENABLE", True)  # 全局总开关
CTRL_ALLOW_DANGEROUS = _get_bool("LINKSTATION_CTRL_ALLOW_DANGEROUS", False)  # 是否允许危险动作

# NVR 集成配置
NVR_ENABLED = _get_bool("NVR_ENABLED", True)
NVR_TIMEOUT = _get_float("NVR_TIMEOUT", 3.0)

# NVR 连接配置（优先使用细粒度配置，向后兼容 NVR_BASE_URL）
NVR_HOST = os.getenv("NVR_HOST", "192.168.99.11")
NVR_PORT = _get_int("NVR_PORT", 8787)
NVR_API_PREFIX = os.getenv("NVR_API_PREFIX", "/v1")

# NVR_BASE_URL：基础 URL（不包含 API 前缀），用于向后兼容
# 如果设置了 NVR_BASE_URL，优先使用（向后兼容）
# 否则根据 NVR_HOST、NVR_PORT 组合生成（不包含 API 前缀）
_nvr_base_url_from_env = os.getenv("NVR_BASE_URL", "").strip()
if _nvr_base_url_from_env:
    # 如果用户设置的 NVR_BASE_URL 包含 /v1，需要去掉
    NVR_BASE_URL = _nvr_base_url_from_env.rstrip("/").rstrip("/v1")
else:
    NVR_BASE_URL = f"http://{NVR_HOST}:{NVR_PORT}".rstrip("/")

# NVR 对手机／App 暴露出来的统一 RTSP 入口
NVR_PUBLIC_HOST = os.getenv("NVR_PUBLIC_HOST", NVR_HOST)
NVR_PUBLIC_SUB_BASE_PORT = _get_int("NVR_PUBLIC_SUB_BASE_PORT", 9550)


# NVR URL 生成工具函数
def get_nvr_base_url() -> str:
    """
    获取 NVR 基础 URL（包含协议、主机、端口，不包含 API 前缀）
    例如：http://192.168.99.11:8787
    """
    return NVR_BASE_URL


def nvr_url(path: str) -> str:
    """
    生成完整的 NVR API URL（自动添加 API 前缀）
    
    Args:
        path: API 路径，例如 "/cameras" 或 "cameras" 或 "/v1/cameras"
          如果 path 以 /v1/ 开头，会保留；否则会自动添加 NVR_API_PREFIX
    
    Returns:
        完整的 URL，例如 "http://192.168.99.11:8787/v1/cameras"
    
    Examples:
        >>> nvr_url("/cameras")
        'http://192.168.99.11:8787/v1/cameras'
        >>> nvr_url("cameras")
        'http://192.168.99.11:8787/v1/cameras'
        >>> nvr_url("/v1/health")
        'http://192.168.99.11:8787/v1/health'
    """
    base = get_nvr_base_url().rstrip("/")
    path = path.lstrip("/")
    # 如果 path 已经以 /v1/ 开头，直接拼接；否则添加 API 前缀
    if path.startswith("v1/"):
        return f"{base}/{path}"
    else:
        api_prefix = NVR_API_PREFIX.lstrip("/")
        return f"{base}/{api_prefix}/{path}"
