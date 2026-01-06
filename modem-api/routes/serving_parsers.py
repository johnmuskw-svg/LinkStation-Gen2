# coding: utf-8
from typing import List, Optional, Any, Dict
import re

def _first_qeng_line(lines: List[str], tag: str) -> Optional[str]:
    for s in lines:
        t = s.strip()
        if t.startswith("+QENG:") and f'"{tag}"' in t:
            return t
    return None

def _payload_after_first_quoted_tag(line: str) -> str:
    try:
        i0 = line.index('"')
        i1 = line.index('"', i0 + 1)
        j  = line.find(",", i1 + 1)
        return line[j + 1 :].strip() if j != -1 else ""
    except ValueError:
        return ""

def _split_csv_tokens(payload: str) -> List[str]:
    res, cur, q = [], "", False
    for ch in payload:
        if ch == '"':
            q = not q
            cur += ch
        elif ch == ',' and not q:
            res.append(cur.strip()); cur = ""
        else:
            cur += ch
    if cur: res.append(cur.strip())
    return res

def _to_int(x: Any) -> Optional[int]:
    try:
        v = int(str(x).strip(), 10)
        return None if v == -32768 else v
    except Exception:
        return None

def parse_qeng_serving_lte(lines: List[str]) -> Optional[Dict[str, Any]]:
    """防御式 LTE 解析：能解析就返回少量字段；不行就 None。绝不抛错。"""
    s = _first_qeng_line(lines, "servingcell")
    if not s or "LTE" not in s.upper():
        return None
    payload = _payload_after_first_quoted_tag(s)
    toks = _split_csv_tokens(payload)
    # 找到 "LTE" 的位置（不同固件可能有引号/无引号/大小写）
    ix = -1
    for k, v in enumerate(toks):
        if "LTE" in v.upper():
            ix = k; break
    if ix < 0: 
        return None

    def gi(k: int):
        j = ix + k
        return toks[j] if 0 <= j < len(toks) else None

    return {
        "state": gi(-1),                # 往前一位常见为 "NOCONN"/"CONNECTED"
        "mcc":   _to_int(gi(1)),
        "mnc":   _to_int(gi(2)),
        "pcid":  _to_int(gi(3)),
        "earfcn":_to_int(gi(4)),
        # RSRP/RSRQ 的索引在不同固件可能位移，这里做容错兜底
        "rsrp":  _to_int(gi(6) if gi(6) is not None else gi(5)),
        "rsrq":  _to_int(gi(7) if gi(7) is not None else gi(6)),
    }

def parse_qeng_serving_nsa(lines: List[str]) -> Optional[Dict[str, Any]]:
    """防御式 NSA 解析：只返回原始切片预览，后续拿到样例再精细化。"""
    s = _first_qeng_line(lines, "servingcell")
    if not s: 
        return None
    up = s.upper()
    if "NSA" not in up and "NR5G-NSA" not in up:
        return None
    payload = _payload_after_first_quoted_tag(s)
    toks = _split_csv_tokens(payload)
    return {"preview": toks[:24]}

# ---------- temps & CA parsers (append at end of file) ----------

import re

from typing import Dict, List, Optional, Tuple


QTEMP_ALIAS = {
    # 功放/PA
    "modem-lte-sub6-pa1": ("pa", "lte_pa1"),
    "modem-lte-sub6-pa2": ("pa", "lte_pa2"),
    "modem-sdr0-pa0": ("pa", "sdr0_pa0"),
    "modem-sdr0-pa1": ("pa", "sdr0_pa1"),
    "modem-sdr0-pa2": ("pa", "sdr0_pa2"),
    "modem-sdr1-pa0": ("pa", "sdr1_pa0"),
    "modem-sdr1-pa1": ("pa", "sdr1_pa1"),
    "modem-sdr1-pa2": ("pa", "sdr1_pa2"),
    # 毫米波与环境
    "modem-mmw0": ("mmw", None),
    "modem-ambient-usr": ("ambient", None),
    # 基带&子系统
    "aoss-0-usr": ("baseband", "aoss_0_usr"),
    "cpuss-0-usr": ("baseband", "cpuss_0_usr"),
    "mdmq6-0-usr": ("baseband", "mdmq6_0_usr"),
    "mdmss-0-usr": ("baseband", "mdmss_0_usr"),
    "mdmss-1-usr": ("baseband", "mdmss_1_usr"),
    "mdmss-2-usr": ("baseband", "mdmss_2_usr"),
    "mdmss-3-usr": ("baseband", "mdmss_3_usr"),
}

_qtemp_pat = re.compile(r'\+QTEMP:"([^"]+)"\s*,\s*"(-?\d+)"')


