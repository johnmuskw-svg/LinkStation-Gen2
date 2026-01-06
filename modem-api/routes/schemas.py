from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any, Literal
import time

from pydantic.config import ConfigDict


class InfoModel(BaseModel):
    manufacturer: Optional[str] = Field(
        None, description="厂商名（AT+GMI）示例：'Quectel'"
    )
    model: Optional[str] = Field(
        None, description="模组型号（AT+CGMM）示例：'RM520N-CN'"
    )
    revision: Optional[str] = Field(
        None, description="固件版本（AT+GMR）示例：'RM520NCNAAR05A03M4G'"
    )
    imei: Optional[str] = Field(
        None, description="IMEI（AT+GSN）15位数字"
    )


class SimModel(BaseModel):
    imsi: Optional[str] = Field(None, description="IMSI（AT+CIMI）")
    iccid: Optional[str] = Field(None, description="ICCID（AT+ICCID）")
    msisdn: Optional[str] = Field(
        None, description="本机号码/MDN（AT+CNUM），可能为空"
    )
    enabled: Optional[bool] = Field(
        None, description="是否启用SIM插拔上报（AT+QSIMSTAT? 第一位 1/0）"
    )
    inserted: Optional[bool] = Field(
        None, description="当前是否检测到SIM插入（AT+QSIMSTAT? 第二位 1/0）"
    )


class UsbSpeedModel(BaseModel):
    code: Optional[int] = Field(
        None,
        description='USB 模式代码 [AT+QCFG="usbspeed"]：20=USB 2.0 (480Mbps), 311=USB 3.1 Gen1 (5Gbps), 312=USB 3.1 Gen2 (10Gbps)',
    )
    label: Optional[str] = Field(None, description="人类可读说明")


class ModemModel(BaseModel):
    usb: Optional[UsbSpeedModel] = Field(
        None, description='USB速率模式（AT+QCFG="usbspeed"）'
    )


class InfoResponse(BaseModel):
    ok: bool = Field(True, description="调用是否成功")
    ts: int = Field(..., description="毫秒级时间戳")
    error: Optional[str] = Field(None, description="错误信息（成功时为 None）")
    info: InfoModel = Field(default_factory=InfoModel)
    sim: SimModel = Field(default_factory=SimModel)
    modem: ModemModel = Field(default_factory=ModemModel)
    raw: Optional[Dict[str, List[str]]] = Field(
        None, description="仅在 ?verbose=1 时返回：AT 原始回显"
    )

# routes/schemas.py  —— 仅 live 模块所需模型（Pydantic v2）

class LiveRegModel(BaseModel):
    cs: Optional[str] = Field(None, description="电路域注册状态(保留)")
    ps: Optional[str] = Field(None, description="分组域注册状态")

class LiveModeModel(BaseModel):
    rat: Optional[str] = Field(None, description="接入制式: SA/LTE/NSA/…")
    duplex: Optional[str] = Field(None, description="TDD/FDD")

class LiveOperatorModel(BaseModel):
    name: Optional[str] = Field(None, description="运营商标识(如 46000)")
    mcc: Optional[str] = Field(None, description="MCC 字符串")
    mnc: Optional[str] = Field(None, description="MNC 字符串")

class LiveSignalModel(BaseModel):
    rsrp: Optional[int] = None
    rsrq: Optional[int] = None
    rssi: Optional[int] = None
    sinr: Optional[int] = None
    cqi: Optional[int] = None

class SignalBlock(BaseModel):
    rssi: Optional[str] = None
    rsrp: Optional[str] = None
    rsrq: Optional[str] = None
    sinr: Optional[str] = None
    quality: Optional[str] = None   # excellent/good/fair/poor
    note: Optional[str] = None      # 可选备注

class ServingSA(BaseModel):
    model_config = ConfigDict(extra="ignore")
    state: Optional[str] = None
    duplex: Optional[str] = None
    mcc: Optional[str] = None
    mnc: Optional[str] = None
    cellid: Optional[int] = None               # 5G 36-bit CellID -> int
    pcid: Optional[int] = None
    tac: Optional[str] = None                  # 你现场 schema 期望是 str
    nrarfcn: Optional[int] = None
    band: Optional[str] = None                 # "NR5G BAND 41"
    dl_bw_mhz: Optional[int] = None
    rsrp: Optional[int] = None
    rsrq: Optional[int] = None
    sinr: Optional[int] = None
    scs_khz: Optional[int] = None
    srxlev: Optional[int] = None

