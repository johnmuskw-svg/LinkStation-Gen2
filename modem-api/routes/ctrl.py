# routes/ctrl.py
import logging
import re
import time
from typing import List, Optional, Tuple

from fastapi import APIRouter

from config import CTRL_ENABLE, CTRL_ALLOW_DANGEROUS
from core.serial_port import serial_at, SerialATError
from .schemas import (
    CtrlBaseResponse,
    CtrlBaseRequest,
    CtrlActionDetail,
    CtrlRebootRequest,
    CtrlUsbNetRequest,
    CtrlApnRequest,
    CtrlRoamingRequest,
    CtrlBandRequest,
    CtrlCellLockRequest,
    CtrlCaRequest,
    CtrlGnssRequest,
    CtrlResetProfileRequest,
    CtrlNetworkModeRequest,
    CtrlBandPreferenceRequest,
    RoamingResponse,
    RoamingState,
    NetworkModeResponse,
    NetworkModeState,
    BandPreferenceResponse,
    BandPreferenceState,
)

router = APIRouter(prefix="/ctrl", tags=["ctrl"])
logger = logging.getLogger(__name__)


# AT 命令发送辅助函数（与 live/info 保持一致）
def _at(cmd: str) -> List[str]:
    """发送 AT 命令并返回回显行列表"""
    return serial_at.send(cmd)


# ===== 计划函数：将请求转换为 AT 命令列表 =====

def _plan_reboot(req: CtrlRebootRequest) -> List[str]:
    """
    计划重启命令
    根据手册: AT+CFUN=<fun>[,<rst>]
    - soft: AT+CFUN=1,1 (全功能 + 重启)
    - full: AT+CFUN=1,1 (全功能 + 重启，与 soft 相同)
    - rf_off: AT+CFUN=4 (飞行模式，关闭射频)
    """
    if req.mode == "soft":
        return ["AT+CFUN=1,1"]
    elif req.mode == "full":
        # 完整重启：先关闭射频再重启
        return ["AT+CFUN=4", "AT+CFUN=1,1"]
    elif req.mode == "rf_off":
        return ["AT+CFUN=4"]
    else:
        raise ValueError(f"unsupported reboot mode: {req.mode}")


def _plan_roaming(req: CtrlRoamingRequest) -> List[str]:
    """计划漫游开关命令
    
    根据 Quectel 手册 5.24.8，使用 AT+QNWPREFCFG="roam_pref",<roam_pref>
    - enable=False -> 1 (仅 home 网络)
    - enable=True  -> 255 (任意网络，包括漫游)
    """
    pref_val = "255" if req.enable else "1"
    return [f'AT+QNWPREFCFG="roam_pref",{pref_val}']


def _parse_roam_pref(lines: List[str]) -> Optional[int]:
    """解析 AT+QNWPREFCFG="roam_pref" 的返回，提取 roam_pref 数值"""
    for line in lines:
        match = re.search(r'\+QNWPREFCFG:\s*"roam_pref"\s*,\s*(\d+)', line)
        if match:
            try:
                return int(match.group(1))
            except Exception:
                return None
    return None


def _pref_to_bool(pref: int) -> bool:
    """将 roam_pref 数值转换为布尔漫游状态"""
    # 1: 仅 home，不允许漫游；其他值允许漫游
    return pref not in (1,)


def _bool_to_pref(enabled: bool) -> int:
    """根据布尔开关返回 roam_pref 取值"""
    return 255 if enabled else 1


def _query_roam_pref() -> Tuple[Optional[bool], Optional[List[str]]]:
    """查询当前漫游配置，返回 (enabled, raw_lines)"""
    lines = _at('AT+QNWPREFCFG="roam_pref"')
    pref_val = _parse_roam_pref(lines)
    if pref_val is None:
        return None, lines
    return _pref_to_bool(pref_val), lines


def _plan_gnss(req: CtrlGnssRequest) -> List[str]:
    """计划 GNSS 控制命令"""
    enable_val = "1" if req.enable else "0"
    if req.mode:
        # 如果指定了模式，使用更详细的配置
        return [f'AT+QCFG="gnss",{req.mode},{enable_val}']
    else:
        # 简单开关
        return [f'AT+QCFG="gnss","all",{enable_val}']


