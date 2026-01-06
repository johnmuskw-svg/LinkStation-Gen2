# LinkStation Modem API 参考文档

## 总览
LinkStation Modem API 部署在树莓派（或同类 Linux 边缘节点）上，对外提供查询与控制 5G 模组的统一接口。除特殊说明外，所有业务路由都挂载在统一前缀 `API_PREFIX=/v1` 下，并监听在 `http://<device-ip>:8000`。

- **基础 URL 示例**：`http://192.168.1.254:8000`
- **版本前缀**：`/v1`（可通过环境变量 `API_PREFIX` 调整）
- **统一响应外壳**：绝大多数接口返回 `{ ok, ts, error, raw, ... }`
  - `ok`：布尔值，表示本次调用是否成功
  - `ts`：毫秒级 Unix 时间戳，由服务端生成
  - `error`：若 `ok=false`，包含错误描述；成功时为 `null`
  - `raw`：仅在 `?verbose=1` 或控制类接口执行实际 AT 时返回，结构为 `{ "AT+CMD": ["AT+CMD", "...", "OK"] }`

## 鉴权 / 安全
- **X-Api-Token**：当 `.env` 或环境变量设置 `AUTH_REQUIRED=1`（或 `true/yes/on`）时，`/v1/info` 与 `/v1/live` 需要在请求头携带 `X-Api-Token: <config.AUTH_TOKEN>`；`AUTH_REQUIRED=0` 时无需校验。`/v1/health`、`/v1/version` 与 `/v1/ctrl/*` 始终开放。
- **控制总开关**：
  - `CTRL_ENABLE`（环境变量 `LINKSTATION_CTRL_ENABLE`，默认 `True`）关闭后，所有 `/v1/ctrl/*` 仅返回计划（`detail.dry_run=true`），不会发送任何 AT 命令。
  - `CTRL_ALLOW_DANGEROUS`（环境变量 `LINKSTATION_CTRL_ALLOW_DANGEROUS`，默认 `False`）控制“危险动作”是否允许真正执行。被标记为危险的 action（`reboot`/`usbnet`/`apn`/`band`/`cell_lock`/`ca`/`reset_profile`）在该开关为 `0` 时，即使 `dry_run=false` 也只会返回计划而不执行 AT。
- **dry_run 行为**：所有控制请求都继承 `CtrlBaseRequest` 的 `dry_run`，前端可以主动先获取计划；如果 `dry_run=false` 且开关允许，才会调用 `serial_at.send` 真正执行。

## 健康检查与版本
### `GET /v1/health`
简单存活探针。示例：
```bash
curl -s http://192.168.1.254:8000/v1/health | jq
```
响应字段：
- `ok`：恒为 `true`
- `time`：ISO8601 UTC 时间戳，例如 `2025-11-19T05:51:34.123456Z`
- `uptime_sec`：进程自启动以来的秒数（浮点）

示例响应：
```json
{
  "ok": true,
  "time": "2025-11-19T05:51:34.781958Z",
  "uptime_sec": 4589.312345
}
```

### `GET /v1/version`
直接返回 `config.py` 中的运行参数。示例：
```bash
curl -s http://192.168.1.254:8000/v1/version | jq
```
字段说明：
- `api_title`：FastAPI 实例标题，默认 `"LinkStation Modem API"`
- `api_prefix`：当前 API 前缀，例如 `"/v1"`
- `serial_port`：串口路径，如 `/dev/ttyUSB2`
- `baudrate`：串口波特率

示例响应：
```json
{
  "api_title": "LinkStation Modem API",
  "api_prefix": "/v1",
  "serial_port": "/dev/ttyUSB2",
  "baudrate": 115200
}
```

