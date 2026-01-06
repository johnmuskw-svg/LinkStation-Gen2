# routes/net.py
import logging
import subprocess
import time
from typing import Optional, Literal
from fastapi import APIRouter, HTTPException
from .schemas import UplinkRequest, UplinkResponse

router = APIRouter(prefix="/net", tags=["net"])
logger = logging.getLogger(__name__)

# 脚本路径
UPLINK_SCRIPT = "/usr/local/sbin/ls-uplink"


def _get_current_uplink_mode() -> Optional[Literal["sim", "wifi"]]:
    """
    通过 ip route 判断当前默认路由的网卡，确定当前上网出口模式
    返回 "sim" (usb0) 或 "wifi" (wlan0) 或 None
    """
    try:
        result = subprocess.run(
            ["ip", "route"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True
        )
        lines = result.stdout.strip().split("\n")
        
        # 查找 metric 最小的 default 路由
        default_routes = []
        for line in lines:
            if line.startswith("default"):
                parts = line.split()
                # 提取 dev 和 metric
                dev = None
                metric = 9999
                for i, part in enumerate(parts):
                    if part == "dev" and i + 1 < len(parts):
                        dev = parts[i + 1]
                    elif part == "metric" and i + 1 < len(parts):
                        try:
                            metric = int(parts[i + 1])
                        except ValueError:
                            pass
                
                if dev:
                    default_routes.append((metric, dev, line))
        
        if not default_routes:
            return None
        
        # 按 metric 排序，取最小的
        default_routes.sort(key=lambda x: x[0])
        primary_dev = default_routes[0][1]
        
        if primary_dev == "usb0":
            return "sim"
        elif primary_dev == "wlan0":
            return "wifi"
        else:
            logger.warning(f"Unknown primary device: {primary_dev}")
            return None
            
    except subprocess.TimeoutExpired:
        logger.error("Timeout while getting current uplink mode")
        return None
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to get current uplink mode: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting current uplink mode: {e}")
        return None


def _get_default_route_string() -> Optional[str]:
    """获取当前默认路由的字符串表示"""
    try:
        result = subprocess.run(
            ["ip", "route"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True
        )
        lines = result.stdout.strip().split("\n")
        default_lines = [line for line in lines if line.startswith("default")]
        return "\n".join(default_lines) if default_lines else None
    except Exception as e:
        logger.error(f"Failed to get default route: {e}")
        return None


@router.get("/uplink", response_model=UplinkResponse)
def get_uplink():
    """
    查询当前上网出口模式
    通过 ip route 判断默认路由的网卡（usb0=sim, wlan0=wifi）
    """
    ts = int(time.time() * 1000)
    
    try:
        mode = _get_current_uplink_mode()
        default_route = _get_default_route_string()
        
        if mode is None:
            return UplinkResponse(
                ok=False,
                ts=ts,
                error="无法确定当前上网出口模式",
                mode=None,
                default_route=default_route
            )
        
        return UplinkResponse(
            ok=True,
            ts=ts,
            error=None,
            mode=mode,
            default_route=default_route
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_uplink: {e}")
        return UplinkResponse(
            ok=False,
            ts=ts,
            error=f"查询失败: {str(e)}",
            mode=None,
            default_route=None
        )


@router.post("/uplink", response_model=UplinkResponse)
def set_uplink(req: UplinkRequest):
    """
    切换上网出口模式
    内部执行: sudo /usr/local/sbin/ls-uplink <mode>
    只接受 sim/wifi 两种模式（已在 Pydantic 模型中限制）
    """
    ts = int(time.time() * 1000)
    
    # 安全验证：确保 mode 只能是 sim 或 wifi（Pydantic 已保证，但双重检查）
    if req.mode not in ("sim", "wifi"):
        raise HTTPException(
            status_code=400,
            detail=f"无效的模式: {req.mode}，只支持 sim 或 wifi"
        )
    
    try:
        # 执行脚本（使用 sudo，通过 sudoers 配置允许无密码执行）
        result = subprocess.run(
            ["sudo", UPLINK_SCRIPT, req.mode],
            capture_output=True,
            text=True,
            timeout=30,
            check=False  # 不自动抛出异常，手动处理
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() or f"脚本执行失败，退出码: {result.returncode}"
            
            # 根据退出码提供更详细的错误信息
            if result.returncode == 2:
                error_msg = f"参数错误: {error_msg}"
            elif result.returncode == 3:
                error_msg = f"SIM 连接未找到: {error_msg}"
            elif result.returncode == 4:
                error_msg = f"Wi-Fi 连接未找到: {error_msg}"
            
            logger.error(f"ls-uplink failed: {error_msg}")
            return UplinkResponse(
                ok=False,
                ts=ts,
                error=error_msg,
                mode=None,
                default_route=None
            )
        
        # 脚本执行成功，获取当前状态
        mode = _get_current_uplink_mode()
        default_route = _get_default_route_string()
        
        # 如果无法确定模式，使用请求的模式（脚本已执行成功）
        if mode is None:
            mode = req.mode
        
        return UplinkResponse(
            ok=True,
            ts=ts,
            error=None,
            mode=mode,
            default_route=default_route
        )
        
    except subprocess.TimeoutExpired:
        error_msg = "脚本执行超时（超过30秒）"
        logger.error(error_msg)
        return UplinkResponse(
            ok=False,
            ts=ts,
            error=error_msg,
            mode=None,
            default_route=None
        )
    except FileNotFoundError:
        error_msg = f"脚本不存在: {UPLINK_SCRIPT}，请确保已正确安装"
        logger.error(error_msg)
        return UplinkResponse(
            ok=False,
            ts=ts,
            error=error_msg,
            mode=None,
            default_route=None
        )
    except PermissionError:
        error_msg = "权限不足，无法执行脚本。请检查 sudoers 配置"
        logger.error(error_msg)
        return UplinkResponse(
            ok=False,
            ts=ts,
            error=error_msg,
            mode=None,
            default_route=None
        )
    except Exception as e:
        error_msg = f"切换失败: {str(e)}"
        logger.error(f"Unexpected error in set_uplink: {e}")
        return UplinkResponse(
            ok=False,
            ts=ts,
            error=error_msg,
            mode=None,
            default_route=None
        )


