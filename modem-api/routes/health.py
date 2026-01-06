from fastapi import APIRouter
from datetime import datetime
import config

router = APIRouter(tags=["health"])

_started_at = datetime.utcnow()

@router.get("/health")
def health():
    # 这里先做最简健康返回；后续可接入 poller 状态/串口自检
    return {
        "ok": True,
        "time": datetime.utcnow().isoformat() + "Z",
        "uptime_sec": (datetime.utcnow() - _started_at).total_seconds(),
    }

@router.get("/version")
def version():
    return {
        "api_title": config.API_TITLE,
        "api_prefix": config.API_PREFIX,
        "serial_port": config.SERIAL_PORT,
        "baudrate": config.BAUDRATE,
    }