class ServingLTE(BaseModel):
    model_config = ConfigDict(extra="ignore")
    # 预留，暂为空
    pass

class ServingNSA_NRPart(BaseModel):
    model_config = ConfigDict(extra="ignore")
    # 预留，暂为空
    pass

class ServingNSA(BaseModel):
    model_config = ConfigDict(extra="ignore")
    # 预留，暂为空
    pass

class RegStatus(BaseModel):
    eps: Optional[int] = None       # from +CEREG? stat
    nr5g: Optional[int] = None      # from +C5GREG? stat
    eps_text: Optional[str] = None  # 1=registered... 人类可读
    nr5g_text: Optional[str] = None

class CellIdNorm(BaseModel):
    # 输入可来自 QENG/CEREG/C5GREG 混合；全部可选
    tac_hex: Optional[str] = None
    tac_dec: Optional[int] = None
    eci_hex: Optional[str] = None       # LTE E-UTRAN Cell Identity（常见28位）
    eci_dec: Optional[int] = None
    enb_id: Optional[int] = None        # eNB/gNB 拆分后的基站ID（LTE）
    cell_id: Optional[int] = None       # 小区内Cell ID（LTE）
    nci_hex: Optional[str] = None       # NR Cell Identity（常见36位）
    nci_dec: Optional[int] = None
    gnb_id: Optional[int] = None        # gNB 基站ID（NR）
    nci_cell_id: Optional[int] = None   # NR小区ID
    rat: Optional[str] = None           # "LTE" / "NR5G-NSA" / "NR5G-SA" …

class LiveServingModel(BaseModel):
    rat: Optional[str] = None
    sa: Optional[ServingSA] = None
    lte: Optional[ServingLTE] = None
    nsa: Optional[ServingNSA] = None
    nsa_nr: Optional[ServingNSA_NRPart] = None
    band: Optional[str] = None
    arfcn: Optional[str] = None
    pci: Optional[str] = None
    # 规范化后的ID放这里
    id: Optional[CellIdNorm] = None

# ===== Step6: Neighbors & CA models (auto-added) =====
class NbLTE(BaseModel):
    earfcn: int
    pci: int
    rsrp: Optional[int] = None
    rsrq: Optional[int] = None
    sinr: Optional[int] = None
    srxlev: Optional[int] = None

class NbNR(BaseModel):
    nrarfcn: int
    pci: int
    rsrp: Optional[int] = None
    rsrq: Optional[int] = None
    sinr: Optional[int] = None
    scs_khz: Optional[int] = None

class LiveNeighborsModel(BaseModel):
    lte: List[NbLTE] = []
    nr:  List[NbNR]  = []

class CA_Pcc(BaseModel):
    rat: Optional[str] = None      # "LTE"/"NR"
    arfcn: Optional[int] = None
    dl_bw_mhz: Optional[int] = None
    band: Optional[str] = None
    rsrp: Optional[int] = None
    rsrq: Optional[int] = None
    sinr: Optional[int] = None

class CA_Scc(CA_Pcc):
    idx: int

class LiveCAInfoModel(BaseModel):
    pcc: Optional[CA_Pcc] = None
    scc: List[CA_Scc] = []
    summary: Optional[str] = None
# ===== /Step6 =====

class LiveResponse(BaseModel):
    ok: bool = True
    ts: int = Field(..., description="毫秒时间戳")
    error: Optional[str] = Field(None, description="错误信息（成功时为 None）")
    reg: LiveRegModel = Field(default_factory=LiveRegModel)
    mode: LiveModeModel = Field(default_factory=LiveModeModel)
    operator: LiveOperatorModel = Field(default_factory=LiveOperatorModel)
    signal: LiveSignalModel = Field(default_factory=LiveSignalModel)
    serving: LiveServingModel = Field(default_factory=LiveServingModel)
    neighbors: LiveNeighborsModel = Field(default_factory=LiveNeighborsModel)
    ca: LiveCAInfoModel = Field(default_factory=LiveCAInfoModel)
    temps: Optional[Dict[str, Any]] = None
    neighbours: List[NeighbourCell] = Field(default_factory=list)
    netdev: Optional[LiveNetDev] = None
    session: Optional[LiveSessionModel] = None
    reg_detail: Optional[RegStatus] = None
    serving_norm: Optional[LiveServingModel] = None
    signal_lte: Optional[SignalBlock] = None
    signal_nr: Optional[SignalBlock] = None
    raw: Optional[Dict[str, List[str]]] = None