## 静态信息接口：`GET /v1/info`
- **查询参数**：`verbose`（可选，布尔）。当 `true/1` 时，在 `raw` 字段内附带所有 AT 回显。
- **响应结构**：
  - 外层：`ok`, `ts`, `error`, `raw`
  - `info`：`InfoModel`
    - `manufacturer`：`AT+GMI` 结果
    - `model`：`AT+CGMM`
    - `revision`：`AT+GMR`
    - `imei`：`AT+GSN`
  - `sim`：`SimModel`
    - `imsi`：`AT+CIMI`
    - `iccid`：`AT+ICCID`
    - `msisdn`：`AT+CNUM`
    - `enabled` / `inserted`：`AT+QSIMSTAT?` 第 1/2 位
  - `modem.usb`：`UsbSpeedModel`
    - `code`：`AT+QCFG="usbspeed"` 数值，例如 `312`
    - `label`：预置的人类可读描述，如 `"USB 3.1 Gen2, 10 Gbps"`

### 响应示例（正常 / 未请求 raw）
```json
{
  "ok": true,
  "ts": 1732001234567,
  "error": null,
  "info": {
    "manufacturer": "Quectel",
    "model": "RM520N-GL",
    "revision": "RM520NGLAAR04A02M4G",
    "imei": "866012050123456"
  },
  "sim": {
    "imsi": "460011234567890",
    "iccid": "89860123456789012345",
    "msisdn": "+8613800138000",
    "enabled": true,
    "inserted": true
  },
  "modem": {
    "usb": {
      "code": 312,
      "label": "USB 3.1 Gen2, 10 Gbps"
    }
  },
  "raw": null
}
```

### 响应示例（`verbose=1`，含部分回显）
```json
{
  "ok": true,
  "ts": 1732002234567,
  "error": null,
  "info": {
    "manufacturer": "Quectel",
    "model": "RM520N-GL",
    "revision": "RM520NGLAAR04A02M4G",
    "imei": "866012050123456"
  },
  "sim": {
    "imsi": "460011234567890",
    "iccid": "89860123456789012345",
    "msisdn": "+8613800138000",
    "enabled": true,
    "inserted": true
  },
  "modem": {
    "usb": {
      "code": 311,
      "label": "USB 3.1 Gen1, 5 Gbps"
    }
  },
  "raw": {
    "AT+GMI": ["AT+GMI", "Quectel", "OK"],
    "AT+CGMM": ["AT+CGMM", "RM520N-GL", "OK"],
    "AT+GMR": ["AT+GMR", "RM520NGLAAR04A02M4G", "OK"],
    "AT+GSN": ["AT+GSN", "866012050123456", "OK"],
    "AT+CIMI": ["AT+CIMI", "460011234567890", "OK"],
    "AT+ICCID": ["AT+ICCID", "+ICCID: 89860123456789012345", "OK"],
    "AT+CNUM": ["AT+CNUM", "+CNUM: \"\",\"+8613800138000\",145", "OK"],
    "AT+QSIMSTAT?": ["AT+QSIMSTAT?", "+QSIMSTAT: 1,1", "OK"],
    "AT+QCFG=\"usbspeed\"": ["AT+QCFG=\"usbspeed\"", "+QCFG: \"usbspeed\",\"311\"", "OK"]
  }
}
```