def parse_qtemp_lines(at_qtemp_lines: List[str]) -> Dict:
    """
    将 AT+QTEMP 的原始行解析为 temps 结构：
    temps = {
        "ambient": Optional[int],
        "mmw": Optional[int],
        "pa": Dict[str,int],
        "baseband": Dict[str,int],
        "raw": Dict[str, Optional[int]],
    }
    说明：返回 -273 视为 None（无读数）
    """
    ambient: Optional[int] = None
    mmw: Optional[int] = None
    pa: Dict[str, int] = {}
    base: Dict[str, int] = {}
    raw: Dict[str, Optional[int]] = {}
    for ln in at_qtemp_lines or []:
        m = _qtemp_pat.search(ln)
        if not m:
            continue
        key, sval = m.group(1), m.group(2)
        try:
            v = int(sval)
        except Exception:
            v = None
        v_std: Optional[int]
        if v == -273:
            v_std = None
        else:
            v_std = v
        raw[key] = v_std
        grp = QTEMP_ALIAS.get(key)
        if not grp:
            if v_std is not None:
                base[key.replace("-", "_")] = v_std
            continue
        cat, sub = grp
        if cat == "ambient":
            ambient = v_std
        elif cat == "mmw":
            mmw = v_std
        elif cat == "pa" and sub and v_std is not None:
            pa[sub] = v_std
        elif cat == "baseband" and sub and v_std is not None:
            base[sub] = v_std
    return {
        "ambient": ambient,
        "mmw": mmw,
        "pa": pa,
        "baseband": base,
        "raw": raw,
    }


_qcainfo_pcc_pat = re.compile(
    r'\+QCAINFO:\s*"PCC"\s*,\s*([^,]+)\s*,\s*([^,]+)\s*,\s*"([^"]+)"\s*,\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^,\r\n]+)'
)


def _parse_bandwidth_to_mhz(bw_val: str) -> Optional[int]:
    """将带宽值转换为MHz。根据官方文档，bandwidth值对应：6=1.4MHz, 15=3MHz, 25=5MHz, 50=10MHz, 75=15MHz, 100=20MHz"""
    try:
        bw_int = int(bw_val)
        # 映射表：bandwidth值 -> MHz
        bw_map = {6: 1, 15: 3, 25: 5, 50: 10, 75: 15, 100: 20}
        return bw_map.get(bw_int, bw_int if bw_int < 100 else None)
    except Exception:
        return None


def parse_qcainfo(at_qcainfo_lines: List[str]) -> Tuple[Optional[dict], List[dict]]:
    """
    解析 AT+QCAINFO。
    返回 (pcc_obj, scc_list)
    
    根据官方文档，LTE模式的PCC响应格式：
    "PCC",<freq>,<bandwidth>,<band>,<pcell_state>,<PCID>,<RSRP>,<RSRQ>,<RSSI>,<RSSNR>
    
    EN-DC和SA模式的PCC响应格式可能不同，包含NR相关参数。
    """
    pcc: Optional[dict] = None
    scc: List[dict] = []
    for ln in at_qcainfo_lines or []:
        if not ln.strip().startswith("+QCAINFO:"):
            continue
        
        # 尝试匹配标准LTE格式的PCC
        m = _qcainfo_pcc_pat.search(ln)
        if m:
            try:
                freq = _as_int(m.group(1))
                bandwidth_code = _as_int(m.group(2))
                band = m.group(3).strip()
                pcell_state = _as_int(m.group(4))
                pcid = _as_int(m.group(5))
                rsrp = _as_int(m.group(6))
                rsrq = _as_int(m.group(7))
                rssi = _as_int(m.group(8))
                rssnr = _as_int(m.group(9))
                
                # 转换bandwidth代码为MHz
                dl_bw_mhz = _parse_bandwidth_to_mhz(str(bandwidth_code)) if bandwidth_code else None
                
                pcc = {
                    "earfcn": freq,
                    "dl_bw_mhz": dl_bw_mhz,
                    "band": band,
                    "pcell_state": pcell_state,
                    "pci": pcid,
                    "rsrp": rsrp,
                    "rsrq": rsrq,
                    "rssi": rssi,
                    "rssnr": rssnr,
                }
                continue
            except Exception:
                pass
        
        # 如果标准格式匹配失败，尝试更宽松的解析（兼容不同格式）
        # 例如EN-DC或SA模式的PCC格式可能不同
        if '"PCC"' in ln.upper():
            parts = [_clean_token(p) for p in ln.split(":", 1)[-1].split(",")]
            if len(parts) >= 4:
                try:
                    freq = _as_int(parts[1])
                    bandwidth_code = _as_int(parts[2])
                    band = parts[3] if len(parts) > 3 else None
                    pcc = {
                        "earfcn": freq,
                        "dl_bw_mhz": _parse_bandwidth_to_mhz(str(bandwidth_code)) if bandwidth_code else None,
                        "band": band,
                        "pci": _as_int(parts[5]) if len(parts) > 5 else None,
                        "rsrp": _as_int(parts[6]) if len(parts) > 6 else None,
                        "rsrq": _as_int(parts[7]) if len(parts) > 7 else None,
                        "rssi": _as_int(parts[8]) if len(parts) > 8 else None,
                        "rssnr": _as_int(parts[9]) if len(parts) > 9 else None,
                    }
                except Exception:
                    pass
    
    return pcc, scc


# --- CA (SCC) Parsers: QCAINFO / QENG fallback ---------------------------------