class NeighbourCell(BaseModel):
    rat: Optional[str] = None
    mode: Optional[str] = None
    mcc: Optional[int] = None
    mnc: Optional[int] = None
    tac: Optional[str] = None
    ci: Optional[str] = None
    pci: Optional[int] = None
    earfcn: Optional[int] = None
    nrarfcn: Optional[int] = None
    band: Optional[str] = None
    rsrp: Optional[int] = None
    rsrq: Optional[int] = None
    rssi: Optional[int] = None
    sinr: Optional[int] = None

class LiveNetDev(BaseModel):
    iface: Optional[str] = None
    state: Optional[str] = None
    ipv4: Optional[str] = None
    rx_bytes: Optional[int] = None
    tx_bytes: Optional[int] = None
    rx_rate_bps: Optional[int] = None
    tx_rate_bps: Optional[int] = None

class PDPContext(BaseModel):
    cid: int
    type: Optional[str] = None   # e.g. "IP","IPV6","IPV4V6"
    apn: Optional[str] = None
    state: Optional[int] = None  # 0/1 from CGACT
    ip: Optional[str] = None     # IPv4/IPv6/IPv4v6 任一
    dns1: Optional[str] = None
    dns2: Optional[str] = None

class LiveSessionModel(BaseModel):
    default_cid: Optional[int] = None
    pdp: List[PDPContext] = []

# ===== Step-2: Control API Models =====

class CtrlBaseRequest(BaseModel):
    """所有控制请求的基类，包含 dry_run 字段"""
    dry_run: bool = False


class CtrlActionDetail(BaseModel):
    """统一的控制动作详情结构"""
    dry_run: bool
    dangerous: bool
    executed: bool
    blocked_reason: Optional[str] = None
    planned: List[str] = []
    errors: List[str] = []
    extra: Optional[Dict[str, Any]] = None


class CtrlBaseResponse(BaseModel):
    ok: bool = True
    ts: int = Field(default_factory=lambda: int(time.time() * 1000))
    action: str
    error: Optional[str] = None
    # 未来放 AT 回显：{ "AT+XXX": ["AT+XXX", "...", "OK"] }
    raw: Optional[Dict[str, List[str]]] = None
    # 每个动作专属的内容（统一使用 CtrlActionDetail）
    detail: CtrlActionDetail


# 模组重启
class CtrlRebootRequest(CtrlBaseRequest):
    mode: str = Field("soft", description="soft|full|rf_off")


# USBNet 切换
class CtrlUsbNetRequest(CtrlBaseRequest):
    mode: str = Field(..., description="rndis|ecm|mbim 等")
    reboot_modem: bool = False


# APN/PDP 配置
class CtrlApnAuth(BaseModel):
    type: str = Field("none", description="none|pap|chap")
    user: Optional[str] = None
    password: Optional[str] = None


class CtrlApnRequest(CtrlBaseRequest):
    cid: int = 1
    apn: str
    pdp_type: str = Field("IPV4V6", description="IP|IPV6|IPV4V6")
    auth: CtrlApnAuth = CtrlApnAuth()
    activate: bool = True


# 漫游开关
class CtrlRoamingRequest(CtrlBaseRequest):
    enable: bool


# Band 偏好（软锁频段）
class CtrlBandRequest(CtrlBaseRequest):
    rat: str = Field("BOTH", description="LTE|NR5G|BOTH")
    lte_bands: Optional[List[str]] = None
    nr_bands: Optional[List[str]] = None
    reset: bool = False


# 小区锁定（工程用）
class CtrlCellLockRequest(CtrlBaseRequest):
    enable: bool
    rat: Optional[str] = None
    pci: Optional[int] = None
    tac: Optional[str] = Field(None, description="十六进制 TAC，如 '0800'")
    cell_id: Optional[str] = None


# CA 开关
class CtrlCaRequest(CtrlBaseRequest):
    lte_ca_enable: Optional[bool] = None
    nr_ca_enable: Optional[bool] = None


# GNSS 控制
class CtrlGnssRequest(CtrlBaseRequest):
    enable: bool
    mode: Optional[str] = Field(None, description="standalone|assisted 等")
    cold_start: bool = False