## 实时信息接口：`GET /v1/live`
- **查询参数**：`verbose`（可选）。当开启时，`raw` 中包含所有实时 AT 回显，供调试使用。
- **响应结构概览**（参照 `LiveResponse`）：
  - 通用外壳：`ok`, `ts`, `error`, `raw`
  - `reg`：`LiveRegModel`，包含 `cs`/`ps` 注册状态（EPS/PS）。可能为 `null`。
  - `mode`：网络模式，例如 `rat`（`SA`/`NSA`/`LTE`）与 `duplex`（`TDD`/`FDD`）。
  - `operator`：`name`（如 `China Mobile` 或 `46000`），`mcc`，`mnc`。部分字段可能缺省。
  - `signal`：原始合并信号指标（`rsrp`/`rsrq`/`rssi`/`sinr`/`cqi`），单位 dBm/dB。
  - `serving`：当前服务小区详细信息（`rat` + `sa/lte/nsa` 子对象）。
  - `serving_norm`：规范化后的 ID（`tac_hex/tac_dec`、`eci/nci` 拆分、`pci`、`band`、`arfcn`）。
  - `reg_detail`：`RegStatus`，含 `eps`/`nr5g` 数字状态码与 `*_text` 说明。
  - `signal_lte` / `signal_nr`：结构化信号块（字符串字段 + `quality` 和 `note`），若设备未驻留对应 RAT 则为 `null`。
  - `cell` 相关：`serving.sa.*`（NR）、`serving.lte.*`（LTE）字段包含 `pci`、`tac`、`nrarfcn` 等；`serving_norm.id` 同步提供十进制/十六进制形式。
  - `temps`：由 `AT+QTEMP` 解析的模组温度，如 `ambient`、`mmw`、`pa`、`baseband`，字段可能依固件不同而缺省。
  - `ca`：载波聚合信息，包含：
    - `pcc`：主载波 `CA_Pcc`（`band`, `arfcn`, `dl_bw_mhz`, `rsrp`, `rsrq`, `sinr`）
    - `scc[]`：辅载波数组，每项含 `idx`, `band`, `arfcn`, `dl_bw_mhz`, `rsrp`, `rsrq`, `sinr`
    - `summary`：`build_ca_summary` 生成的字符串描述
    - 当无 CA 时 `pcc=null`、`scc=[]`
  - `neighbors`：结构化邻区集合（`lte[]`、`nr[]`），字段参照 `NbLTE`/`NbNR`
  - `neighbours`：面向 UI 的邻区数组（`NeighbourCell`），字段包括 `rat/mode/mcc/mnc/tac/ci/pci/...`。若固件未上报邻区则为空数组。
  - `netdev`：`LiveNetDev`，包含 `iface/state/ipv4/rx_bytes/tx_bytes/rx_rate_bps/tx_rate_bps`，无法获取时为 `null`。
  - `session`：`LiveSessionModel`，包含 `default_cid` 与 `pdp[]`（`cid/type/apn/state/ip/dns1/dns2`）。若未建立数据会话则为空。
  - `raw`：与 `verbose` 关联，包含全部 AT 调用回显。

### 字段补充说明
- `reg` 取值对应 `AT+CGREG?`/`ps` 状态码映射：`home/roaming/searching/denied/...`。
- `reg_detail.eps`/`nr5g` 来自 `AT+CEREG?` 与 `AT+C5GREG?`，典型值 `1`（已注册）/`5`（漫游）。
- `signal`/`signal_lte`/`signal_nr` 的 `rsrp` / `rsrq` 单位 dBm/dB，`sinr` 单位 dB。`quality` 均值级别：`excellent/good/fair/poor`。
- `temps` 的 `ambient` 单位摄氏度；某些固件可能只返回 `raw`。
- `ca` 在无聚合时 `scc` 空数组；`summary` 仅在成功解析后才有文本。
- `neighbors.lte`/`nr` 的 `rsrp/rsrq` 为整数 dBm/dB，可为 `null` 表示固件未上报。
- `netdev.rx_rate_bps/tx_rate_bps` 为瞬时速率估算，可能为 `null`（无采样窗口）。