def _plan_usbnet(req: CtrlUsbNetRequest) -> List[str]:
    """
    计划 USB 网络模式切换
    根据手册: AT+QCFG="usbnet",<mode>
    mode: 0=ECM, 1=RNDIS, 2=NCM
    """
    mode_map = {
        "ecm": "0",
        "rndis": "1",
        "ncm": "2",
        "mbim": "2",  # MBIM 通常映射到 NCM
        "auto": "0",  # 默认 ECM
    }
    
    mode_val = mode_map.get(req.mode.lower(), "0")
    cmds = [f'AT+QCFG="usbnet",{mode_val}']
    
    # 如果需要重启模组
    if req.reboot_modem:
        cmds.append("AT+CFUN=1,1")
    
    return cmds


def _plan_apn(req: CtrlApnRequest) -> List[str]:
    """
    计划 APN 配置
    根据手册: AT+CGDCONT=<cid>[,<pdp_type>[,<apn>[,<pd_addr>[,<d_comp>[,<h_comp>]]]]]
    认证: AT+CGAUTH=<cid>,<auth_type>,<username>,<password>
    """
    cmds = []
    
    # 1. 配置 PDP 上下文
    # AT+CGDCONT=<cid>,<pdp_type>,<apn>
    cgdcont_cmd = f'AT+CGDCONT={req.cid},"{req.pdp_type}","{req.apn}"'
    cmds.append(cgdcont_cmd)
    
    # 2. 配置认证（如果需要）
    if req.auth.type != "none" and req.auth.user and req.auth.password:
        auth_type_map = {
            "none": "0",
            "pap": "1",
            "chap": "2",
        }
        auth_val = auth_type_map.get(req.auth.type.lower(), "0")
        if auth_val != "0":
            cgauth_cmd = f'AT+CGAUTH={req.cid},{auth_val},"{req.auth.user}","{req.auth.password}"'
            cmds.append(cgauth_cmd)
    
    # 3. 激活 PDP 上下文（如果需要）
    if req.activate:
        cmds.append(f"AT+CGACT=1,{req.cid}")
    
    return cmds


def _plan_band(req: CtrlBandRequest) -> List[str]:
    """
    计划频段锁定
    根据手册:
    - AT+QCFG="band",<rat>,<band_list> (简单方式)
    - AT+QCFG="lte/band",<band_mask> (详细方式，位掩码)
    - AT+QCFG="nr5g/band",<band_mask> (详细方式，位掩码)
    """
    cmds = []
    
    # 如果 reset，清空所有频段锁定
    if req.reset:
        if req.rat == "LTE" or req.rat == "BOTH":
            cmds.append('AT+QCFG="lte/band","0"')
        if req.rat == "NR5G" or req.rat == "BOTH":
            cmds.append('AT+QCFG="nr5g/band","0"')
        return cmds
    
    # 使用简单方式：AT+QCFG="band",<rat>,<band_list>
    if req.rat == "LTE" and req.lte_bands:
        band_list = ",".join(req.lte_bands)
        cmds.append(f'AT+QCFG="band","LTE","{band_list}"')
    elif req.rat == "NR5G" and req.nr_bands:
        band_list = ",".join(req.nr_bands)
        cmds.append(f'AT+QCFG="band","NR5G","{band_list}"')
    elif req.rat == "BOTH":
        if req.lte_bands:
            band_list = ",".join(req.lte_bands)
            cmds.append(f'AT+QCFG="band","LTE","{band_list}"')
        if req.nr_bands:
            band_list = ",".join(req.nr_bands)
            cmds.append(f'AT+QCFG="band","NR5G","{band_list}"')
    
    return cmds


def _plan_cell_lock(req: CtrlCellLockRequest) -> List[str]:
    """
    计划小区锁定
    根据手册:
    - AT+QNWLOCK=<mode>,<rat> (制式锁定)
    - 小区锁定可能需要组合多个命令，这里先实现制式锁定
    """
    cmds = []
    
    if req.enable:
        # 锁定到指定制式
        if req.rat:
            # AT+QNWLOCK=1,<rat>
            rat_map = {
                "lte": "LTE",
                "nr5g": "NR5G",
                "nr": "NR5G",
                "5g": "NR5G",
            }
            rat_val = rat_map.get(req.rat.lower(), req.rat.upper())
            cmds.append(f'AT+QNWLOCK=1,"{rat_val}"')
        
        # 如果指定了 PCI，可能需要额外的锁定命令
        # 注意：Quectel 的小区锁定可能需要特定固件支持，这里先做基础实现
        if req.pci is not None:
            # 某些固件可能支持 AT+QNWLOCK 的扩展参数，这里先占位
            # 实际实现可能需要查询固件版本和手册
            pass
    else:
        # 解锁：AT+QNWLOCK=0
        cmds.append("AT+QNWLOCK=0")
    
    return cmds


