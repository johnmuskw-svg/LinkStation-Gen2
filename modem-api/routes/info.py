from fastapi import APIRouter, Query
from typing import List, Dict, Optional,Tuple
from core.serial_port import serial_at, SerialATError
from routes.schemas import InfoResponse, InfoModel, SimModel, ModemModel, UsbSpeedModel
import re
import time
import traceback


router = APIRouter(tags=["info"])

# ---- 工具/解析 ----

def _at(cmd: str) -> List[str]:
    """统一发送 AT，返回行数组（含 'AT+Xxx' 与 'OK' 行）"""
    return serial_at.send(cmd)

def _first_payload_line(lines: List[str]) -> Optional[str]:
    """取第一条有效负载行：跳过 'AT...' 与 'OK' 与空行"""
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("AT+"):
            continue
        if s == "OK":
            continue
        return s
    return None

def _parse_iccid(lines: List[str]) -> Optional[str]:
    # 形如：+ICCID: 8986...
    for ln in lines:
        m = re.search(r"\+ICCID:\s*([0-9A-Fa-f]+)", ln)
        if m:
            return m.group(1)
    return None

def _parse_cnum(lines: List[str]) -> Optional[str]:
    """
    兼容以下几种常见回显：
      +CNUM: "alpha","+8613xxxx",145
      +CNUM: ,"+8613xxxx",145
      +CNUM: "+8613xxxx",145
      +CNUM: "alpha", "+8613xxxx", 161
    取第一条号码返回（若多条）。
    """
    for ln in lines:
        s = ln.strip()
        # 形式1: +CNUM: "alpha", "number", type
        m = re.search(r'\+CNUM:\s*"[^"]*"\s*,\s*"([^"]+)"\s*,\s*\d+', s)
        if m:
            return m.group(1).strip()

        # 形式2: +CNUM: , "number", type   （alpha 为空）
        m = re.search(r'\+CNUM:\s*,\s*"([^"]+)"\s*,\s*\d+', s)
        if m:
            return m.group(1).strip()

        # 形式3: +CNUM: "number", type     （只有号码+类型）
        m = re.search(r'\+CNUM:\s*"([^"]+)"\s*,\s*\d+', s)
        if m:
            return m.group(1).strip()

    return None

USB_SPEED_LABELS: Dict[str, str] = {
    "20":  "USB 2.0 high speed, 480 Mbps",
    "311": "USB 3.1 Gen1, 5 Gbps",
    "312": "USB 3.1 Gen2, 10 Gbps",
}

def _parse_usbspeed(lines: List[str]) -> Optional[str]:
    # 形如：+QCFG: "usbspeed","312"
    for ln in lines:
        m = re.search(r'\+QCFG:\s*"usbspeed"\s*,\s*"([^"]+)"', ln)
        if m:
            return m.group(1)
    return None

def _parse_qsimstat(lines: List[str]) -> Tuple[Optional[bool], Optional[bool]]:
    # 形如：+QSIMSTAT: 1,1
    for ln in lines:
        m = re.search(r"\+QSIMSTAT:\s*(\d)\s*,\s*(\d)", ln)
        if m:
            enabled = (m.group(1) == "1")
            inserted = (m.group(2) == "1")
            return enabled, inserted
    return None, None


@router.get("/info", response_model=InfoResponse)
def get_info(verbose: bool = Query(False, description="是否返回 raw 原始AT回显（1/true 开启）")):
    ts = int(time.time() * 1000)
    try:
        # --- 执行 AT 指令 ---
        gmi   = _at("AT+GMI")
        cgmm  = _at("AT+CGMM")
        gmr   = _at("AT+GMR")
        gsn   = _at("AT+GSN")
        cimi  = _at("AT+CIMI")
        iccid = _at("AT+ICCID")
        cnum  = _at("AT+CNUM")
        qsim  = _at("AT+QSIMSTAT?")
        usbspeed_raw = _at('AT+QCFG="usbspeed"')

        # --- 解析展示字段 ---
        info = InfoModel(
            manufacturer=_first_payload_line(gmi),
            model=_first_payload_line(cgmm),
            revision=_first_payload_line(gmr),
            imei=_first_payload_line(gsn),
        )

        sim_enabled, sim_inserted = _parse_qsimstat(qsim)
        sim = SimModel(
            imsi=_first_payload_line(cimi),
            iccid=_parse_iccid(iccid),
            msisdn=_parse_cnum(cnum),
            enabled=sim_enabled,
            inserted=sim_inserted,
        )

        usb_code_str = _parse_usbspeed(usbspeed_raw)
        usb_code = int(usb_code_str) if usb_code_str and usb_code_str.isdigit() else None
        modem = ModemModel(
            usb=UsbSpeedModel(
                code=usb_code,
                label=USB_SPEED_LABELS.get(usb_code_str) if usb_code_str else None,
            )
        )

        raw_payload = None
        if verbose:
            raw_payload = {
                "AT+GMI": gmi,
                "AT+CGMM": cgmm,
                "AT+GMR": gmr,
                "AT+GSN": gsn,
                "AT+CIMI": cimi,
                "AT+ICCID": iccid,
                "AT+CNUM": cnum,
                'AT+QCFG="usbspeed"': usbspeed_raw,
                "AT+QSIMSTAT?": qsim,
            }

        return InfoResponse(
            ok=True,
            ts=ts,
            error=None,
            info=info,
            sim=sim,
            modem=modem,
            raw=raw_payload,
        )
    except SerialATError as exc:
        return InfoResponse(
            ok=False,
            ts=ts,
            error=str(exc),
            info=InfoModel(),
            sim=SimModel(),
            modem=ModemModel(),
            raw=None,
        )
    except Exception as exc:
        traceback.print_exc()
        return InfoResponse(
            ok=False,
            ts=ts,
            error=f"info failed: {exc}",
            info=InfoModel(),
            sim=SimModel(),
            modem=ModemModel(),
            raw=None,
        )