def _clean_token(tok: str) -> str:
    return tok.strip().strip('"').strip()


def _as_int(x: Optional[str]) -> Optional[int]:
    if x is None: return None
    s = str(x).strip()
    if s in ("", "-", "null", "None"): return None
    try:
        v = int(float(s))
        if v == -32768:
            return None
        return v
    except Exception:
        return None


def _as_mhz(x: Optional[str]) -> Optional[int]:
    """Try parse bandwidth like '20', '20MHz', '100' (kHz not expected here)."""
    if x is None: return None
    s = str(x).lower().replace("mhz", "").strip()
    return _as_int(s)


def parse_qcainfo_scc(lines: List[str]) -> List[Dict]:
    """
    Parse SCC rows from AT+QCAINFO.
    We accept very liberal formats, e.g.:
      +QCAINFO: "SCC1","NR5G","n41",...,  499680, 100, ..., PCI, RSRP, RSRQ, SINR
      +QCAINFO: "SCC2","LTE","B3",  EARFCN=..., DL_BW=20,...
    Only fill what we can find, keep the rest None.
    """
    scc_list: List[Dict] = []
    for ln in lines or []:
        if "+QCAINFO" not in ln:
            continue
        raw = ln.split(":", 1)[-1]
        parts = [_clean_token(p) for p in raw.split(",")]

        # Identify SCC row
        head = parts[0] if parts else ""
        if not head.upper().startswith("SCC"):
            continue

        # Extract cc_idx
        idx_str = ''.join(ch for ch in head if ch.isdigit())
        cc_idx = _as_int(idx_str) or 0

        # Try to read RAT and BAND tokens among the first few fields
        # We tolerate both LTE and NR naming.
        rat = None
        band = None
        # Commonly: ["SCC1","NR5G","n41", ...] or ["SCC1","LTE","B3", ...]
        if len(parts) >= 3:
            rat = parts[1] or None
            band = parts[2] or None

        # Heuristics for freq & BW & PCI/RSRP/RSRQ/SINR (positions vary by FW)
        earfcn = None
        nrarfcn = None
        pci = None
        rsrp = None
        rsrq = None
        sinr = None
        dl_bw_mhz = None
        ul_bw_mhz = None
        scs_khz = None

        # Try to scan numbers in the rest tokens conservatively
        # We'll simply look for typical keywords when present, or fallback by position.
        for i, t in enumerate(parts[3:], start=3):
            tl = t.lower()
            # bandwidth
            if "bw" in tl and ("dl" in tl or "ul" in tl):
                # e.g. DL_BW=20
                kv = tl.replace("=", ":").split(":")
                if len(kv) == 2:
                    val = _as_mhz(kv[1])
                    if "dl" in tl and dl_bw_mhz is None:
                        dl_bw_mhz = val
                    elif "ul" in tl and ul_bw_mhz is None:
                        ul_bw_mhz = val
                continue
            # scs
            if "scs" in tl:
                kv = tl.replace("=", ":").split(":")
                if len(kv) == 2:
                    scs_khz = _as_int(kv[1])
                continue
            # pci
            if tl.startswith("pci=") or tl == "pci":
                if "=" in t:
                    pci = _as_int(t.split("=",1)[-1])
                else:
                    # next token might be value
                    if i+1 < len(parts): pci = _as_int(parts[i+1])
                continue
            # earfcn / nrarfcn
            if "earfcn" in tl:
                val = t.split("=",1)[-1] if "=" in t else None
                earfcn = _as_int(val or t)
                continue
            if "nrarfcn" in tl or "arfcn" in tl:
                val = t.split("=",1)[-1] if "=" in t else None
                nrarfcn = _as_int(val or t)
                continue
            # simple positional best-effort for RSRP/RSRQ/SINR if tokens look numeric
            if rsrp is None and t.replace("-", "").isdigit():
                # try assign in order RSRP->RSRQ->SINR
                val = _as_int(t)
                if val is not None:
                    if rsrp is None: rsrp = val; continue
            elif rsrq is None and t.replace("-", "").isdigit():
                val = _as_int(t)
                if val is not None:
                    if rsrq is None: rsrq = val; continue
            elif sinr is None and t.replace("-", "").isdigit():
                val = _as_int(t)
                if val is not None:
                    if sinr is None: sinr = val; continue

        # normalize by RAT
        if rat and rat.upper().startswith("NR"):
            earfcn = None
        else:
            nrarfcn = None

        scc_list.append({
            "cc_idx": cc_idx,
            "band": band or None,
            "band_ind": None,
            "earfcn": earfcn,
            "nrarfcn": nrarfcn,
            "pci": pci,
            "rsrp": rsrp, "rsrq": rsrq, "sinr": sinr,
            "dl_bw_mhz": dl_bw_mhz, "ul_bw_mhz": ul_bw_mhz,
            "scs_khz": scs_khz,
        })

    # Sort by cc_idx ascending
    scc_list.sort(key=lambda x: x.get("cc_idx") or 0)
    return scc_list