def _plan_ca(req: CtrlCaRequest) -> List[str]:
    """
    计划 CA 开关
    根据手册:
    - AT+QCFG="ca",<enable> (全局 CA)
    - AT+QCFG="lte/ca",<enable> (LTE CA)
    - AT+QCFG="nr5g/ca",<enable> (5G CA)
    """
    cmds = []
    
    # 如果同时指定了 LTE 和 NR，分别配置
    if req.lte_ca_enable is not None:
        enable_val = "1" if req.lte_ca_enable else "0"
        cmds.append(f'AT+QCFG="lte/ca",{enable_val}')
    
    if req.nr_ca_enable is not None:
        enable_val = "1" if req.nr_ca_enable else "0"
        cmds.append(f'AT+QCFG="nr5g/ca",{enable_val}')
    
    # 如果只指定了一个，使用全局 CA 配置
    if req.lte_ca_enable is None and req.nr_ca_enable is None:
        # 默认启用 CA
        cmds.append('AT+QCFG="ca",1')
    elif req.lte_ca_enable is not None and req.nr_ca_enable is None:
        # 只有 LTE，使用全局配置
        enable_val = "1" if req.lte_ca_enable else "0"
        cmds.append(f'AT+QCFG="ca",{enable_val}')
    elif req.lte_ca_enable is None and req.nr_ca_enable is not None:
        # 只有 NR，使用全局配置
        enable_val = "1" if req.nr_ca_enable else "0"
        cmds.append(f'AT+QCFG="ca",{enable_val}')
    
    return cmds


def _plan_network_mode(req: CtrlNetworkModeRequest) -> List[str]:
    """
    计划网络模式选择命令
    根据手册 5.24.5: AT+QNWPREFCFG="mode_pref",<mode_pref>
    mode_pref: AUTO, WCDMA, LTE, NR5G 或组合（用冒号分隔，如 LTE:NR5G）
    """
    if req.mode_pref is None:
        return []  # 查询模式，不需要计划命令
    
    # 设置模式
    return [f'AT+QNWPREFCFG="mode_pref",{req.mode_pref}']


def _parse_mode_pref(lines: List[str]) -> Optional[str]:
    """解析 AT+QNWPREFCFG="mode_pref" 的返回，提取 mode_pref 值"""
    for line in lines:
        match = re.search(r'\+QNWPREFCFG:\s*"mode_pref"\s*,\s*([^\r\n]+)', line)
        if match:
            return match.group(1).strip()
    return None


def _query_mode_pref() -> Tuple[Optional[str], Optional[List[str]]]:
    """查询当前网络模式配置，返回 (mode_pref, raw_lines)"""
    lines = _at('AT+QNWPREFCFG="mode_pref"')
    mode_pref = _parse_mode_pref(lines)
    return mode_pref, lines


def _plan_band_preference(req: CtrlBandPreferenceRequest) -> List[str]:
    """
    计划频段偏好设置命令
    根据手册 5.24.2-5.24.4: AT+QNWPREFCFG="lte_band"/"nsa_nr5g_band"/"nr5g_band"
    注意：这是频段偏好（非锁定），区别于 AT+QCFG="band" 的频段锁定
    """
    cmds = []
    
    # LTE频段偏好
    if req.lte_bands is not None:
        if len(req.lte_bands) == 0:
            # 空列表表示使用所有支持的频段（查询当前值，不设置）
            pass
        else:
            band_str = ":".join(str(b) for b in req.lte_bands)
            cmds.append(f'AT+QNWPREFCFG="lte_band",{band_str}')
    
    # 5G NSA频段偏好
    if req.nsa_nr5g_bands is not None:
        if len(req.nsa_nr5g_bands) == 0:
            pass
        else:
            band_str = ":".join(str(b) for b in req.nsa_nr5g_bands)
            cmds.append(f'AT+QNWPREFCFG="nsa_nr5g_band",{band_str}')
    
    # 5G SA频段偏好
    if req.nr5g_bands is not None:
        if len(req.nr5g_bands) == 0:
            pass
        else:
            band_str = ":".join(str(b) for b in req.nr5g_bands)
            cmds.append(f'AT+QNWPREFCFG="nr5g_band",{band_str}')
    
    return cmds


def _parse_band_pref(lines: List[str], param_name: str) -> Optional[List[int]]:
    """解析 AT+QNWPREFCFG="<param_name>" 的返回，提取频段列表"""
    for line in lines:
        match = re.search(rf'\+QNWPREFCFG:\s*"{param_name}"\s*,\s*([^\r\n]+)', line)
        if match:
            band_str = match.group(1).strip()
            if not band_str:
                return []
            try:
                # 解析冒号分隔的频段列表
                bands = [int(b.strip()) for b in band_str.split(":") if b.strip().isdigit()]
                return bands if bands else None
            except Exception:
                return None
    return None


