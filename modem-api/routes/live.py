# routes/live.py
from fastapi import APIRouter, Query
from typing import List, Optional, Tuple, Dict
from core.serial_port import serial_at, SerialATError
from routes.schemas import (
    LiveResponse,
    LiveRegModel, LiveModeModel, LiveOperatorModel, LiveSignalModel,
    LiveNeighborsModel, LiveCAInfoModel, LiveServingModel,
    ServingSA, ServingLTE, ServingNSA, ServingNSA_NRPart, CA_Pcc, CA_Scc, NbLTE, NbNR,
    NeighbourCell, LiveNetDev, LiveSessionModel, PDPContext,
    RegStatus, CellIdNorm, SignalBlock
)
from routes.serving_parsers import (
    parse_qtemp_lines, parse_qcainfo, parse_qcainfo_scc, parse_qeng_scc_from_serving, 
    parse_qeng_neighbour, build_ca_summary, parse_qnetdevstatus, probe_sys_netdev, with_rates, 
    parse_cgdcont, parse_cgact, parse_cgcontrdp, parse_qidnscfg,
    reg_text, parse_cereg_stat, parse_c5greg_stat, parse_qeng_serving_core, 
    _try_int_hex, _split_lte_eci, _split_nr_nci, pretty_band,
    rate_quality_lte, rate_quality_nr
)
import re
import time
import traceback

router = APIRouter(tags=["live"])

# --- runtime safe helpers ---
def _to_dict_or_default(obj, default):
    try:
        if obj is None:
            return default
        md = getattr(obj, 'model_dump', None)
        return md() if callable(md) else obj
    except Exception:
        return default


# --- 通用响应兜底 ---
def _live_error_response(ts: int, message: str) -> LiveResponse:
    return LiveResponse(
        ok=False,
        ts=ts,
        error=message,
        reg=LiveRegModel(),
        mode=LiveModeModel(),
        operator=LiveOperatorModel(),
        signal=LiveSignalModel(),
        serving=LiveServingModel(),
        neighbors=LiveNeighborsModel(lte=[], nr=[]),
        ca=LiveCAInfoModel(),
        temps=None,
        neighbours=[],
        netdev=None,
        session=None,
        reg_detail=None,
        serving_norm=None,
        signal_lte=None,
        signal_nr=None,
        raw=None,
    )


# ---------- 串口与工具 ----------

def _at(cmd: str) -> List[str]:
    return serial_at.send(cmd)

def _first_payload_line(lines: List[str]) -> Optional[str]:
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("AT+") or s == "OK":
            continue
        return s
    return None

def _find_line(lines: List[str], prefix: str) -> Optional[str]:
    for ln in lines:
        s = ln.strip()
        if s.startswith(prefix):
            return s
    return None

def _split_csv(line: str) -> List[str]:
    if ":" in line:
        line = line.split(":", 1)[1].strip()
    toks = re.findall(r'"[^"]*"|[^,]+', line)
    return [t.strip().strip('"') for t in toks]

def _to_int(s: Optional[str]) -> Optional[int]:
    if s is None or s == "":
        return None
    try:
        return int(s)
    except Exception:
        return None

def _to_int_hex(s: Optional[str]) -> Optional[int]:
    if s is None or s == "":
        return None
    try:
        # 兼容纯 16 进制/带 0x
        return int(s, 16) if re.fullmatch(r"[0-9A-Fa-f]+", s) else int(s, 0)
    except Exception:
        return None

def _v(x: Optional[int]) -> Optional[int]:
    return None if (x is None or x == -32768) else x

# === NEW HELPERS (robust casting & small utils) ===
def _to_int_or_none(v):
    try:
        if v is None:
            return None
        iv = int(str(v).strip())
        if iv in (-32768, -32767):
            return None
        return iv
    except Exception:
        return None


def _find_token_index(toks, *keys):
    up = [str(x).upper() for x in toks]
    for k in keys:
        k = str(k).upper()
        if k in up:
            return up.index(k)
    return None

_SCS_CODE_TO_KHZ = {0: 15, 1: 30, 2: 60, 3: 120, 4: 240}

def _split_csv_tokens(payload: str) -> List[str]:
    s = payload.strip()
    tokens: List[str] = []
    buf: List[str] = []
    in_quote = False
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == '"':
            # 处理转义的双引号 "" -> 一个双引号
            if i + 1 < n and s[i + 1] == '"':
                buf.append('"')
                i += 2
                continue
            in_quote = not in_quote
            i += 1
            continue
        if ch == ',' and not in_quote:
            tokens.append(''.join(buf).strip())
            buf.clear()
            i += 1
            continue
        buf.append(ch)
        i += 1
    # 收尾
    tokens.append(''.join(buf).strip())

    # 去掉外围引号，例如 "LTE" -> LTE；空串保持为空
    cleaned: List[str] = []
    for t in tokens:
        t = t.strip()
        if len(t) >= 2 and t[0] == '"' and t[-1] == '"':
            t = t[1:-1]
        cleaned.append(t)
    return cleaned

# ---------- 解析 ----------

def _parse_cgreg(lines: List[str]) -> LiveRegModel:
    s = _find_line(lines, "+CGREG:")
    ps = None
    if s:
        toks = _split_csv(s)
        if len(toks) >= 2:
            stat = _to_int(toks[1])
            mp = {
                0: "not_registered",
                1: "home",
                2: "searching",
                3: "denied",
                4: "unknown",
                5: "roaming",
            }
            ps = mp.get(stat, None)
    return LiveRegModel(cs=None, ps=ps)