### 正常运行示例（裁剪版）
```json
{
  "ok": true,
  "ts": 1732003333444,
  "error": null,
  "reg": { "cs": null, "ps": "home" },
  "mode": { "rat": "SA", "duplex": "TDD" },
  "operator": { "name": "46000", "mcc": "460", "mnc": "00" },
  "signal": { "rsrp": -92, "rsrq": -11, "rssi": null, "sinr": 18, "cqi": null },
  "serving": {
    "rat": "SA",
    "sa": {
      "state": "CONNECTED",
      "duplex": "TDD",
      "mcc": "460",
      "mnc": "00",
      "cellid": 439041101234,
      "pcid": 201,
      "tac": "0800",
      "nrarfcn": 635520,
      "band": "NR5G BAND 41",
      "dl_bw_mhz": 80,
      "rsrp": -92,
      "rsrq": -11,
      "sinr": 18,
      "scs_khz": 30,
      "srxlev": 48
    }
  },
  "serving_norm": {
    "rat": "NR5G-SA",
    "band": "NR5G n41",
    "arfcn": "635520",
    "pci": "201",
    "id": {
      "tac_hex": "0800",
      "tac_dec": 2048,
      "nci_hex": "0000000006719FADD2",
      "nci_dec": 439041101234,
      "gnb_id": 1710934,
      "nci_cell_id": 466
    }
  },
  "reg_detail": {
    "eps": 1,
    "nr5g": 1,
    "eps_text": "registered",
    "nr5g_text": "registered"
  },
  "signal_lte": null,
  "signal_nr": {
    "rsrp": "-92",
    "rsrq": "-11",
    "sinr": "18",
    "quality": "good",
    "note": "rsrp>-100 & sinr>10"
  },
  "temps": {
    "ambient": 38.2,
    "mmw": null,
    "pa": {"pa0": 45.0},
    "baseband": {"bb0": 41.5},
    "raw": {"lines": ["+QTEMP: ..."]}
  },
  "ca": {
    "pcc": {"arfcn": 635520, "dl_bw_mhz": 80, "band": "n41", "rsrp": null, "rsrq": null, "sinr": null, "rat": null},
    "scc": [],
    "summary": "PCC n41@635520 (80MHz)"
  },
  "neighbors": {
    "lte": [{"earfcn": 38950, "pci": 120, "rsrp": -105, "rsrq": -15, "sinr": -2, "srxlev": null}],
    "nr": [{"nrarfcn": 635520, "pci": 345, "rsrp": -115, "rsrq": -14, "sinr": 5, "scs_khz": 30}]
  },
  "neighbours": [
    {"rat": "NR", "mode": "SA", "mcc": 460, "mnc": 0, "tac": "0800", "ci": "000006719FADD2", "pci": 345, "nrarfcn": 635520, "rsrp": -115, "sinr": 5}
  ],
  "netdev": {
    "iface": "wwan0",
    "state": "up",
    "ipv4": "10.10.10.3",
    "rx_bytes": 362134589,
    "tx_bytes": 251234012,
    "rx_rate_bps": 18500000,
    "tx_rate_bps": 5200000
  },
  "session": {
    "default_cid": 1,
    "pdp": [
      {"cid": 1, "type": "IPV4V6", "apn": "cmnet", "state": 1, "ip": "10.10.10.3", "dns1": "223.5.5.5", "dns2": "2400:3200::1"},
      {"cid": 2, "type": "IPV6", "apn": "cmims", "state": 0, "ip": null, "dns1": null, "dns2": null}
    ]
  },
  "raw": null
}
```

> 注：以上示例仅展示关键字段；真实响应还包含 `neighbors.nr` 的更多元素以及 `raw`（若启用 verbose）。遇到固件未支持的字段时，对应值会为 `null` 或空数组。

## 控制接口总览：`/v1/ctrl/*`
所有控制请求均为 `POST`，内容类型 `application/json`，请求体继承 `CtrlBaseRequest(dry_run: bool=False)`。通用响应模型 `CtrlBaseResponse` 包含：
- `ok`：请求是否处理成功（语义层面，不代表命令已执行）
- `ts`：毫秒时间戳
- `action`：动作标识（如 `"reboot"`）
- `error`：错误描述（失败时）
- `raw`：当实际执行时记录每条 AT 的回显
- `detail`：`CtrlActionDetail`
  - `dry_run`：本次是否仅返回计划
  - `dangerous`：该 action 是否被标记为危险（需要 `CTRL_ALLOW_DANGEROUS`）
  - `executed`：是否已真正执行 AT 并且全部成功
  - `blocked_reason`：如 `"CTRL_ENABLE=0"` 或 `"CTRL_ALLOW_DANGEROUS=0"`
  - `planned`：即将执行或已执行的 AT 列表
  - `errors`：执行阶段的错误数组
  - `extra`：预留附加信息