def _query_band_preference() -> Tuple[Optional[List[int]], Optional[List[int]], Optional[List[int]], Optional[dict]]:
    """查询当前频段偏好配置，返回 (lte_bands, nsa_nr5g_bands, nr5g_bands, raw_dict)"""
    raw_dict = {}
    
    # 查询LTE频段偏好
    lte_lines = _at('AT+QNWPREFCFG="lte_band"')
    raw_dict['AT+QNWPREFCFG="lte_band"'] = lte_lines
    lte_bands = _parse_band_pref(lte_lines, "lte_band")
    
    # 查询5G NSA频段偏好
    nsa_lines = _at('AT+QNWPREFCFG="nsa_nr5g_band"')
    raw_dict['AT+QNWPREFCFG="nsa_nr5g_band"'] = nsa_lines
    nsa_bands = _parse_band_pref(nsa_lines, "nsa_nr5g_band")
    
    # 查询5G SA频段偏好
    sa_lines = _at('AT+QNWPREFCFG="nr5g_band"')
    raw_dict['AT+QNWPREFCFG="nr5g_band"'] = sa_lines
    nr5g_bands = _parse_band_pref(sa_lines, "nr5g_band")
    
    return lte_bands, nsa_bands, nr5g_bands, raw_dict


def _plan_reset_profile(req: CtrlResetProfileRequest) -> List[str]:
    """
    计划一键恢复网络默认配置
    根据 profile 类型生成恢复命令列表
    """
    plan: List[str] = []
    
    if req.profile != "modem_safe":
        # 未知 profile，暂时不生成任何命令
        return plan
    
    # 1) 频段恢复默认（复用 _plan_band 中 reset 的逻辑）
    # 使用位掩码方式清空锁定，与 _plan_band 保持一致
    plan.append('AT+QCFG="lte/band","0"')
    plan.append('AT+QCFG="nr5g/band","0"')
    
    # 2) 解除小区锁（复用 _plan_cell_lock 中解锁的逻辑）
    plan.append("AT+QNWLOCK=0")
    
    # 3) CA 打开（LTE + NR，复用 _plan_ca 的逻辑）
    plan.append('AT+QCFG="lte/ca",1')
    plan.append('AT+QCFG="nr5g/ca",1')
    
    # 4) 数据漫游恢复默认（开启，复用 _plan_roaming 的逻辑）
    plan.append('AT+QNWPREFCFG="roam_pref",255')
    
    # 5) USBNET 恢复为 demo 默认（rndis，复用 _plan_usbnet 的逻辑）
    # rndis 对应 mode="1"，与 _plan_usbnet 保持一致
    plan.append('AT+QCFG="usbnet",1')
    
    # 6) 暂时不修改 APN 和 GNSS（保持用户配置）
    
    return plan


# ===== 执行函数：统一执行层 =====