def _parse_qnwinfo(lines: List[str]) -> Tuple[LiveModeModel, LiveOperatorModel]:
    s = _find_line(lines, "+QNWINFO:")
    rat = None
    duplex = None
    oper_name = None
    if s:
        toks = _split_csv(s)
        if toks:
            rat_full = (toks[0] or "").upper()
            if "NR5G" in rat_full and "TDD" in rat_full:
                rat, duplex = "SA", "TDD"
            elif "NR5G" in rat_full and "FDD" in rat_full:
                rat, duplex = "SA", "FDD"
            elif "LTE" in rat_full:
                rat, duplex = "LTE", None
            else:
                rat = "SA" if "NR5G" in rat_full else rat_full or None
            if len(toks) >= 2:
                oper_name = toks[1] or None
    return LiveModeModel(rat=rat, duplex=duplex), LiveOperatorModel(name=oper_name, mcc=None, mnc=None)

def _parse_qrsrp(lines: List[str]) -> Optional[int]:
    s = _find_line(lines, "+QRSRP:")
    if not s:
        return None
    toks = _split_csv(s)
    return _v(_to_int(toks[0] if toks else None))

def _parse_qrsrq(lines: List[str]) -> Optional[int]:
    s = _find_line(lines, "+QRSRQ:")
    if not s:
        return None
    toks = _split_csv(s)
    return _v(_to_int(toks[0] if toks else None))

def _parse_qsinr(lines: List[str]) -> Optional[int]:
    s = _find_line(lines, "+QSINR:")
    if not s:
        return None
    toks = _split_csv(s)
    return _v(_to_int(toks[0] if toks else None))

def _parse_qeng_serving_sa(lines: List[str]) -> Tuple[str, Optional[ServingSA], Optional[str], Optional[str], Optional[str]]:
    """
    +QENG: "servingcell","<state>","NR5G-SA","<duplex>","<MCC>","<MNC>","<cellID>","<PCID>",<TAC>,<ARFCN>,<band>,<NR_DL_bw>,<RSRP>,<RSRQ>,<SINR>,<scs>,<srxlev>
    返回: (rat, sa_obj, mcc, mnc, duplex)
    """
    s = _find_line(lines, '+QENG: "servingcell"')
    if not s:
        return "UNKNOWN", None, None, None, None

    toks = _split_csv(s)
    if len(toks) < 17:
        return "UNKNOWN", None, None, None, None

    state   = toks[1] or None
    rat_str = (toks[2] or "").upper()
    if "NR5G" not in rat_str:
        return "UNKNOWN", None, None, None, None

    duplex  = toks[3] or None
    mcc_str = toks[4] or None
    mnc_str = toks[5] or None
    cellid  = _to_int_hex(toks[6])
    pcid    = _to_int(toks[7])
    tac_str = toks[8] or None                  # 你的 schema 里 tac= str
    nrarfcn = _to_int(toks[9])
    band    = toks[10] or None
    dl_bw   = _to_int(toks[11])
    rsrp    = _v(_to_int(toks[12]))
    rsrq    = _v(_to_int(toks[13]))
    sinr    = _v(_to_int(toks[14]))
    scs_khz = _SCS_CODE_TO_KHZ.get(_to_int(toks[15]), None)
    srxlev  = _to_int(toks[16])

    sa_obj = ServingSA(
        state=state, duplex=duplex, mcc=mcc_str, mnc=mnc_str,
        cellid=cellid, pcid=pcid, tac=tac_str, nrarfcn=nrarfcn, band=band,
        dl_bw_mhz=dl_bw, rsrp=rsrp, rsrq=rsrq, sinr=sinr, scs_khz=scs_khz, srxlev=srxlev
    )
    return "SA", sa_obj, mcc_str, mnc_str, duplex

# ---------- 路由 ----------

@router.get("/live", response_model=LiveResponse)
def get_live(verbose: bool = Query(False, description="是否返回 raw 原始AT回显(1/true 开启)")):
    ts = int(time.time() * 1000)
    try:
        return _build_live_response(verbose, ts)
    except SerialATError as exc:
        return _live_error_response(ts, str(exc))
    except Exception as exc:
        traceback.print_exc()
        return _live_error_response(ts, f"live failed: {exc}")