def parse_qeng_scc_from_serving(lines: List[str]) -> List[Dict]:
    """
    Optional fallback: try to infer SCCs from +QENG="servingcell".
    RM520N 的 QENG 未必给足 SCC 明细；先返回空数组，保留函数骨架以便后续扩展。
    """
    return []


# --- Neighbour Cells Parser: QENG="neighbourcell" ------------------------------

def _tok(s: Optional[str]) -> Optional[str]:
    if s is None: return None
    ss = s.strip().strip('"').strip()
    return ss or None


def _to_int_or_none(s: Optional[str]) -> Optional[int]:
    if s is None: return None
    v = s.strip().lower().replace("mhz", "")
    if v in ("", "-", "null", "none"): return None
    try:
        iv = int(float(v))
        if iv == -32768:
            return None
        return iv
    except Exception:
        return None


def _guess_lte_band_from_earfcn(earfcn: Optional[int]) -> Optional[str]:
    if earfcn is None: return None
    n = earfcn
    # 粗略映射，尽量保守；命中常见频段即可
    if 0 <= n <= 599: return "B1"
    if 1200 <= n <= 1949: return "B3"
    if 37750 <= n <= 38249: return "B34"
    if 38250 <= n <= 38649: return "B38"
    if 38650 <= n <= 39649: return "B39"
    if 39650 <= n <= 41589: return "B40"
    if 41590 <= n <= 43589: return "B41"
    return None


def _guess_nr_band_from_nrarfcn(nrarfcn: Optional[int]) -> Optional[str]:
    if nrarfcn is None: return None
    n = nrarfcn
    if 499200 <= n <= 537999: return "n41"
    if 620000 <= n <= 680000: return "n78"
    if 151600 <= n <= 160600: return "n28"
    if 422000 <= n <= 434000: return "n1"
    return None


def parse_qeng_neighbour(lines: List[str]) -> List[Dict]:
    """
    兼容多种 QENG 邻区行：
      +QENG: "neighbourcell intra","LTE","FDD",MCC,MNC,TAC,CI,EARFCN,PCI,RSRQ,RSRP,RSSI,...(可变)
      +QENG: "neighbourcell","NR5G",MCC,MNC,PCI,SS-RSRP,SS-RSRQ,SS-SINR,NRARFCN,SCS,...
    取能稳定识别的字段，其余置 None；出现异常不抛错。
    """
    out: List[Dict] = []
    for ln in lines or []:
        if "+QENG" not in ln or "neighbourcell" not in ln.lower():
            continue
        # 拆主干
        try:
            payload = ln.split(":", 1)[1].strip()
        except Exception:
            continue
        # 基于逗号粗切，再去引号
        parts = [_tok(p) for p in payload.split(",")]
        # 找 RAT
        rat = None
        mode = None
        if len(parts) >= 2:
            # 可能出现 "...","LTE","FDD",... 或 "...","NR5G",...
            # 先扫前 4 个槽位里是否有 LTE/NR5G / FDD/TDD
            head = [p for p in parts[:4] if p]
            for p in head:
                up = p.upper()
                if up in ("LTE", "NR5G"):
                    rat = up
                if up in ("FDD", "TDD"):
                    mode = up
        # 抽数字（通用）
        nums = re.findall(r"-?\d+", ln)
        mcc = None; mnc = None; tac = None; ci = None
        pci = None; rsrp = None; rsrq = None; rssi = None; sinr = None
        earfcn = None; nrarfcn = None
        if rat == "LTE":
            # LTE 邻区常见顺序（可能有出入）：MCC,MNC,TAC,CI,EARFCN,PCI,RSRQ,RSRP,RSSI
            # 尝试按 tokens 再用数字兜底
            # 从 parts 中定位 earfcn/pci/rsrp/rsrq/rssi
            # 优先关键字，再回落到数字序列位置
            # 直接用数字数组作为容错来源：
            #   按照最后 6~8 个数，依次匹配 PCI/RSRQ/RSRP/RSSI 等
            #   保守起见只要拿到 EARFCN/PCI/RSRP/RSRQ/RSSI 就行
            # 粗提 EARFCN
            m = re.search(r"EARFCN[=\s:]+(-?\d+)", ln, re.I)
            if m: earfcn = _to_int_or_none(m.group(1))
            # 粗提 PCI
            m = re.search(r"PCI[=\s:]+(-?\d+)", ln, re.I)
            if m: pci = _to_int_or_none(m.group(1))
            # 三强指标
            m = re.search(r"RSRP[=\s:]+(-?\d+)", ln, re.I)
            if m: rsrp = _to_int_or_none(m.group(1))
            m = re.search(r"RSRQ[=\s:]+(-?\d+)", ln, re.I)
            if m: rsrq = _to_int_or_none(m.group(1))
            m = re.search(r"RSSI[=\s:]+(-?\d+)", ln, re.I)
            if m: rssi = _to_int_or_none(m.group(1))
            # MCC/MNC/TAC/CI 尝试从 parts（去引号后）按位置兜底
            # 位置并不完全可靠，但通常在 LTE 邻区行靠前
            ints = [p for p in parts if p and re.fullmatch(r"-?\d+", p)]
            if len(ints) >= 2:
                mcc = _to_int_or_none(ints[0]); mnc = _to_int_or_none(ints[1])
            # TAC/CI 可能是十六进制或十进制，保持字符串原样
            tac_m = re.search(r'\b([0-9A-Fa-f]{4,})\b', ln)
            ci_m  = re.search(r'\b([0-9A-Fa-f]{5,})\b', ln)
            if tac_m: tac = tac_m.group(1)
            if ci_m:  ci  = ci_m.group(1)
        elif rat == "NR5G":
            # NR 邻区常见顺序：MCC,MNC,PCI,SS-RSRP,SS-RSRQ,SS-SINR,NRARFCN,SCS,...
            m = re.search(r"\bPCI[=\s:]+(-?\d+)", ln, re.I)
            if m: pci = _to_int_or_none(m.group(1))
            m = re.search(r"SS-?RSRP[=\s:]+(-?\d+)", ln, re.I)
            if m: rsrp = _to_int_or_none(m.group(1))
            m = re.search(r"SS-?RSRQ[=\s:]+(-?\d+)", ln, re.I)
            if m: rsrq = _to_int_or_none(m.group(1))
            m = re.search(r"SINR[=\s:]+(-?\d+)", ln, re.I)
            if m: sinr = _to_int_or_none(m.group(1))
            m = re.search(r"NRARFCN[=\s:]+(-?\d+)", ln, re.I)
            if m: nrarfcn = _to_int_or_none(m.group(1))
            ints = [p for p in parts if p and re.fullmatch(r"-?\d+", p)]
            if len(ints) >= 2:
                mcc = _to_int_or_none(ints[0]); mnc = _to_int_or_none(ints[1])
        # 频段推断
        band = None
        if rat == "LTE":
            band = _guess_lte_band_from_earfcn(earfcn)
        elif rat == "NR5G":
            band = _guess_nr_band_from_nrarfcn(nrarfcn)
        out.append({
            "rat": rat, "mode": mode,
            "mcc": mcc, "mnc": mnc,
            "tac": tac, "ci": ci,
            "pci": pci,
            "earfcn": earfcn, "nrarfcn": nrarfcn,
            "band": band,
            "rsrp": rsrp, "rsrq": rsrq, "rssi": rssi, "sinr": sinr,
        })
    return out