已实现的控制动作：
- `POST /v1/ctrl/reboot`：模组软/全重启或仅关闭射频（危险）
- `POST /v1/ctrl/usbnet`：切换 USB 网络模式，支持 `rndis/ecm/mbim/ncm`（危险）
- `POST /v1/ctrl/apn`：配置/激活 APN & 认证（危险）
- `GET /v1/ctrl/roaming`：查询数据漫游状态（安全）
- `POST /v1/ctrl/roaming`：开启/关闭数据漫游（安全）
- `POST /v1/ctrl/band`：设置 LTE/NR5G 频段锁定或 `reset`（危险）
- `POST /v1/ctrl/cell_lock`：锁定/解锁小区与 RAT（危险）
- `POST /v1/ctrl/ca`：切换载波聚合（危险）
- `POST /v1/ctrl/gnss`：启用/禁用 GNSS（安全）
- `POST /v1/ctrl/reset_profile`：恢复"modem_safe"网络配置（危险）

### 数据漫游接口：`GET /v1/ctrl/roaming` 和 `POST /v1/ctrl/roaming`

#### `GET /v1/ctrl/roaming` - 查询数据漫游状态
查询当前数据漫游是否开启。使用 `AT+QNWPREFCFG="roam_pref"` 查询模组配置。

**请求示例**：
```bash
curl -s http://192.168.1.254:8000/v1/ctrl/roaming | jq
```

**响应结构**（`RoamingResponse`）：
- `ok`：调用是否成功
- `ts`：毫秒级时间戳
- `error`：错误信息（成功时为 `null`）
- `roaming.enabled`：数据漫游是否开启（`true` 表示允许漫游，`false` 表示仅 home 网络）
- `raw`：原始 AT 回显行列表（可选）

**响应示例**：
```json
{
  "ok": true,
  "ts": 1732004455000,
  "error": null,
  "roaming": {
    "enabled": true
  },
  "raw": [
    "AT+QNWPREFCFG=\"roam_pref\"",
    "+QNWPREFCFG: \"roam_pref\",255",
    "OK"
  ]
}
```

#### `POST /v1/ctrl/roaming` - 设置数据漫游开关
启用或禁用数据漫游。使用 `AT+QNWPREFCFG="roam_pref",<value>` 设置配置：
- `enabled=true` → `roam_pref=255`（允许漫游到任意网络）
- `enabled=false` → `roam_pref=1`（仅 home 网络，不允许漫游）

**请求体**（`CtrlRoamingRequest`）：
- `enable`：`bool`，是否启用数据漫游（必填）
- `dry_run`：`bool`，是否仅返回计划（默认 `false`）

**请求示例**：
```bash
curl -X POST http://192.168.1.254:8000/v1/ctrl/roaming \
  -H 'Content-Type: application/json' \
  -d '{"enable": true, "dry_run": false}' | jq
```

**响应结构**（`RoamingResponse`）：
- `ok`：调用是否成功
- `ts`：毫秒级时间戳
- `error`：错误信息（成功时为 `null`）
- `roaming.enabled`：设置后的漫游状态（设置成功后会重新查询确认）
- `raw`：原始 AT 回显行列表（包含设置命令和查询确认的回显）

**响应示例**（成功设置）：
```json
{
  "ok": true,
  "ts": 1732004455000,
  "error": null,
  "roaming": {
    "enabled": true
  },
  "raw": [
    "AT+QNWPREFCFG=\"roam_pref\"",
    "+QNWPREFCFG: \"roam_pref\",255",
    "OK"
  ]
}
```