# 一键恢复网络默认配置
class CtrlResetProfileRequest(CtrlBaseRequest):
    """
    一键恢复网络默认配置。
    目前只支持一个 profile: "modem_safe"。
    将 band / CA / 小区锁 / roaming / usbnet 重置为安全默认值。
    APN / GNSS 暂时不动。
    """
    profile: Literal["modem_safe"] = "modem_safe"


# 网络模式选择
class CtrlNetworkModeRequest(CtrlBaseRequest):
    """
    网络模式选择请求。
    用于设置模组的上网模式偏好（AUTO/WCDMA/LTE/NR5G等）。
    """
    mode_pref: Optional[str] = Field(
        None,
        description='网络搜索模式：AUTO（自动）、WCDMA（仅WCDMA）、LTE（仅LTE）、NR5G（仅5G），或组合如"LTE:NR5G"（LTE和5G）。查询时省略此字段。'
    )


# 频段偏好设置（区别于频段锁定）
class CtrlBandPreferenceRequest(CtrlBaseRequest):
    """
    频段偏好设置请求。
    用于设置频段搜索偏好（非锁定），模组会优先搜索指定的频段。
    """
    lte_bands: Optional[List[int]] = Field(
        None,
        description="LTE频段列表（整数列表，如[1,3,7]表示B1、B3、B7）。设置为空列表或null表示使用所有支持的频段。"
    )
    nsa_nr5g_bands: Optional[List[int]] = Field(
        None,
        description="5G NSA频段列表（整数列表，如[1,41,78]表示n1、n41、n78）。设置为空列表或null表示使用所有支持的频段。"
    )
    nr5g_bands: Optional[List[int]] = Field(
        None,
        description="5G SA频段列表（整数列表，如[1,41,78]表示n1、n41、n78）。设置为空列表或null表示使用所有支持的频段。"
    )


# ===== 网络模式查询响应模型 =====
class NetworkModeState(BaseModel):
    mode_pref: Optional[str] = Field(None, description="当前网络搜索模式，如AUTO、LTE、NR5G、LTE:NR5G等")


class NetworkModeResponse(BaseModel):
    ok: bool = Field(True, description="调用是否成功")
    ts: int = Field(..., description="毫秒级时间戳")
    error: Optional[str] = Field(None, description="错误信息（成功时为 None）")
    mode: NetworkModeState = Field(..., description="网络模式状态")
    raw: Optional[List[str]] = Field(None, description="原始 AT 回显行列表（可选）")


# ===== 频段偏好查询响应模型 =====
class BandPreferenceState(BaseModel):
    lte_bands: Optional[List[int]] = Field(None, description="当前LTE频段偏好列表")
    nsa_nr5g_bands: Optional[List[int]] = Field(None, description="当前5G NSA频段偏好列表")
    nr5g_bands: Optional[List[int]] = Field(None, description="当前5G SA频段偏好列表")


class BandPreferenceResponse(BaseModel):
    ok: bool = Field(True, description="调用是否成功")
    ts: int = Field(..., description="毫秒级时间戳")
    error: Optional[str] = Field(None, description="错误信息（成功时为 None）")
    bands: BandPreferenceState = Field(..., description="频段偏好状态")
    raw: Optional[List[str]] = Field(None, description="原始 AT 回显行列表（可选）")


# ===== 漫游查询响应模型 =====
class RoamingState(BaseModel):
    enabled: bool = Field(..., description="数据漫游是否开启")


class RoamingResponse(BaseModel):
    ok: bool = Field(True, description="调用是否成功")
    ts: int = Field(..., description="毫秒级时间戳")
    error: Optional[str] = Field(None, description="错误信息（成功时为 None）")
    roaming: RoamingState = Field(..., description="漫游状态")
    raw: Optional[List[str]] = Field(None, description="原始 AT 回显行列表（可选）")


# ===== 上网出口切换请求/响应模型 =====
class UplinkRequest(BaseModel):
    mode: Literal["sim", "wifi"] = Field(..., description="上网出口模式：sim=SIM卡优先，wifi=Wi-Fi优先")


class UplinkResponse(BaseModel):
    ok: bool = Field(True, description="调用是否成功")
    ts: int = Field(..., description="毫秒级时间戳")
    error: Optional[str] = Field(None, description="错误信息（成功时为 None）")
    mode: Optional[Literal["sim", "wifi"]] = Field(None, description="当前或设置后的上网出口模式")
    default_route: Optional[str] = Field(None, description="当前默认路由信息（ip route 输出）")