def _execute_plan(
    action: str,
    plan: List[str],
    req: CtrlBaseRequest,
    *,
    is_dangerous: bool,
) -> CtrlBaseResponse:
    """
    统一执行层：
      - 检查 CTRL_ENABLE / CTRL_ALLOW_DANGEROUS
      - 尊重 req.dry_run
      - 收集 AT 回显放到 resp.raw 里面
      - 统一返回 CtrlActionDetail 结构
      - 捕获所有异常，确保不会抛出 500
    
    执行逻辑（按优先级）：
      1. CTRL_ENABLE=0：强制 dry_run=True, executed=False, blocked_reason="CTRL_ENABLE=0"
      2. 无计划指令：dry_run=True, executed=False, blocked_reason=None
      3. 危险动作且 CTRL_ALLOW_DANGEROUS=False：强制 dry_run=True, executed=False, blocked_reason="CTRL_ALLOW_DANGEROUS=0"
      4. 请求要求 dry_run=true：dry_run=True, executed=False（即使 CTRL_ALLOW_DANGEROUS=True）
      5. 可以真正执行：dry_run=False, executed=True（如果成功）
    """
    try:
        # 初始化 detail 字段
        dry_run: bool
        executed: bool = False
        blocked_reason: Optional[str] = None
        errors: List[str] = []
        all_raw: Optional[dict[str, List[str]]] = None
        
        # 0) 总开关关掉：全 dry_run
        if not CTRL_ENABLE:
            dry_run = True
            executed = False
            blocked_reason = "CTRL_ENABLE=0"
        # 1) 如果没有计划指令：啥也不发，直接返回
        elif not plan:
            dry_run = True
            executed = False
            blocked_reason = None  # 没有计划不算被阻止
        # 2) 危险动作 + 没开 "危险许可" 时：强制 dry_run，无论请求传什么
        elif is_dangerous and not CTRL_ALLOW_DANGEROUS:
            dry_run = True
            executed = False
            blocked_reason = "CTRL_ALLOW_DANGEROUS=0"
        # 3) 如果请求要求 dry_run：只返回计划，不真正执行
        elif req.dry_run:
            dry_run = True
            executed = False
            blocked_reason = None
        # 4) 可以真正执行
        else:
            dry_run = False
            # 真正执行：对每条 AT 调 serial_at.send 收集回显
            all_raw = {}
            for cmd in plan:
                try:
                    logger.info("[%s] sending %s", action, cmd)
                    lines = serial_at.send(cmd)
                    logger.info("[%s] response lines for %s: %s", action, cmd, lines)
                    all_raw[cmd] = lines
                except Exception as e:
                    error_msg = str(e)
                    errors.append(f"{cmd}: {error_msg}")
                    all_raw[cmd] = [f"ERROR: {error_msg}"]
            
            # 如果所有命令都执行成功（没有错误），标记为已执行
            if not errors:
                executed = True
        
        # 构造统一的 detail
        detail = CtrlActionDetail(
            dry_run=dry_run,
            dangerous=is_dangerous,
            executed=executed,
            blocked_reason=blocked_reason,
            planned=plan,
            errors=errors,
            extra=None,
        )
        
        return CtrlBaseResponse(
            ok=True,
            action=action,
            error=None,
            detail=detail,
            raw=all_raw,
        )
    except Exception as e:
        # 兜底：任何未预期的异常都转换为 ok=false 的响应
        detail = CtrlActionDetail(
            dry_run=True,
            dangerous=is_dangerous,
            executed=False,
            blocked_reason=None,
            planned=plan,
            errors=[f"execute_plan failed: {str(e)}"],
            extra=None,
        )
        return CtrlBaseResponse(
            ok=False,
            action=action,
            error=f"ctrl {action} failed: {str(e)}",
            detail=detail,
            raw=None,
        )


# ===== 路由端点 =====

@router.post(
    "/reboot",
    response_model=CtrlBaseResponse,
    summary="重启模组",
    description="重启模组（危险动作，默认只 dry_run）。需要设置 LINKSTATION_CTRL_ALLOW_DANGEROUS=1 才能执行。"
)
async def ctrl_reboot(req: CtrlRebootRequest) -> CtrlBaseResponse:
    """模组重启（危险动作）"""
    logger.info("[reboot] request received: mode=%s, dry_run=%s", req.mode, req.dry_run)
    plan = _plan_reboot(req)
    return _execute_plan("reboot", plan, req, is_dangerous=True)


@router.post(
    "/usbnet",
    response_model=CtrlBaseResponse,
    summary="USB 网络模式切换",
    description="切换 USB 网络模式（危险动作，默认只 dry_run）。支持 rndis/ecm/ncm/mbim 等模式。需要设置 LINKSTATION_CTRL_ALLOW_DANGEROUS=1 才能执行。"
)
async def ctrl_usbnet(req: CtrlUsbNetRequest) -> CtrlBaseResponse:
    """USB 网络模式切换（危险动作）"""
    plan = _plan_usbnet(req)
    return _execute_plan("usbnet", plan, req, is_dangerous=True)


@router.post(
    "/apn",
    response_model=CtrlBaseResponse,
    summary="APN 配置",
    description="配置 APN/PDP 上下文（危险动作，默认只 dry_run）。包括 APN 名称、PDP 类型、认证信息等。需要设置 LINKSTATION_CTRL_ALLOW_DANGEROUS=1 才能执行。"
)
async def ctrl_apn(req: CtrlApnRequest) -> CtrlBaseResponse:
    """APN 配置（危险动作）"""
    plan = _plan_apn(req)
    return _execute_plan("apn", plan, req, is_dangerous=True)