def _build_live_response(verbose: bool, ts: int) -> LiveResponse:
    # 1. AT 指令
    cgreg   = _at("AT+CGREG?")
    cereg   = _at("AT+CEREG?")  # EPS 注册状态
    c5greg  = _at("AT+C5GREG?")  # 5G 注册状态
    qnwinfo = _at("AT+QNWINFO")
    qrsrp   = _at("AT+QRSRP")
    qrsrq   = _at("AT+QRSRQ")
    qcainfo = _at("AT+QCAINFO")
    qeng_serv = _at('AT+QENG="servingcell"')
    qsinr   = _at("AT+QSINR")
    qeng    = _at('AT+QENG="servingcell"')
    qtemp   = _at("AT+QTEMP")  # 温度数据
    qnetdev  = _at("AT+QNETDEVSTATUS")  # NetDev 状态
    cgdcont  = _at("AT+CGDCONT?")  # PDP 上下文配置
    cgact    = _at("AT+CGACT?")  # PDP 激活状态
    cgcontrdp = _at("AT+CGCONTRDP?")  # PDP 上下文详情
    qidnscfg = _at("AT+QIDNSCFG?")  # DNS 配置

    qeng_nb  = _at(r'AT+QENG="neighbourcell"')

    # 2. 通用字段
    reg  = _parse_cgreg(cgreg)
    mode, operator = _parse_qnwinfo(qnwinfo)
    signal = LiveSignalModel(
        rsrp=_parse_qrsrp(qrsrp),
        rsrq=_parse_qrsrq(qrsrq),
        rssi=None,
        sinr=_parse_qsinr(qsinr),
        cqi=None,
    )

    # 3. Serving Cell 解析（支持 SA/NSA/LTE 所有模式）
    rat, sa_obj, lte_obj, nsa_lte_obj, nsa_nr_obj, sa_mcc, sa_mnc, sa_duplex = _try_parse_serving_all(qeng)
    
    # 根据解析结果构建 serving 模型
    if rat == "SA" and sa_obj is not None:
        serving = LiveServingModel(rat="SA", sa=sa_obj, lte=None, nsa=None, nsa_nr=None)
        # operator 兜底
        if operator.mcc is None and sa_mcc is not None:
            operator.mcc = sa_mcc
        if operator.mnc is None and sa_mnc is not None:
            operator.mnc = sa_mnc
        if mode.duplex is None and sa_duplex is not None:
            mode.duplex = sa_duplex
        if mode.rat is None:
            mode.rat = "SA"
    elif rat == "NSA" and (nsa_lte_obj is not None or nsa_nr_obj is not None):
        serving = LiveServingModel(rat="NSA", sa=None, lte=None, nsa=nsa_lte_obj, nsa_nr=nsa_nr_obj)
        if mode.rat is None:
            mode.rat = "NSA"
    elif rat == "LTE" and lte_obj is not None:
        serving = LiveServingModel(rat="LTE", sa=None, lte=lte_obj, nsa=None, nsa_nr=None)
        if mode.rat is None:
            mode.rat = "LTE"
    else:
        serving = LiveServingModel(rat=mode.rat, sa=None, lte=None, nsa=None, nsa_nr=None)

    # 4. Neighbors（邻区）解析
    nb_lte_dicts = _parse_qeng_neighbor_lte(qeng_nb)
    nb_nr_dicts = _parse_qeng_neighbor_nr(qeng_nb)
    nb_lte_models = [NbLTE(**d) for d in nb_lte_dicts]
    nb_nr_models = [NbNR(**d) for d in nb_nr_dicts]
    neighbors = LiveNeighborsModel(lte=nb_lte_models, nr=nb_nr_models)

    # 5. CA & 温度占位
    ca_info = LiveCAInfoModel()
    
    # 7. 组装响应
    resp = LiveResponse(
        ok=True,
        ts=ts,
        error=None,
        reg=reg,
        mode=mode,
        operator=operator,
        signal=signal,
        serving=serving,
        neighbors=neighbors,
        ca=ca_info,
        raw=None,
    )

    if verbose:
        resp.raw = {
            "AT+CGREG?": cgreg,
            "AT+CEREG?": cereg,
            "AT+C5GREG?": c5greg,
            "AT+QNWINFO": qnwinfo,
            "AT+QRSRP": qrsrp,
            "AT+QRSRQ": qrsrq,
            "AT+QSINR": qsinr,
            'AT+QENG="servingcell"': qeng,
            'AT+QENG="servingcell"': qeng_serv,
            r'AT+QENG="neighbourcell"': qeng_nb,
            "AT+QCAINFO": qcainfo,
            "AT+QTEMP": qtemp,
            "AT+QNETDEVSTATUS": qnetdev,
            "AT+CGDCONT?": cgdcont,
            "AT+CGACT?": cgact,
            "AT+CGCONTRDP?": cgcontrdp,
            "AT+QIDNSCFG?": qidnscfg,
        }

    raw_data = resp.raw if isinstance(resp.raw, dict) else {}

    # ---- fill temps from AT+QTEMP ----
    temps_payload = {"ambient": None, "mmw": None, "pa": {}, "baseband": {}, "raw": {}}
    try:
        at_qtemp_lines = raw_data.get("AT+QTEMP", []) if raw_data else []
        if not at_qtemp_lines:
            at_qtemp_lines = qtemp
        temps_payload = parse_qtemp_lines(at_qtemp_lines)
    except Exception:
        pass
    resp.temps = temps_payload

    # ---- fill CA from AT+QCAINFO ----
    try:
        at_qcainfo_lines = raw_data.get("AT+QCAINFO", []) if raw_data else []
        if not at_qcainfo_lines:
            at_qcainfo_lines = qcainfo
        pcc_dict, _ = parse_qcainfo(at_qcainfo_lines)
        ca_base = resp.ca or LiveCAInfoModel()
        ca_obj = ca_base.model_dump() if isinstance(ca_base, LiveCAInfoModel) else dict(ca_base)
        pcc_model = None
        if pcc_dict:
            try:
                pcc_model = CA_Pcc(
                    arfcn=pcc_dict.get("earfcn"),
                    dl_bw_mhz=pcc_dict.get("dl_bw_mhz"),
                    band=pcc_dict.get("band"),
                    rat=None,
                    rsrp=None,
                    rsrq=None,
                    sinr=None,
                )
            except Exception:
                pcc_model = None
        ca_obj["pcc"] = pcc_model
        
        # --- CA.SCC fill (safe; never raise) ---
        scc_list = []
        try:
            scc_list = parse_qcainfo_scc(at_qcainfo_lines)
            if not scc_list:
                # fallback from QENG serving if needed
                qeng_serv = raw_data.get('AT+QENG="servingcell"', []) if raw_data else []
                if not qeng_serv:
                    qeng_serv = qeng
                scc_list = parse_qeng_scc_from_serving(qeng_serv)
        except Exception:
            pass
        
        # Convert SCC dicts to CA_Scc models, mapping cc_idx -> idx
        ca_obj["scc"] = []
        for scc_item in scc_list:
            try:
                # Map cc_idx to idx for CA_Scc model
                scc_dict = {
                    "idx": scc_item.get("cc_idx", 0),
                    "band": scc_item.get("band"),
                    "arfcn": scc_item.get("earfcn") or scc_item.get("nrarfcn"),
                    "dl_bw_mhz": scc_item.get("dl_bw_mhz"),
                    "rsrp": scc_item.get("rsrp"),
                    "rsrq": scc_item.get("rsrq"),
                    "sinr": scc_item.get("sinr"),
                    "rat": None,  # Could be inferred from band/earfcn/nrarfcn if needed
                }
                ca_obj["scc"].append(CA_Scc(**scc_dict))
            except Exception:
                continue
        resp.ca = LiveCAInfoModel(**ca_obj)
    except Exception:
        # 任何异常都不要影响主流程
        if resp.ca is None:
            resp.ca = LiveCAInfoModel()
        if not hasattr(resp.ca, "scc") or resp.ca.scc is None:
            resp.ca.scc = []

    # ---- build CA summary ----
    try:
        if getattr(resp, "ca", None) and (getattr(resp.ca, "pcc", None) or getattr(resp.ca, "scc", None)):
            pcc_dict = resp.ca.pcc.model_dump() if hasattr(resp.ca.pcc, "model_dump") else (resp.ca.pcc.dict() if hasattr(resp.ca.pcc, "dict") else dict(resp.ca.pcc) if resp.ca.pcc else None)
            scc_list = []
            if resp.ca.scc:
                for s in resp.ca.scc:
                    scc_list.append(s.model_dump() if hasattr(s, "model_dump") else (s.dict() if hasattr(s, "dict") else dict(s)))
            resp.ca.summary = build_ca_summary(pcc_dict, scc_list)
    except Exception as _:
        # 不阻断主流程
        pass

    # ---- fill neighbours from AT+QENG="neighbourcell" ----
    neigh_list = []
    try:
        at_qeng_nb_lines = raw_data.get(r'AT+QENG="neighbourcell"', []) if raw_data else []
        if not at_qeng_nb_lines:
            at_qeng_nb_lines = qeng_nb
        neigh_list = parse_qeng_neighbour(at_qeng_nb_lines)
    except Exception:
        neigh_list = []
    resp.neighbours = [NeighbourCell(**n) for n in neigh_list] if neigh_list else []

    # --- NetDev: QNETDEVSTATUS -> fallback sysfs, then compute rates ---
    try:
        raw = resp.raw if hasattr(resp, "raw") else None
        lines = None
        if raw and isinstance(raw, dict):
            lines = raw.get("AT+QNETDEVSTATUS")
        nd = None
        if lines:
            nd = parse_qnetdevstatus(lines)
        if not nd:
            nd = probe_sys_netdev()
        if nd:
            nd = with_rates(nd)
            # 将字典映射到模型（若已经有 resp.netdev 则覆写其值）
            if hasattr(resp, "netdev") and resp.netdev is not None:
                for k, v in nd.items():
                    setattr(resp.netdev, k, v)
            else:
                resp.netdev = LiveNetDev(**nd)
    except Exception as _:
        pass

    # --- Session: PDP/APN/DNS via CGCONTRDP/CGACT/CGDCONT/QIDNSCFG ---
    try:
        raw = resp.raw if hasattr(resp, "raw") else None
        cgdc = parse_cgdcont(raw.get("AT+CGDCONT?") if raw and isinstance(raw, dict) else [])
        cgac = parse_cgact(raw.get("AT+CGACT?") if raw and isinstance(raw, dict) else [])
        cgco = parse_cgcontrdp(raw.get("AT+CGCONTRDP?") if raw and isinstance(raw, dict) else [])
        qdns = parse_qidnscfg(raw.get("AT+QIDNSCFG?") if raw and isinstance(raw, dict) else [])
        # 合并到 CID 维度
        cids = set(cgdc.keys()) | set(cgac.keys()) | set(cgco.keys())
        pdp_list = []
        for cid in sorted(cids):
            d = {**cgdc.get(cid, {}), **cgco.get(cid, {})}
            if cid in cgac: d["state"] = cgac[cid]
            # 补 DNS（若 AT+CGCONTRDP 没给出）
            d.setdefault("dns1", qdns.get("dns1"))
            d.setdefault("dns2", qdns.get("dns2"))
            pdp_list.append(PDPContext(
                cid=cid,
                type=d.get("type"),
                apn=d.get("apn"),
                state=d.get("state"),
                ip=d.get("ip"),
                dns1=d.get("dns1"),
                dns2=d.get("dns2"),
            ))
        if pdp_list:
            # default_cid：优先取 state=1 的最小 cid
            default_cid = None
            for p in pdp_list:
                if p.state == 1:
                    default_cid = p.cid
                    break
            resp.session = LiveSessionModel(default_cid=default_cid, pdp=pdp_list)
    except Exception:
        pass

    # --- Registration & Serving Cell Normalization ---
    try:
        raw = resp.raw if hasattr(resp, "raw") else None
        raw_dict = raw if isinstance(raw, dict) else {}
        
        # 解析注册状态
        eps_stat = parse_cereg_stat(raw_dict.get("AT+CEREG?", []))
        nr5g_stat = parse_c5greg_stat(raw_dict.get("AT+C5GREG?", []))
        
        if eps_stat is not None or nr5g_stat is not None:
            resp.reg_detail = RegStatus(
                eps=eps_stat,
                nr5g=nr5g_stat,
                eps_text=reg_text(eps_stat),
                nr5g_text=reg_text(nr5g_stat),
            )
        
        # 解析 serving cell 核心信息
        qeng_serving_lines = raw_dict.get('AT+QENG="servingcell"', [])
        if not qeng_serving_lines:
            # 尝试从其他变量获取
            qeng_serving_lines = qeng if 'qeng' in locals() else []
        
        serving_core = parse_qeng_serving_core(qeng_serving_lines)
        
        if serving_core:
            rat = serving_core.get("rat")
            tac_hex = serving_core.get("tac_hex")
            tac_dec = _try_int_hex(tac_hex) if tac_hex else None
            
            # 构建 CellIdNorm
            cell_id_norm = CellIdNorm(
                tac_hex=tac_hex,
                tac_dec=tac_dec,
                rat=rat,
            )
            
            # 处理 LTE ECI
            if rat == "LTE":
                # 尝试从现有 serving 数据获取 ECI
                eci_hex = None
                eci_dec = None
                if hasattr(resp, "serving") and resp.serving:
                    # 从 serving.lte 或其他字段尝试获取
                    pass  # 暂时留空，后续可从其他解析函数获取
                
                if eci_dec:
                    enb_id, cell_id = _split_lte_eci(eci_dec)
                    cell_id_norm.eci_dec = eci_dec
                    cell_id_norm.eci_hex = eci_hex
                    cell_id_norm.enb_id = enb_id
                    cell_id_norm.cell_id = cell_id
            
            # 处理 NR NCI
            elif rat and ("NR5G" in rat or "NR" in rat):
                # 优先从 serving_core 获取 nci_hex（Task B）
                nci_hex = serving_core.get("nci_hex")
                nci_dec = None
                
                if nci_hex:
                    nci_dec = _try_int_hex(nci_hex)
                elif hasattr(resp, "serving") and resp.serving and resp.serving.sa:
                    # 从 serving.sa.cellid 获取（兜底）
                    if resp.serving.sa.cellid:
                        nci_dec = resp.serving.sa.cellid
                        nci_hex = hex(nci_dec)[2:].upper() if nci_dec else None
                
                if nci_dec:
                    gnb_id, nci_cell_id = _split_nr_nci(nci_dec)
                    cell_id_norm.nci_dec = nci_dec
                    cell_id_norm.nci_hex = nci_hex
                    cell_id_norm.gnb_id = gnb_id
                    cell_id_norm.nci_cell_id = nci_cell_id
            
            # 获取 band 和 arfcn（从现有 serving 或 ca 数据）
            band = None
            arfcn = None
            pci = serving_core.get("pci")
            
            # 尝试从现有 serving 数据获取
            if hasattr(resp, "serving") and resp.serving:
                if resp.serving.sa:
                    band = resp.serving.sa.band
                    arfcn = str(resp.serving.sa.nrarfcn) if resp.serving.sa.nrarfcn else None
                    if not pci and resp.serving.sa.pcid:
                        pci = str(resp.serving.sa.pcid)
                elif resp.serving.lte:
                    # LTE serving 数据
                    pass
            
            # 如果还没有，从 serving_core 获取
            if not arfcn:
                arfcn = serving_core.get("arfcn")
            
            # Task A: 统一 band 命名
            band = pretty_band(rat, band)
            
            # 组装 serving_norm
            resp.serving_norm = LiveServingModel(
                rat=rat,
                band=band,
                arfcn=arfcn,
                pci=pci,
                id=cell_id_norm,
            )
    except Exception as e:
        # 调试用：打印异常信息
        import traceback
        print(f"[live] Registration & Serving normalization error: {e}")
        traceback.print_exc()
        pass

    # --- Step-9: Separate LTE & NR Signal Blocks ---
    try:
        # 从 serving 数据提取信号
        lte_rssi = None
        lte_rsrp = None
        lte_rsrq = None
        lte_sinr = None
        
        nr_rssi = None
        nr_rsrp = None
        nr_rsrq = None
        nr_sinr = None
        
        # 从现有 serving 数据获取
        if hasattr(resp, "serving") and resp.serving:
            # NR 信号（从 serving.sa 或 serving.nsa_nr）
            if resp.serving.sa:
                if resp.serving.sa.rsrp is not None:
                    nr_rsrp = str(resp.serving.sa.rsrp)
                if resp.serving.sa.rsrq is not None:
                    nr_rsrq = str(resp.serving.sa.rsrq)
                if resp.serving.sa.sinr is not None:
                    nr_sinr = str(resp.serving.sa.sinr)
            elif resp.serving.nsa_nr:
                # NSA 的 NR 部分
                pass
            elif resp.serving.lte:
                # LTE serving 数据
                pass
            elif resp.serving.nsa:
                # NSA 的 LTE 部分
                pass
        
        # 从 signal 数据获取（兜底）
        if hasattr(resp, "signal") and resp.signal:
            # 根据当前 RAT 判断是 LTE 还是 NR
            current_rat = None
            if hasattr(resp, "mode") and resp.mode and resp.mode.rat:
                current_rat = resp.mode.rat
            elif hasattr(resp, "serving") and resp.serving:
                current_rat = resp.serving.rat
            
            # 如果 serving 没有数据，从全局 signal 获取
            if not lte_rsrp and not nr_rsrp and resp.signal.rsrp is not None:
                if current_rat and ("LTE" in current_rat):
                    lte_rsrp = str(resp.signal.rsrp)
                elif current_rat and ("NR" in current_rat or "SA" in current_rat):
                    nr_rsrp = str(resp.signal.rsrp)
                else:
                    # 默认根据 serving 判断
                    if hasattr(resp, "serving") and resp.serving and resp.serving.sa:
                        nr_rsrp = str(resp.signal.rsrp)
                    else:
                        lte_rsrp = str(resp.signal.rsrp)
            
            if not lte_rsrq and not nr_rsrq and resp.signal.rsrq is not None:
                if current_rat and ("LTE" in current_rat):
                    lte_rsrq = str(resp.signal.rsrq)
                elif current_rat and ("NR" in current_rat or "SA" in current_rat):
                    nr_rsrq = str(resp.signal.rsrq)
                else:
                    if hasattr(resp, "serving") and resp.serving and resp.serving.sa:
                        nr_rsrq = str(resp.signal.rsrq)
                    else:
                        lte_rsrq = str(resp.signal.rsrq)
            
            if not lte_sinr and not nr_sinr and resp.signal.sinr is not None:
                if current_rat and ("LTE" in current_rat):
                    lte_sinr = str(resp.signal.sinr)
                elif current_rat and ("NR" in current_rat or "SA" in current_rat):
                    nr_sinr = str(resp.signal.sinr)
                else:
                    if hasattr(resp, "serving") and resp.serving and resp.serving.sa:
                        nr_sinr = str(resp.signal.sinr)
                    else:
                        lte_sinr = str(resp.signal.sinr)
            
            if not lte_rssi and resp.signal.rssi is not None:
                lte_rssi = str(resp.signal.rssi)
        
        # 计算质量等级
        lte_q, lte_note = rate_quality_lte(lte_rsrp, lte_sinr)
        nr_q, nr_note = rate_quality_nr(nr_rsrp, nr_sinr)
        
        # 组装 SignalBlock
        if lte_rsrp is not None or lte_rsrq is not None or lte_sinr is not None or lte_rssi is not None:
            resp.signal_lte = SignalBlock(
                rssi=lte_rssi,
                rsrp=lte_rsrp,
                rsrq=lte_rsrq,
                sinr=lte_sinr,
                quality=lte_q,
                note=lte_note,
            )
        
        if nr_rsrp is not None or nr_rsrq is not None or nr_sinr is not None or nr_rssi is not None:
            resp.signal_nr = SignalBlock(
                rssi=nr_rssi,
                rsrp=nr_rsrp,
                rsrq=nr_rsrq,
                sinr=nr_sinr,
                quality=nr_q,
                note=nr_note,
            )
    except Exception as e:
        import traceback
        print(f"[live] Signal separation error: {e}")
        traceback.print_exc()
        pass

    print(f"[live] neighbors lte={len(nb_lte_dicts)}, nr={len(nb_nr_dicts)}")
    print(f"[live] neighbours count={len(neigh_list)}")
    ca_scc_len = len(getattr(resp.ca, "scc", []) or [])
    print(f"[live] ca scc={ca_scc_len}")
    return resp