**注意事项**：
- 这是**安全动作**，不需要设置 `CTRL_ALLOW_DANGEROUS=1` 即可执行
- 设置成功后会自动重新查询状态以确认生效
- 开启漫游可能产生额外费用，但不会立即断网（若仍在本地网络）
- 当 `CTRL_ENABLE=0` 或 `dry_run=true` 时，不会真正执行 AT 命令，仅返回当前状态

## NVR 集成接口：`/v1/nvr/*`
后端提供代理 NVR 服务的接口，用于查询 NVR 健康状态和摄像头列表。

### 配置说明
NVR 集成通过环境变量配置（可在 `.env` 文件中设置）：
- `NVR_ENABLED`：是否启用 NVR 集成（默认 `1`，即启用）
- `NVR_HOST`：NVR 服务的主机地址（默认 `192.168.99.11`）
- `NVR_PORT`：NVR 服务的端口（默认 `8787`）
- `NVR_API_PREFIX`：NVR API 前缀（默认 `/v1`）
- `NVR_BASE_URL`：NVR 服务的基础 URL（可选，如果设置则优先使用，否则根据 HOST+PORT+PREFIX 组合）
- `NVR_TIMEOUT`：请求超时时间，单位秒（默认 `3.0`）

**环境变量示例**（推荐使用细粒度配置）：
```bash
export NVR_ENABLED=1
export NVR_HOST=192.168.99.11
export NVR_PORT=8787
export NVR_API_PREFIX=/v1
export NVR_TIMEOUT=3.0
```

**向后兼容**（仍支持直接设置 NVR_BASE_URL）：
```bash
export NVR_ENABLED=1
export NVR_BASE_URL=http://192.168.99.11:8787/v1
export NVR_TIMEOUT=3.0
```

### `GET /v1/nvr/health`
代理 NVR 的 `/v1/health` 接口，用于查询 NVR 服务健康状态。

**请求示例**：
```bash
curl -s http://127.0.0.1:8000/v1/nvr/health | python3 -m json.tool
```

**响应结构**：
- `ok`：调用是否成功
- `ts`：毫秒级时间戳（来自 NVR 响应）
- `nvr`：NVR 服务的原始响应数据

**响应示例**：
```json
{
  "ok": true,
  "ts": 1732004455000,
  "nvr": {
    "status": "healthy",
    "version": "1.0.0"
  }
}
```

**错误处理**：
- 当 `NVR_ENABLED=0` 时，返回 `503 Service Unavailable`，错误信息为 `"NVR integration disabled"`
- 当 NVR 服务不可达或超时时，返回 `502 Bad Gateway`，错误信息包含具体失败原因

### `GET /v1/nvr/cameras`
代理 NVR 的 `/v1/cameras` 接口，用于获取摄像头列表。

**请求示例**：
```bash
curl -s http://127.0.0.1:8000/v1/nvr/cameras | python3 -m json.tool
```

**响应结构**：
- `ok`：调用是否成功
- `ts`：毫秒级时间戳（来自 NVR 响应）
- `cameras`：摄像头数组，每个元素包含摄像头信息

**响应示例**：
```json
{
  "ok": true,
  "ts": 1732004455000,
  "cameras": [
    {
      "id": "camera-001",
      "name": "Front Door",
      "status": "online"
    },
    {
      "id": "camera-002",
      "name": "Back Yard",
      "status": "online"
    }
  ]
}
```

**错误处理**：
- 当 `NVR_ENABLED=0` 时，返回 `503 Service Unavailable`
- 当 NVR 服务不可达或超时时，返回 `502 Bad Gateway`

