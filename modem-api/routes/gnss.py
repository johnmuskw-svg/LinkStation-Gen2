# routes/gnss.py
import json
import subprocess
import time
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/gnss", tags=["gnss"])

PYTHON = "/opt/linkstation/gnss-demo/.venv/bin/python3"
SCRIPT = "/opt/linkstation/gnss-demo/gnss_reader.py"
CWD = "/opt/linkstation/gnss-demo"

# 模块级全局变量：保存上一帧有效的卫星数据（用于补丁）
_GNSS_LAST_GOOD_SATS = None  # type: dict | None


def _read_nav_state_once() -> dict:
    """调用 GNSS 脚本获取导航状态"""
    try:
        proc = subprocess.run(
            [PYTHON, SCRIPT, "--once"],
            capture_output=True,
            text=True,
            timeout=2.5,  # 脚本内部1.2秒超时，这里给2.5秒缓冲
            cwd=CWD,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="GNSS reader timeout")
    
    if proc.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"GNSS reader error: {proc.stderr.strip() or proc.stdout.strip()}",
        )
    
    stdout = proc.stdout.strip()
    if not stdout:
        raise HTTPException(status_code=500, detail="GNSS reader returned empty output")
    
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid GNSS JSON output")


@router.get("/live")
def gnss_live(verbose: bool = Query(False, description="是否返回原始 NMEA 数据")):
    """获取 GNSS 实时导航状态"""
    global _GNSS_LAST_GOOD_SATS
    
    nav = _read_nav_state_once()
    
    # 处理卫星数据缓存和补丁逻辑
    sats = nav.get("satellites") or {}
    in_view = sats.get("in_view") or 0
    valid = sats.get("valid", False)
    
    # 如果当前帧卫星数据有效，更新缓存
    if valid and in_view > 0:
        _GNSS_LAST_GOOD_SATS = {
            "in_use": sats.get("in_use"),
            "in_view": sats.get("in_view"),
            "list": sats.get("list", []),
            "valid": True,
        }
    elif _GNSS_LAST_GOOD_SATS is not None:
        # 没有新卫星数据，就沿用上一帧
        nav["satellites"] = _GNSS_LAST_GOOD_SATS.copy()
    
    # 默认删除 raw 字段，除非 verbose=true
    if not verbose and isinstance(nav, dict) and "raw" in nav:
        nav = dict(nav)
        nav.pop("raw", None)
    
    return {
        "ok": True,
        "ts": int(time.time() * 1000),
        "nav": nav,
    }