# ======== STEP3: NSA/LTE servingcell 解析(自动追加) ========

def _nz(v: Optional[int]) -> Optional[int]:
    # -32768/None 统一视为无效
    if v is None:
        return None
    try:
        return None if int(v) == -32768 else int(v)
    except Exception:
        return None

def _payload_after_first_quoted_tag(line: str) -> str:
    # 取第一对引号后的逗号开始的 payload，例如:
    # +QENG: "servingcell","NOCONN","NR5G-SA",... -> 取到 "NOCONN","NR5G-SA",...
    try:
        i = line.index('",')
        return line[i+2:].strip()
    except ValueError:
        # 兜底：去掉到第一个冒号
        return line.split(":",1)[-1].strip()

def _parse_qeng_serving_lte(lines: List[str]) -> Tuple[str, Optional[ServingLTE]]:
    """解析 LTE 模式的 +QENG: "servingcell","LTE"... 行"""
    ln = None
    for s in lines:
        if s.strip().startswith('+QENG: "servingcell"') and '"LTE"' in s:
            ln = s
            break
    if not ln:
        return "UNKNOWN", None

    payload = _payload_after_first_quoted_tag(ln)
    toks = _split_csv_tokens(payload)

    # 预期: state, "LTE", is_tdd, mcc, mnc, cellid, pcid, earfcn, freq_band_ind, ul_bw, dl_bw, tac, rsrp, rsrq, rssi, sinr, cqi, tx_power, srxlev
    if len(toks) < 19:
        return "UNKNOWN", None

    state   = toks[0]
    is_tdd  = toks[2] if toks[2] in ("TDD","FDD") else None
    lte = ServingLTE(
        state=state,
        is_tdd=is_tdd,
        mcc=_to_int(toks[3]),
        mnc=_to_int(toks[4]),
        cellid=_to_int(toks[5]),
        pcid=_to_int(toks[6]),
        earfcn=_to_int(toks[7]),
        band=_to_int(toks[8]),
        ul_bw_mhz=_to_int(toks[9]),
        dl_bw_mhz=_to_int(toks[10]),
        tac=_to_int(toks[11]),
        rsrp=_nz(_to_int(toks[12])),
        rsrq=_nz(_to_int(toks[13])),
        rssi=_to_int(toks[14]),
        sinr=_nz(_to_int(toks[15])),
        cqi=_to_int(toks[16]),
        tx_power=_to_int(toks[17]),
        srxlev=_to_int(toks[18]),
    )
    return "LTE", lte