# === Step-5 helpers (safe to append) ===

def _nz(v):
    return v if (v is not None and v != "" and v != -32768) else None


def _band_of(cell: Dict[str, Any]) -> Optional[str]:
    # 允许 key 叫 "band" 或 "nr_band"/"lte_band"
    for k in ("band", "nr_band", "lte_band"):
        b = cell.get(k)
        if b:
            return str(b)
    return None


def _arfcn_of(cell: Dict[str, Any]) -> Optional[int]:
    for k in ("arfcn", "nrarfcn", "earfcn"):
        v = cell.get(k)
        if isinstance(v, int):
            return v
        try:
            return int(v) if v not in (None, "", "-") else None
        except Exception:
            pass
    return None


def _bw_of(cell: Dict[str, Any]) -> Optional[int]:
    # 约定 dl_bw_mhz；若是 kHz/Hz 请在解析处已归一
    for k in ("dl_bw_mhz", "bw_mhz", "bandwidth_mhz"):
        v = cell.get(k)
        try:
            return int(v)
        except Exception:
            pass
    return None


def build_ca_summary(pcc: Optional[Dict[str, Any]], scc_list: List[Dict[str, Any]]) -> Optional[str]:
    """
    生成可读汇总：
    例：NR5G PCC n41@504990 (BW 100MHz), SCC×2: n41@505990, n78@635334
    字段缺失时自动省略，不报错。
    """
    try:
        if not pcc and not scc_list:
            return None
        # PCC 文案
        if pcc:
            rat = pcc.get("rat") or "NR/LTE"
            band = _band_of(pcc)
            arfcn = _arfcn_of(pcc)
            bw    = _bw_of(pcc)
            pcc_main = []
            if band and arfcn:
                pcc_main.append(f"{band}@{arfcn}")
            elif band:
                pcc_main.append(band)
            elif arfcn:
                pcc_main.append(str(arfcn))
            pcc_bw = f"(BW {bw}MHz)" if bw else None
            pcc_txt = f"{rat} PCC " + " ".join([x for x in [", ".join(pcc_main) if pcc_main else None, pcc_bw] if x])
        else:
            pcc_txt = "PCC —"
        # SCC 文案
        scc_txt = ""
        if scc_list:
            parts = []
            for s in scc_list:
                band = _band_of(s)
                arfcn = _arfcn_of(s)
                if band and arfcn:
                    parts.append(f"{band}@{arfcn}")
                elif band:
                    parts.append(band)
                elif arfcn:
                    parts.append(str(arfcn))
            if parts:
                scc_txt = f"SCC×{len(parts)}: " + ", ".join(parts)
            else:
                scc_txt = f"SCC×{len(scc_list)}"
        else:
            scc_txt = "SCC×0"
        return ", ".join([pcc_txt, scc_txt]).strip(", ").strip()
    except Exception:
        return None