@router.get(
    "/roaming",
    response_model=RoamingResponse,
    summary="查询数据漫游状态",
    description='查询当前数据漫游是否开启（基于 AT+QNWPREFCFG="roam_pref"）。'
)
async def get_roaming() -> RoamingResponse:
    """查询数据漫游状态（使用 AT+QNWPREFCFG="roam_pref"）"""
    ts = int(time.time() * 1000)
    try:
        enabled, lines = _query_roam_pref()
        if enabled is None:
            return RoamingResponse(
                ok=False,
                ts=ts,
                error="Modem did not return roam_pref value (AT+QNWPREFCFG=\"roam_pref\" not supported).",
                roaming=RoamingState(enabled=False),
                raw=lines,
            )

        return RoamingResponse(
            ok=True,
            ts=ts,
            error=None,
            roaming=RoamingState(enabled=enabled),
            raw=lines,
        )
    except SerialATError as exc:
        return RoamingResponse(
            ok=False,
            ts=ts,
            error=str(exc),
            roaming=RoamingState(enabled=False),
            raw=None,
        )
    except Exception as exc:
        return RoamingResponse(
            ok=False,
            ts=ts,
            error=f"get_roaming failed: {exc}",
            roaming=RoamingState(enabled=False),
            raw=None,
        )


@router.post(
    "/roaming",
    response_model=RoamingResponse,
    summary="设置数据漫游开关",
    description='启用/禁用数据漫游（安全动作，可以执行）。使用 AT+QNWPREFCFG="roam_pref" 下发指令。'
)
async def ctrl_roaming(req: CtrlRoamingRequest) -> RoamingResponse:
    """设置数据漫游开关（安全动作）"""
    ts = int(time.time() * 1000)

    # dry_run 或 CTRL_ENABLE=0：仅返回计划与当前状态
    if req.dry_run or not CTRL_ENABLE:
        try:
            enabled, _ = _query_roam_pref()
        except SerialATError:
            enabled = None
        if enabled is None:
            enabled = False
        return RoamingResponse(
            ok=True,
            ts=ts,
            error=None if req.dry_run else "CTRL_ENABLE=0",
            roaming=RoamingState(enabled=enabled),
            raw=None,
        )

    try:
        pref_val = _bool_to_pref(req.enable)
        raw_lines = _at(f'AT+QNWPREFCFG="roam_pref",{pref_val}')
        enabled, confirm_lines = _query_roam_pref()
        if enabled is None:
            return RoamingResponse(
                ok=True,
                ts=ts,
                error="Roaming preference set but modem did not return confirmation.",
                roaming=RoamingState(enabled=req.enable),
                raw=raw_lines,
            )
        return RoamingResponse(
            ok=True,
            ts=ts,
            error=None,
            roaming=RoamingState(enabled=enabled),
            raw=confirm_lines,
        )
    except SerialATError as exc:
        return RoamingResponse(
            ok=False,
            ts=ts,
            error=str(exc),
            roaming=RoamingState(enabled=False),
            raw=None,
        )
    except Exception as exc:
        return RoamingResponse(
            ok=False,
            ts=ts,
            error=f"ctrl_roaming failed: {exc}",
            roaming=RoamingState(enabled=False),
            raw=None,
        )





@router.post(
    "/band",
    response_model=CtrlBaseResponse,
    summary="频段锁定",
    description="设置频段锁定（危险动作，默认只 dry_run）。可以锁定到指定的 LTE/NR5G 频段。需要设置 LINKSTATION_CTRL_ALLOW_DANGEROUS=1 才能执行。"
)
async def ctrl_band(req: CtrlBandRequest) -> CtrlBaseResponse:
    """频段锁定（危险动作）"""
    plan = _plan_band(req)
    return _execute_plan("band", plan, req, is_dangerous=True)


@router.post(
    "/cell_lock",
    response_model=CtrlBaseResponse,
    summary="小区锁定",
    description="锁定到指定小区/制式（危险动作，默认只 dry_run）。可以锁定到指定的 RAT、PCI 等。需要设置 LINKSTATION_CTRL_ALLOW_DANGEROUS=1 才能执行。"
)
async def ctrl_cell_lock(req: CtrlCellLockRequest) -> CtrlBaseResponse:
    """小区锁定（危险动作）"""
    plan = _plan_cell_lock(req)
    return _execute_plan("cell_lock", plan, req, is_dangerous=True)


@router.post(
    "/ca",
    response_model=CtrlBaseResponse,
    summary="CA 开关",
    description="启用/禁用载波聚合（安全动作，可以执行）。可以分别控制 LTE 和 NR5G 的 CA 功能。这是安全的设置命令，用于控制载波聚合功能。"
)
async def ctrl_ca(req: CtrlCaRequest) -> CtrlBaseResponse:
    """CA 开关（安全动作）"""
    plan = _plan_ca(req)
    return _execute_plan("ca", plan, req, is_dangerous=False)


@router.post(
    "/gnss",
    response_model=CtrlBaseResponse,
    summary="GNSS 控制",
    description="启用/禁用 GNSS（GPS/北斗等）功能（安全动作，可以执行）。当 dry_run=false 时会真正执行 AT 命令。"
)
async def ctrl_gnss(req: CtrlGnssRequest) -> CtrlBaseResponse:
    """GNSS 控制（安全动作）"""
    plan = _plan_gnss(req)
    return _execute_plan("gnss", plan, req, is_dangerous=False)