def _parse_qeng_serving_nsa(lines: List[str]) -> Tuple[str, Optional[ServingNSA], Optional[ServingNSA_NRPart]]:
    """解析 EN-DC(NR5G-NSA)两行：+QENG: "LTE"... 与 +QENG: "NR5G-NSA"..."""
    lte_line = None
    nr_line  = None
    for s in lines:
        st = s.strip()
        if st.startswith('+QENG: "LTE"'):
            lte_line = s
        elif st.startswith('+QENG: "NR5G-NSA"'):
            nr_line = s
    if not lte_line or not nr_line:
        return "UNKNOWN", None, None

    # LTE 锚点
    toks_lte = _split_csv_tokens(_payload_after_first_quoted_tag(lte_line))
    # 预期: "LTE", is_tdd, mcc, mnc, cellid, pcid, earfcn, freq_band_ind, ul_bw, dl_bw, tac, rsrp, rsrq, rssi, sinr, cqi, tx_power, srxlev
    if len(toks_lte) < 18:
        return "UNKNOWN", None, None

    lte = ServingNSA(
        is_tdd=toks_lte[1] if toks_lte[1] in ("TDD","FDD") else None,
        mcc=_to_int(toks_lte[2]),
        mnc=_to_int(toks_lte[3]),
        cellid=_to_int(toks_lte[4]),
        pcid=_to_int(toks_lte[5]),
        earfcn=_to_int(toks_lte[6]),
        band=_to_int(toks_lte[7]),
        ul_bw_mhz=_to_int(toks_lte[8]),
        dl_bw_mhz=_to_int(toks_lte[9]),
        tac=_to_int(toks_lte[10]),
        rsrp=_nz(_to_int(toks_lte[11])),
        rsrq=_nz(_to_int(toks_lte[12])),
        rssi=_to_int(toks_lte[13]),
        sinr=_nz(_to_int(toks_lte[14])),
        cqi=_to_int(toks_lte[15]),
        tx_power=_to_int(toks_lte[16]),
        srxlev=_to_int(toks_lte[17]),
    )

    # NR 部分
    toks_nr = _split_csv_tokens(_payload_after_first_quoted_tag(nr_line))
    # 预期: "NR5G-NSA", mcc, mnc, pcid, rsrp, sinr, rsrq, arfcn, band, nr_dl_bw, scs
    if len(toks_nr) < 11:
        return "UNKNOWN", lte, None

    nr = ServingNSA_NRPart(
        mcc=_to_int(toks_nr[1]),
        mnc=_to_int(toks_nr[2]),
        pcid=_to_int(toks_nr[3]),
        rsrp=_nz(_to_int(toks_nr[4])),
        sinr=_nz(_to_int(toks_nr[5])),
        rsrq=_nz(_to_int(toks_nr[6])),
        nrarfcn=_to_int(toks_nr[7]),
        band=_to_int(toks_nr[8]),
        dl_bw_mhz=_to_int(toks_nr[9]),
        scs_khz=_to_int(toks_nr[10]),
    )
    return "NSA", lte, nr