# ===== Step-6: NetDev helpers (append-only) =====
import os
import subprocess
import time

def parse_qnetdevstatus(lines: list[str]) -> Optional[Dict[str, Any]]:
    """
    解析 AT+QNETDEVSTATUS 的典型回显（不同固件格式可能不同，此函数做尽量宽松匹配）。
    期望输出：{"iface": "...", "state": "...", "ipv4": "...", "rx_bytes": int, "tx_bytes": int}
    解析不到时返回 None。
    """
    if not lines:
        return None
    # 粗略示例匹配：+QNETDEVSTATUS: <iface>,<state>,<ipv4>,<rx>,<tx>
    patt = re.compile(r'\+QNETDEVSTATUS:\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*(\d+),\s*(\d+)', re.I)
    for ln in lines:
        m = patt.search(ln)
        if m:
            try:
                return {
                    "iface": m.group(1).strip(),
                    "state": m.group(2).strip(),
                    "ipv4":  m.group(3).strip() if m.group(3).strip() not in ("", "0.0.0.0", "N/A") else None,
                    "rx_bytes": int(m.group(4)),
                    "tx_bytes": int(m.group(5)),
                }
            except Exception:
                pass
    return None


def _read_int(path: str) -> Optional[int]:
    try:
        with open(path, "r") as f:
            return int(f.read().strip())
    except Exception:
        return None


def _ip4_of(iface: str) -> Optional[str]:
    try:
        out = subprocess.check_output(["ip", "-4", "-o", "addr", "show", iface], timeout=0.6).decode("utf-8", "ignore")
        m = re.search(r'\sinet\s(\d+\.\d+\.\d+\.\d+)/\d+', out)
        return m.group(1) if m else None
    except Exception:
        return None


def probe_sys_netdev(prefer: list[str] = None) -> Optional[Dict[str, Any]]:
    """
    从 /sys/class/net/<iface>/statistics 读取字节计数；用于 QNETDEVSTATUS 缺省时兜底。
    按优先级挑选接口：默认 ["wwan0","usb0","eth1","eth0"]，若都不存在则挑选有活动地址且非 lo 的接口。
    """
    if prefer is None:
        prefer = ["wwan0", "usb0", "eth1", "eth0"]
    # 选择接口
    candidates = [i for i in prefer if os.path.exists(f"/sys/class/net/{i}")]
    if not candidates:
        try:
            for i in os.listdir("/sys/class/net"):
                if i not in ("lo",) and os.path.exists(f"/sys/class/net/{i}/statistics"):
                    candidates.append(i)
        except Exception:
            pass
    if not candidates:
        return None
    iface = candidates[0]
    rx = _read_int(f"/sys/class/net/{iface}/statistics/rx_bytes")
    tx = _read_int(f"/sys/class/net/{iface}/statistics/tx_bytes")
    ip4 = _ip4_of(iface)
    return {
        "iface": iface,
        "state": "UP" if os.path.exists(f"/sys/class/net/{iface}/carrier") else None,
        "ipv4": ip4,
        "rx_bytes": rx,
        "tx_bytes": tx,
    }


# 进程内速率缓存：{iface: (last_rx, last_tx, last_ts)}
_NETDEV_RATE_CACHE: Dict[str, tuple[int, int, float]] = {}