### 集成 NVR 自测方式
1. **设置环境变量**（在 `.env` 文件或系统环境变量中）：
   ```bash
   export NVR_ENABLED=1
   export NVR_HOST=192.168.99.11
   export NVR_PORT=8787
   export NVR_API_PREFIX=/v1
   export NVR_TIMEOUT=3.0
   ```

2. **重启后端服务**（如果修改了环境变量）：
   ```bash
   sudo systemctl restart modem-api.service
   ```

3. **测试健康检查接口**：
   ```bash
   curl -s http://127.0.0.1:8000/v1/nvr/health | python3 -m json.tool
   ```
   返回的 `nvr` 字段应该和直接请求 NVR 的 `/v1/health` 接口保持一致。

4. **测试摄像头列表接口**：
   ```bash
   curl -s http://127.0.0.1:8000/v1/nvr/cameras | python3 -m json.tool
   ```
   返回的 `cameras` 字段应该和直接请求 NVR 的 `/v1/cameras` 接口保持一致。

**注意事项**：
- 确保后端服务器能够访问 NVR 服务（网络连通性）
- 如果 NVR 服务不可用，接口会返回 `502` 错误，但不会影响其他 API 的正常工作
- 可以通过设置 `NVR_ENABLED=0` 临时禁用 NVR 集成功能

## 服务管理与部署
### systemd 服务
LinkStation Modem API 已配置为 systemd 服务，支持开机自启和崩溃自动重启。

- **服务名称**：`modem-api.service`
- **服务文件位置**：`/etc/systemd/system/modem-api.service`
- **工作目录**：`/opt/linkstation/modem-api`
- **开机自启**：已启用（`enabled`）

### 常用操作命令
```bash
# 启动服务
sudo systemctl start modem-api.service

# 停止服务
sudo systemctl stop modem-api.service

# 重启服务
sudo systemctl restart modem-api.service

# 查看服务状态
sudo systemctl status modem-api.service

# 查看服务日志
sudo journalctl -u modem-api.service -f

# 查看最近 50 行日志
sudo journalctl -u modem-api.service -n 50
```

### 服务配置说明
- **自动重启**：服务配置了 `Restart=on-failure` 和 `RestartSec=5`，当服务异常退出时会自动重启
- **环境变量**：可通过修改 `/etc/systemd/system/modem-api.service` 添加 `Environment=` 行来设置环境变量
- **日志输出**：服务日志通过 systemd journal 管理，可使用 `journalctl` 查看

### 串口自动重连
服务实现了串口自动修复连接功能：
- 当遇到串口 I/O 错误（如模组重启、USB 抖动）时，会自动尝试重连一次
- 重连成功后会自动重试失败的 AT 命令
- 如果重连后仍然失败，会返回错误信息，但服务进程不会退出
- 重连过程会记录在日志中，可通过 `journalctl` 查看

## 文档校验与维护
1. **路径校验**：使用 `grep -R "@router" routes/` 或 IDE 搜索，确认文档列出的 `/v1/*` 路径与 `routes/*.py` 完全一致。
2. **接口实测**：至少执行一次以下调用，确保响应结构与示例匹配：
   - `curl -H "X-Api-Token: ..." http://<ip>:8000/v1/info`
   - `curl -H "X-Api-Token: ..." http://<ip>:8000/v1/live`
   - `curl -s http://<ip>:8000/v1/ctrl/roaming`（GET 查询）
   - `curl -X POST http://<ip>:8000/v1/ctrl/roaming -d '{"enable":true,"dry_run":true}' -H 'Content-Type: application/json'`（POST 设置）
3. **变更流程**：当 `routes/info.py`、`routes/live.py`、`routes/ctrl.py` 或 `routes/schemas.py` 发生字段/路径调整（包括新增控制 action、LiveResponse 字段改名等），必须同步更新本文档的对应章节与示例。
4. **JSON 自检**：保存前用 `python3 -m json.tool` 验证示例 JSON；确保所有路径以 `/v1/` 开头。