def _try_parse_serving_all(lines: List[str]) -> Tuple[str, Optional[ServingSA], Optional[ServingLTE], Optional[ServingNSA], Optional[ServingNSA_NRPart], Optional[int], Optional[int], Optional[str]]:
    """依次尝试 SA → NSA → LTE；统一返回"""
    # 先走已有的 SA 解析(保持向后兼容)
    rat_sa, sa_obj, sa_mcc, sa_mnc, sa_duplex = _parse_qeng_serving_sa(lines)
    if rat_sa == "SA" and sa_obj:
        return "SA", sa_obj, None, None, None, sa_mcc, sa_mnc, sa_duplex

    # 再试 NSA
    rat_nsa, nsa_lte_obj, nsa_nr_obj = _parse_qeng_serving_nsa(lines)
    if rat_nsa == "NSA" and (nsa_lte_obj or nsa_nr_obj):
        return "NSA", None, None, nsa_lte_obj, nsa_nr_obj, None, None, None

    # 最后试 LTE
    rat_lte, lte_obj = _parse_qeng_serving_lte(lines)
    if rat_lte == "LTE" and lte_obj:
        return "LTE", None, lte_obj, None, None, None, None, None

    return "UNKNOWN", None, None, None, None, None, None, None
# ======== /STEP3 ========