def with_rates(entry: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    基于进程内缓存计算 rx/tx 速率（bps）。无历史或字段缺失则不填。
    """
    if not entry:
        return entry
    iface = entry.get("iface")
    rx = entry.get("rx_bytes")
    tx = entry.get("tx_bytes")
    if not iface or rx is None or tx is None:
        return entry
    now = time.time()
    last = _NETDEV_RATE_CACHE.get(iface)
    _NETDEV_RATE_CACHE[iface] = (rx, tx, now)
    if not last:
        return entry
    lrx, ltx, lts = last
    dt = max(0.001, now - lts)
    drx = max(0, rx - lrx) if rx >= lrx else 0
    dtx = max(0, tx - ltx) if tx >= ltx else 0
    entry["rx_rate_bps"] = int(drx * 8 / dt)
    entry["tx_rate_bps"] = int(dtx * 8 / dt)
    return entry


# ===== Step-7: PDP/APN/DNS Session Parsers =====

def parse_cgdcont(lines: List[str]) -> Dict[int, Dict[str, Any]]:
    # +CGDCONT: <cid>,"<pdp_type>","<apn>",...
    out = {}
    if not lines: return out
    patt = re.compile(r'\+CGDCONT:\s*(\d+)\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"', re.I)
    for ln in lines:
        m = patt.search(ln)
        if m:
            cid = int(m.group(1))
            out[cid] = out.get(cid, {})
            out[cid]["type"] = (m.group(2) or None)
            out[cid]["apn"]  = (m.group(3) or None)
    return out


def parse_cgact(lines: List[str]) -> Dict[int, int]:
    # +CGACT: <state>,<cid> 或 +CGACT: <cid>,<state> 部分机型互换，这里双向兼容
    out = {}
    if not lines: return out
    pattA = re.compile(r'\+CGACT:\s*(\d+)\s*,\s*(\d+)', re.I)
    for ln in lines:
        m = pattA.search(ln)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            # 取 (cid, state)：猜测较大的作为 cid
            cid, state = (b, a) if b > a else (a, b)
            out[cid] = state
    return out


def parse_cgcontrdp(lines: List[str]) -> Dict[int, Dict[str, Any]]:
    # +CGCONTRDP: <cid>,<bearer_id>,<apn>,"<local_addr>",...,"<dns1>","<dns2>"
    out = {}
    if not lines: return out
    # 宽松匹配：抓 cid、apn、本地 ip、两个 dns（若存在）
    cid_re  = re.compile(r'\+CGCONTRDP:\s*(\d+)\s*,')
    apn_re  = re.compile(r'\+CGCONTRDP:.*?,\s*[^,]+,\s*"?(.*?)"?',)
    ips_re  = re.compile(r'\"([0-9a-fA-F:\.]+)\"')  # 抓双引号内的 IP 串
    for ln in lines:
        m = cid_re.search(ln)
        if not m: 
            continue
        cid = int(m.group(1))
        out[cid] = out.get(cid, {})
        # apn
        m2 = apn_re.search(ln)
        if m2:
            apn = m2.group(1).strip()
            if apn and apn.upper() != "N/A":
                out[cid]["apn"] = apn
        # 所有引号内看作候选 IP，通常顺序里第一是本地 IP，末尾两个是 DNS1/2
        ips = ips_re.findall(ln)
        if ips:
            out[cid]["ip"] = ips[0]
            if len(ips) >= 2: out[cid]["dns1"] = ips[-2]
            if len(ips) >= 3: out[cid]["dns2"] = ips[-1]
    return out


def parse_qidnscfg(lines: List[str]) -> Dict[str, str]:
    # +QIDNSCFG: "IP","<dns1>","<dns2>"
    out = {}
    if not lines: return out
    patt = re.compile(r'\+QIDNSCFG:\s*"IPV?6?"\s*,\s*"([^"]*)"(?:\s*,\s*"([^"]*)")?', re.I)
    for ln in lines:
        m = patt.search(ln)
        if m:
            if m.group(1): out["dns1"] = m.group(1)
            if m.group(2): out["dns2"] = m.group(2)
    return out


# ===== Step-8: Registration & Cell ID Normalization =====

_REG_MAP = {
    0: "not registered / MT is not currently searching",
    1: "registered (home)",
    2: "searching",
    3: "registration denied",
    4: "unknown",
    5: "registered (roaming)",
    6: "registered for SMS only",
    7: "registered for CSFB or SMS only",
    8: "attached for emergency only",
    9: "registered (CSFB not preferred)",
    10: "registered (home, emergency only)",
}


def reg_text(stat: Optional[int]) -> Optional[str]:
    return None if stat is None else _REG_MAP.get(stat, f"stat={stat}")


def _try_int_hex(s: Optional[str]) -> Optional[int]:
    if not s: return None
    try:
        return int(s, 16)
    except Exception:
        # 有些固件给十进制，这里再试一次
        try: return int(s)
        except Exception: return None


def _split_lte_eci(eci_dec: Optional[int]) -> tuple[Optional[int], Optional[int]]:
    # 典型LTE ECI为28位：高 20/21 bits 为 eNB，低 7/8 bits 为小区
    if eci_dec is None: return None, None
    # 用常见的 20/8 拆分作兜底（不同网有差异，但足够演示）
    enb = eci_dec >> 8
    cid = eci_dec & 0xFF
    return enb, cid


def _split_nr_nci(nci_dec: Optional[int]) -> tuple[Optional[int], Optional[int]]:
    # NR Cell Identity 常见 36 bits：高 bits gNB，低 bits CellID
    if nci_dec is None: return None, None
    # 以 28/8 兜底拆分，便于展示（不同网有差异）
    gnb = nci_dec >> 8
    cid = nci_dec & 0xFF
    return gnb, cid


def parse_cereg_stat(lines: List[str]) -> Optional[int]:
    # +CEREG: 0,1[, ...]
    for ln in lines or []:
        m = re.search(r'\+CEREG:\s*\d\s*,\s*(\d+)', ln)
        if m: return int(m.group(1))
    return None


def parse_c5greg_stat(lines: List[str]) -> Optional[int]:
    for ln in lines or []:
        m = re.search(r'\+C5GREG:\s*\d\s*,\s*(\d+)', ln)
        if m: return int(m.group(1))
    return None


def parse_qeng_serving_core(lines: List[str]) -> Dict[str, Any]:
    """
    从 QENG 'servingcell' 行抽核心字段：rat, tac(hex?), pci, arfcn, band(通过已有函数或简单猜测)。
    返回: {"rat":..., "tac_hex":..., "pci":..., "arfcn":..., "band":...}
    不做强耦合，尽量宽松匹配，避免影响现有逻辑。
    """
    out: Dict[str, Any] = {}
    for ln in lines or []:
        if "+QENG:" not in ln: 
            continue
        s = ln.strip()
        if '"LTE"' in s or "NR5G" in s:
            # 提取 RAT
            if '"LTE"' in s: out["rat"] = "LTE"
            elif "NR5G" in s:
                out["rat"] = "NR5G-NSA" if "NSA" in s else "NR5G-SA"
            
            # NR-SA 专用正则：支持两种格式
            # 格式1: +QENG: "servingcell","NOCONN","NR5G-SA","TDD",MCC,MNC,TAC,NCI,...
            # 格式2: +QENG: "NR5G-SA",MCC,MNC,TAC,NCI,...
            # 实际格式：+QENG: "servingcell","NOCONN","NR5G-SA","TDD",460,00,317D32001,800,...
            # 其中 317D32001 可能是 NCI（36位十六进制），800 可能是 TAC（十进制或十六进制）
            # 尝试匹配：在 "NR5G-SA" 之后找到 MCC, MNC，然后提取后续的十六进制或数字
            m_sa = re.search(r'\+QENG:.*?"NR5G-SA".*?,\s*(\d+)\s*,\s*(\d+)\s*,\s*([0-9A-Fa-f]+)\s*,\s*([0-9A-Fa-f]+)', s)
            if m_sa:
                # 判断哪个是 TAC（通常较短，12位十六进制），哪个是 NCI（较长，36位十六进制）
                val1 = m_sa.group(3)
                val2 = m_sa.group(4)
                # 较长的通常是 NCI，较短的通常是 TAC
                if len(val1) >= len(val2):
                    out["nci_hex"] = val1
                    out["tac_hex"] = val2
                else:
                    out["tac_hex"] = val1
                    out["nci_hex"] = val2
            
            # 宽松提取 TAC（可能是 hex）- LTE 或非 SA 场景
            if "tac_hex" not in out:
                # LTE 示例：+QENG: "LTE","FDD",460,00,E12E50,406,1300,3,5,5,1847, ...
                m_tac = re.search(r'\"LTE\".*?,.*?,\d+,\d+,([0-9A-Fa-f]+)', s)
                if m_tac:
                    out["tac_hex"] = m_tac.group(1)
            
            # PCI：取紧跟在 EARFCN/NRARFCN 之后的数
            nums = re.findall(r'-?\d+', s)
            # LTE 样例：..., earfcn(6), pci(7) / NR NSA 示例中 near ARFCN/PCI
            # 我们不强制索引，尽量兼容已有 parse
            # 读取 ARFCN（最大的 5~6 位数字），作为兜底
            candidates = [n for n in nums if len(n) >= 4]
            if candidates:
                out["arfcn"] = candidates[-1]  # 兜底取最后一个大数
            # 简单找PCI（0~1023），兜底从 nums 中找最合适区间
            for n in nums:
                try:
                    v = int(n)
                    if 0 <= v <= 2048:
                        out.setdefault("pci", str(v))
                except: pass
    return out


def pretty_band(rat: str | None, raw_band: str | None) -> str | None:
    if not raw_band: return None
    if rat and "NR" in rat.upper():
        # 允许传入 "n41"/"41"/"NR5G BAND 41" 三种兜底
        s = raw_band.upper().replace("NR5G BAND ", "").replace("N", "")
        return f"NR5G BAND {s}"
    else:
        s = raw_band.upper().replace("LTE BAND ", "").replace("B", "")
        return f"LTE BAND {s}"


# ===== Step-9: Signal Quality Rating =====

def _as_float(s: str | None) -> float | None:
    try: return float(s)
    except: return None


def rate_quality_lte(rsrp: str | None, sinr: str | None) -> tuple[str, str | None]:
    r = _as_float(rsrp); s = _as_float(sinr)
    # 简洁阈值：先看 RSRP，再看 SINR（可调整）
    # LTE RSRP:  >=-80 优 / >=-90 良 / >=-100 中 / 其他差
    if r is not None:
        if r >= -80: q="excellent"
        elif r >= -90: q="good"
        elif r >= -100: q="fair"
        else: q="poor"
    else:
        q="fair"
    # 轻微修正（SINR加权）
    if s is not None:
        if s >= 20 and q in ("good","fair"): q="excellent"
        elif s < 0 and q in ("good","excellent"): q="fair"
    return q, None


def rate_quality_nr(rsrp: str | None, sinr: str | None) -> tuple[str, str | None]:
    r = _as_float(rsrp); s = _as_float(sinr)
    # NR RSRP：>=-80 优 / >=-90 良 / >=-100 中 / 其他差
    if r is not None:
        if r >= -80: q="excellent"
        elif r >= -90: q="good"
        elif r >= -100: q="fair"
        else: q="poor"
    else:
        q="fair"
    if s is not None:
        if s >= 15 and q in ("good","fair"): q="excellent"
        elif s < 0 and q in ("good","excellent"): q="fair"
    return q, None