@router.get(
    "/network_mode",
    response_model=NetworkModeResponse,
    summary="查询网络模式",
    description='查询当前网络搜索模式（基于 AT+QNWPREFCFG="mode_pref"）。安全查询接口。'
)
async def get_network_mode() -> NetworkModeResponse:
    """查询网络模式（安全查询）"""
    ts = int(time.time() * 1000)
    try:
        mode_pref, lines = _query_mode_pref()
        if mode_pref is None:
            return NetworkModeResponse(
                ok=False,
                ts=ts,
                error="Modem did not return mode_pref value (AT+QNWPREFCFG=\"mode_pref\" not supported).",
                mode=NetworkModeState(mode_pref=None),
                raw=lines,
            )
        
        return NetworkModeResponse(
            ok=True,
            ts=ts,
            error=None,
            mode=NetworkModeState(mode_pref=mode_pref),
            raw=lines,
        )
    except SerialATError as exc:
        return NetworkModeResponse(
            ok=False,
            ts=ts,
            error=str(exc),
            mode=NetworkModeState(mode_pref=None),
            raw=None,
        )
    except Exception as exc:
        return NetworkModeResponse(
            ok=False,
            ts=ts,
            error=f"get_network_mode failed: {exc}",
            mode=NetworkModeState(mode_pref=None),
            raw=None,
        )


@router.post(
    "/network_mode",
    response_model=NetworkModeResponse,
    summary="设置网络模式",
    description='设置网络搜索模式（安全动作，可以执行）。使用 AT+QNWPREFCFG="mode_pref" 下发指令。支持AUTO、WCDMA、LTE、NR5G或组合模式（如LTE:NR5G）。'
)
async def ctrl_network_mode(req: CtrlNetworkModeRequest) -> NetworkModeResponse:
    """设置网络模式（安全动作）"""
    ts = int(time.time() * 1000)
    
    # dry_run 或 CTRL_ENABLE=0：仅返回计划与当前状态
    if req.dry_run or not CTRL_ENABLE:
        try:
            mode_pref, _ = _query_mode_pref()
        except SerialATError:
            mode_pref = None
        if mode_pref is None:
            mode_pref = "AUTO"  # 默认值
        return NetworkModeResponse(
            ok=True,
            ts=ts,
            error=None if req.dry_run else "CTRL_ENABLE=0",
            mode=NetworkModeState(mode_pref=mode_pref),
            raw=None,
        )
    
    try:
        # 如果指定了mode_pref，则设置
        if req.mode_pref is not None:
            raw_lines = _at(f'AT+QNWPREFCFG="mode_pref",{req.mode_pref}')
            # 查询确认
            mode_pref, confirm_lines = _query_mode_pref()
            if mode_pref is None:
                return NetworkModeResponse(
                    ok=True,
                    ts=ts,
                    error="Network mode preference set but modem did not return confirmation.",
                    mode=NetworkModeState(mode_pref=req.mode_pref),
                    raw=raw_lines,
                )
            return NetworkModeResponse(
                ok=True,
                ts=ts,
                error=None,
                mode=NetworkModeState(mode_pref=mode_pref),
                raw=confirm_lines,
            )
        else:
            # 仅查询
            mode_pref, lines = _query_mode_pref()
            if mode_pref is None:
                mode_pref = "AUTO"
            return NetworkModeResponse(
                ok=True,
                ts=ts,
                error=None,
                mode=NetworkModeState(mode_pref=mode_pref),
                raw=lines,
            )
    except SerialATError as exc:
        return NetworkModeResponse(
            ok=False,
            ts=ts,
            error=str(exc),
            mode=NetworkModeState(mode_pref=None),
            raw=None,
        )
    except Exception as exc:
        return NetworkModeResponse(
            ok=False,
            ts=ts,
            error=f"ctrl_network_mode failed: {exc}",
            mode=NetworkModeState(mode_pref=None),
            raw=None,
        )