# ===== Step5 helpers (isolated) =====
def s5__to_int(v):
    try:
        if v is None: return None
        v = v.strip().strip('"').strip("'")
        base = 16 if v.startswith(("0x","0X")) else 10
        return int(v, base)
    except Exception:
        return None

def s5__nz(v):
    # -32768 或空串 统一为 None
    try:
        if v is None: return None
        vv = str(v).strip()
        if vv == "" or vv == "-32768":
            return None
        return v if isinstance(v, (int,float)) else int(v)
    except Exception:
        return None

def s5__mhz(v):
    try:
        if v is None: return None
        return int(v)
    except Exception:
        return None


# ===== Step5: +QCAINFO 解析为 {pcc:{...}, scc:[...]} =====
def _parse_qcainfo(lines):
    # 兼容多行：每行可能是 PCC 或 SCC
    pcc = None
    scc = []
    for ln in lines:
        s = ln.strip()
        if not s.startswith("+QCAINFO:"):
            continue
        # 去掉前缀
        payload = s.split(":",1)[1].strip()
        # 简单 CSV 切分(逗号分隔，保留引号值)
        toks = [t.strip().strip('"') for t in payload.split(",")]
        if not toks:
            continue
        kind = toks[0].upper() if toks else ""
        # 常见字段最小子集：freq(earfcn), bandwidth(MHz), band, pcid/rsrp/rsrq 可选
        try:
            if kind == "PCC":
                obj = {
                    "freq": s5__to_int(toks[1]) if len(toks)>1 else None,
                    "bandwidth": s5__mhz(toks[2]) if len(toks)>2 else None,
                    "band": toks[3] if len(toks)>3 else None,
                }
                pcc = obj
            elif kind == "SCC":
                obj = {
                    "freq": s5__to_int(toks[1]) if len(toks)>1 else None,
                    "bandwidth": s5__mhz(toks[2]) if len(toks)>2 else None,
                    "band": toks[3] if len(toks)>3 else None,
                }
                scc.append(obj)
        except Exception:
            continue
    if pcc is None and not scc:
        return None
    return {"pcc": pcc, "scc": scc}