@router.get(
    "/band_preference",
    response_model=BandPreferenceResponse,
    summary="查询频段偏好",
    description='查询当前频段搜索偏好（基于 AT+QNWPREFCFG="lte_band"/"nsa_nr5g_band"/"nr5g_band"）。安全查询接口。'
)
async def get_band_preference() -> BandPreferenceResponse:
    """查询频段偏好（安全查询）"""
    ts = int(time.time() * 1000)
    try:
        lte_bands, nsa_bands, nr5g_bands, raw_dict = _query_band_preference()
        
        # 合并所有原始回显
        all_raw = []
        for cmd, lines in raw_dict.items():
            all_raw.extend(lines)
        
        return BandPreferenceResponse(
            ok=True,
            ts=ts,
            error=None,
            bands=BandPreferenceState(
                lte_bands=lte_bands,
                nsa_nr5g_bands=nsa_bands,
                nr5g_bands=nr5g_bands,
            ),
            raw=all_raw if all_raw else None,
        )
    except SerialATError as exc:
        return BandPreferenceResponse(
            ok=False,
            ts=ts,
            error=str(exc),
            bands=BandPreferenceState(),
            raw=None,
        )
    except Exception as exc:
        return BandPreferenceResponse(
            ok=False,
            ts=ts,
            error=f"get_band_preference failed: {exc}",
            bands=BandPreferenceState(),
            raw=None,
        )


@router.post(
    "/band_preference",
    response_model=BandPreferenceResponse,
    summary="设置频段偏好",
    description='设置频段搜索偏好（安全动作，可以执行）。使用 AT+QNWPREFCFG="lte_band"/"nsa_nr5g_band"/"nr5g_band" 下发指令。这是频段偏好设置（非锁定），模组会优先搜索指定的频段。'
)
async def ctrl_band_preference(req: CtrlBandPreferenceRequest) -> BandPreferenceResponse:
    """设置频段偏好（安全动作）"""
    ts = int(time.time() * 1000)
    
    # dry_run 或 CTRL_ENABLE=0：仅返回计划与当前状态
    if req.dry_run or not CTRL_ENABLE:
        try:
            lte_bands, nsa_bands, nr5g_bands, _ = _query_band_preference()
        except SerialATError:
            lte_bands = nsa_bands = nr5g_bands = None
        return BandPreferenceResponse(
            ok=True,
            ts=ts,
            error=None if req.dry_run else "CTRL_ENABLE=0",
            bands=BandPreferenceState(
                lte_bands=lte_bands,
                nsa_nr5g_bands=nsa_bands,
                nr5g_bands=nr5g_bands,
            ),
            raw=None,
        )
    
    try:
        plan = _plan_band_preference(req)
        all_raw = []
        
        # 执行计划中的命令
        for cmd in plan:
            try:
                logger.info("[band_preference] sending %s", cmd)
                lines = serial_at.send(cmd)
                logger.info("[band_preference] response lines for %s: %s", cmd, lines)
                all_raw.extend(lines)
            except Exception as e:
                error_msg = str(e)
                all_raw.append(f"ERROR: {error_msg}")
        
        # 查询确认
        lte_bands, nsa_bands, nr5g_bands, confirm_dict = _query_band_preference()
        for cmd, lines in confirm_dict.items():
            all_raw.extend(lines)
        
        return BandPreferenceResponse(
            ok=True,
            ts=ts,
            error=None,
            bands=BandPreferenceState(
                lte_bands=lte_bands,
                nsa_nr5g_bands=nsa_bands,
                nr5g_bands=nr5g_bands,
            ),
            raw=all_raw if all_raw else None,
        )
    except SerialATError as exc:
        return BandPreferenceResponse(
            ok=False,
            ts=ts,
            error=str(exc),
            bands=BandPreferenceState(),
            raw=None,
        )
    except Exception as exc:
        return BandPreferenceResponse(
            ok=False,
            ts=ts,
            error=f"ctrl_band_preference failed: {exc}",
            bands=BandPreferenceState(),
            raw=None,
        )


@router.post(
    "/reset_profile",
    response_model=CtrlBaseResponse,
    summary="一键恢复网络默认配置",
    description="一键恢复网络相关配置到默认安全状态（modem_safe profile）。包括：恢复频段为全频、解除小区锁、打开CA、恢复数据漫游、恢复USBNET为默认模式。不修改APN/GNSS。危险动作，默认只dry_run。需要设置LINKSTATION_CTRL_ALLOW_DANGEROUS=1才能执行。"
)
async def ctrl_reset_profile(req: CtrlResetProfileRequest) -> CtrlBaseResponse:
    """
    一键恢复网络相关配置到默认安全状态（modem_safe profile）。
    - 恢复 band（LTE/NR5G）为默认全频
    - 解除小区锁
    - 打开 CA
    - 恢复数据漫游为默认值
    - 恢复 USBNET 为 demo 默认模式
    不修改 APN / GNSS / NV。
    """
    plan = _plan_reset_profile(req)
    return _execute_plan("reset_profile", plan, req, is_dangerous=True)