# ===== Step5: +QENG="neighbourcell" 解析 =====
def _parse_qeng_neighbors(lines):
    # 仅提取 LTE 邻区(intra/inter)，最小子集：rat, earfcn, pcid, rsrp, rsrq
    items = []
    for ln in lines:
        s = ln.strip()
        if not s.startswith("+QENG:"):
            continue
        # 形如：+QENG: "neighbourcell intra","LTE",<earfcn>,<PCID>,<RSRQ>,<RSRP>,...
        try:
            # 拆出所有以逗号分隔的段，同时保留前两个字符串字段
            # 简易做法：先去掉 +QENG: 和引号中的逗号干扰不处理，抓关键位
            parts = [x.strip() for x in s.split(",")]
            if len(parts) < 6:
                continue
            head = parts[0]  # +QENG: "neighbourcell intra"
            if '"neighbourcell' not in head:
                continue
            rat = parts[1].strip().strip('"').upper()
            if rat != "LTE":
                # 先做 LTE，NR 如需后续扩展
                continue
            earfcn = s5__to_int(parts[2])
            pcid = s5__to_int(parts[3])
            rsrq = s5__nz(parts[4])
            rsrp = s5__nz(parts[5])
            item = {
                "rat": rat,
                "earfcn": earfcn,
                "pcid": pcid,
                "rsrq": rsrq,
                "rsrp": rsrp,
            }
            items.append(item)
        except Exception:
            continue
    # 裁前 5 个，避免冗长
    if not items:
        return None
    return {"lte": items[:5], "nr": []}


# ===== Step6 parsers (auto-added) =====
def _parse_qcainfo(lines: List[str]) -> Tuple[Dict, List[Dict]]:
    pcc = None
    scc: List[Dict] = []
    if not lines:
        return pcc, scc

    for ln in lines:
        s = ln.strip()
        if not s.startswith("+QCAINFO"):
            continue
        payload = _payload_after_first_quoted_tag(s)
        toks = _split_csv_tokens(payload)
        if not toks:
            continue

        tag = str(toks[0]).strip().upper()
        band = toks[1] if len(toks) > 1 and isinstance(toks[1], str) else None

        ints: List[int] = []
        for x in toks[2:]:
            val = _to_int_or_none(x)
            if val is not None:
                ints.append(val)

        arfcn = ints[0] if len(ints) >= 1 else None
        dl_bw_mhz = ints[1] if len(ints) >= 2 else None

        if tag == "PCC":
            pcc = {"band": band, "arfcn": arfcn, "dl_bw_mhz": dl_bw_mhz}
        elif tag == "SCC":
            scc.append(
                {
                    "idx": len(scc) + 1,
                    "band": band,
                    "arfcn": arfcn,
                    "dl_bw_mhz": dl_bw_mhz,
                    "pci": None,
                    "rsrp": None,
                    "rsrq": None,
                    "sinr": None,
                }
            )

    return pcc, scc

def _parse_qeng_neighbor_lte(lines: List[str]) -> List[Dict]:
    out: List[Dict] = []
    if not lines:
        return out
    for ln in lines:
        s = ln.strip()
        if not s.startswith("+QENG:"):
            continue
        if "neighbourcell" not in s and "neighbour" not in s:
            continue
        payload = _payload_after_first_quoted_tag(s)
        toks = _split_csv_tokens(payload)
        if not toks:
            continue
        i = _find_token_index(toks, "LTE")
        if i is None:
            continue

        def g(offset):
            idx = i + offset
            return _to_int_or_none(toks[idx]) if 0 <= idx < len(toks) else None

        earfcn = g(1)
        pci = g(2)
        rsrq = g(3)
        rsrp = g(4)

        if rsrp is not None and rsrq is not None and abs(rsrp) < 10 and abs(rsrq) > 10:
            rsrp, rsrq = rsrq, rsrp

        if earfcn is None or pci is None:
            continue

        out.append(
            {
                "earfcn": earfcn,
                "pci": pci,
                "rsrp": rsrp,
                "rsrq": rsrq,
                "sinr": None,
                "srxlev": None,
            }
        )
    return out

def _parse_qeng_neighbor_nr(lines: List[str]) -> List[Dict]:
    out: List[Dict] = []
    if not lines:
        return out
    for ln in lines:
        s = ln.strip()
        if not s.startswith("+QENG:"):
            continue
        if "neighbourcell" not in s and "neighbour" not in s:
            continue
        payload = _payload_after_first_quoted_tag(s)
        toks = _split_csv_tokens(payload)
        if not toks:
            continue

        i = _find_token_index(toks, "NR5G", "NR", "NR5G-SA", "NR5G-NSA")
        if i is None:
            continue

        scs_khz = None
        next_idx = i + 1
        if next_idx < len(toks):
            maybe_scs = _to_int_or_none(toks[next_idx])
            if maybe_scs in (15, 30, 60, 120):
                scs_khz = maybe_scs
                i = next_idx

        def g(offset):
            idx = i + 1 + offset
            return _to_int_or_none(toks[idx]) if 0 <= idx < len(toks) else None

        nrarfcn = g(0)
        pci = g(1)
        rsrp = g(2)
        rsrq = g(3)

        if nrarfcn is None or pci is None:
            continue

        out.append(
            {
                "nrarfcn": nrarfcn,
                "pci": pci,
                "rsrp": rsrp,
                "rsrq": rsrq,
                "sinr": None,
                "srxlev": None,
                "scs_khz": scs_khz,
            }
        )
    return out

# ===== /Step6 parsers =====
