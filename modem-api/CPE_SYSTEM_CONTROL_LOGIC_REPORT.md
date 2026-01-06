# CPE 系统控制逻辑报告

**项目名称**: LinkStation Gen2 (CPE 网络终端系统)  
**审计日期**: 2025-12-18  
**代码库路径**: `/opt/linkstation/modem-api`  
**总代码行数**: 约 5,358 行 Python 代码

---

## 目录

1. [5G 模组控制](#1-5g-模组控制)
2. [路由与网络](#2-路由与网络)
3. [双机通信](#3-双机通信)
4. [代码质量分析](#4-代码质量分析)
5. [技术架构总结](#5-技术架构总结)
6. [风险评估与建议](#6-风险评估与建议)

---

## 1. 5G 模组控制

### 1.1 通信接口

**接口类型**: **串口通信** (`/dev/ttyUSB*`)

**实现位置**: `core/serial_port.py`

**关键配置**:
- **默认串口**: `/dev/ttyUSB2` (可通过 `SERIAL_PORT` 环境变量配置)
- **波特率**: `115200` (可通过 `BAUDRATE` 环境变量配置)
- **通信协议**: **AT 指令集** (Quectel 标准)

**串口自动识别机制**:
```python
# core/serial_port.py:129-141
def _resolve_port_path(self) -> str:
    """确定当前可用的串口路径"""
    # 1. 优先使用配置的端口
    if os.path.exists(self._preferred_port):
        return self._preferred_port
    # 2. 通过接口ID查找（记录上次使用的接口）
    alt = self._find_port_by_interface()
    if alt:
        return alt
    # 3. 扫描所有 ttyUSB* 设备，匹配接口后缀 ":1.2"
    alt = self._scan_for_expected_interface()
    if alt:
        return alt
    raise SerialATError("Serial device not found")
```

**接口识别逻辑**:
- 通过 `/sys/class/tty/` 解析 USB 接口 ID（形如 `2-1:1.2`）
- 记录接口信息，支持 USB 热插拔后自动重新匹配
- 默认期望接口后缀: `:1.2` (Quectel AT 接口)

### 1.2 AT 指令集

**使用的 AT 指令** (部分列表):

#### 信息查询类
- `AT+GMI` - 查询厂商
- `AT+CGMM` - 查询模组型号
- `AT+GMR` - 查询固件版本
- `AT+GSN` - 查询 IMEI
- `AT+CIMI` - 查询 IMSI
- `AT+ICCID` - 查询 SIM 卡 ICCID
- `AT+CNUM` - 查询本机号码
- `AT+QSIMSTAT?` - 查询 SIM 卡状态

#### 网络状态类
- `AT+CGREG?` - 查询 GPRS 注册状态
- `AT+CEREG?` - 查询 EPS (LTE) 注册状态
- `AT+C5GREG?` - 查询 5G 注册状态
- `AT+QNWINFO` - 查询网络信息
- `AT+QRSRP` - 查询 RSRP (参考信号接收功率)
- `AT+QRSRQ` - 查询 RSRQ (参考信号接收质量)
- `AT+QSINR` - 查询 SINR (信号干扰噪声比)
- `AT+QENG="servingcell"` - 查询服务小区信息
- `AT+QENG="neighbourcell"` - 查询邻区信息
- `AT+QCAINFO` - 查询载波聚合信息
- `AT+QTEMP` - 查询温度

#### 控制类
- `AT+CFUN=<fun>[,<rst>]` - 功能控制/重启
- `AT+QNWPREFCFG="mode_pref",<mode>` - 网络模式选择
- `AT+QNWPREFCFG="roam_pref",<pref>` - 漫游偏好设置
- `AT+QCFG="band",<rat>,<band_list>` - 频段锁定
- `AT+QCFG="ca",<enable>` - 载波聚合开关
- `AT+QCFG="usbnet",<mode>` - USB 网络模式
- `AT+CGDCONT=<cid>,<pdp_type>,<apn>` - APN 配置
- `AT+CGACT=1,<cid>` - 激活 PDP 上下文

**完整指令列表**: 参考 `ctrl_commands_summary.json` 和 `ctrl_commands_summary.md`

### 1.3 看门狗 (Watchdog) 逻辑

**实现位置**: `core/serial_port.py:231-273`

**自动重连机制**:

```python
def send(self, cmd: str, deadline: float = _DEFAULT_DEADLINE) -> List[str]:
    """发送一条 AT 并在看到 OK/ERROR 就立刻返回原始回显行
    
    如果遇到 I/O 错误，会自动重连一次再重试。
    """
    with self._mu:  # 线程锁保证串行执行
        try:
            return self._execute_at(cmd, deadline)
        except (OSError, IOError, serial.SerialException) as e:
            # I/O 错误：自动重连
            logger.warning("Serial I/O error... Attempting reconnect...")
            self.reset()
            # 重连计划：等待 2s, 5s, 10s
            wait_plan = [2.0, 5.0, 10.0]
            for wait_seconds in wait_plan:
                try:
                    self._open(wait_for_device=wait_seconds)
                    logger.info("Serial port reconnected... retrying...")
                    return self._execute_at(cmd, deadline)  # 重试
                except Exception as reconnect_exc:
                    last_error = reconnect_exc
                    self.reset()
                    continue
            # 所有重连尝试失败，抛出异常
            raise SerialATError("Serial I/O error after reconnect attempts...")
```

**重连策略**:
- **触发条件**: 串口 I/O 错误（设备断开、USB 抖动等）
- **重连次数**: 最多 3 次（等待时间: 2s, 5s, 10s）
- **超时保护**: 单条 AT 指令默认超时 1.2 秒
- **线程安全**: 使用 `threading.Lock()` 保证 AT 指令串行执行

**拨号失败处理**:
- **当前实现**: 没有专门的拨号失败检测逻辑
- **依赖**: 依赖模组自身的网络注册状态（通过 `AT+CEREG?` / `AT+C5GREG?` 查询）
- **建议**: 可以添加网络注册状态监控，检测到长时间未注册时触发重连或重启

### 1.4 轮询机制

**实现位置**: `core/poller.py`

**轮询间隔**: `1.0` 秒（可通过 `POLL_INTERVAL` 配置）

**轮询内容**:
```python
def _loop():
    while _running:
        try:
            qeng   = _send('AT+QENG="servingcell"', 1.2)
            cereg  = _send('AT+CEREG?', 0.8)
            c5greg = _send('AT+C5GREG?', 0.8)
            cops   = _send('AT+COPS?', 0.8)
            qtemp  = _send('AT+QTEMP', 1.2)
            # 更新状态到 state 对象
            state.set_live(payload)
        except Exception:
            # 出错也不影响下一轮
            pass
        time.sleep(_POLL_INTERVAL)
```

**状态存储**: `core/state.py` - 线程安全的状态对象，使用 `threading.Lock()` 保护

---

## 2. 路由与网络

### 2.1 路由表操作

**实现位置**: `routes/net.py`

**路由查询**:
```python
# routes/net.py:16-74
def _get_current_uplink_mode() -> Optional[Literal["sim", "wifi"]]:
    """通过 ip route 判断当前默认路由的网卡，确定当前上网出口模式"""
    result = subprocess.run(["ip", "route"], ...)
    # 查找 metric 最小的 default 路由
    # 返回 "sim" (usb0) 或 "wifi" (wlan0)
```

**路由操作**: **只读查询**，不直接修改路由表

**路由切换**: 通过外部脚本 `/usr/local/sbin/ls-uplink` 执行（需要 sudo 权限）

### 2.2 防火墙操作

**防火墙类型**: **nftables** (不是 iptables)

**实现位置**: `restore_nvr_forwarding.sh`

**关键操作**:
```bash
# 1. 开启 IP 转发
sudo sysctl -w net.ipv4.ip_forward=1

# 2. 配置 nftables 规则
sudo nft -f - <<EOF
table inet filter {
  chain forward {
    type filter hook forward priority 0; policy drop;
    ct state established,related accept
    # App侧 -> NVR侧 放行
    iif "$UP_IF" oif "$NVR_IF" ip daddr 192.168.99.11 tcp dport 8787 accept
    # 反向回包放行
    iif "$NVR_IF" oif "$UP_IF" accept
  }
}

table ip nat {
  chain postrouting {
    type nat hook postrouting priority 100; policy accept;
    # App侧访问 192.168.99.0/24 时，源地址伪装成二代的 99 网段地址
    oif "$NVR_IF" ip daddr 192.168.99.0/24 masquerade
  }
}
EOF
```

**网络接口识别**:
- **NVR 接口**: 自动查找 IP 为 `192.168.99.x` 的网卡（通常是 `eth0`）
- **上游接口**: 使用默认路由的网卡（通常是 `wlan0` 或 `usb0`）

### 2.3 DHCP 分配

**当前实现**: **不直接操作 DHCP**

**NVR IP 分配**:
- NVR 通过静态 IP 配置（`192.168.99.11`）
- CPE 主机 IP: `192.168.99.1` (eth0)
- 通过 NAT masquerade 实现 App → NVR 的访问

**网络架构**:
```
App (192.168.71.x) 
  ↓ (wlan0/usb0)
CPE (192.168.99.1) 
  ↓ (eth0, NAT masquerade)
NVR (192.168.99.11:8787)
```

---

## 3. 双机通信

### 3.1 CPE 与 NVR 通信

**通信方式**: **HTTP REST API 代理**

**实现位置**: `routes/nvr.py`, `nvr_client.py`

**NVR 客户端**:
```python
# nvr_client.py:11-44
class NvrClient:
    def __init__(self):
        self.base_url = config.NVR_BASE_URL  # 默认: http://192.168.99.11:8787
        self.timeout = config.NVR_TIMEOUT     # 默认: 3.0 秒
    
    def health(self) -> Dict[str, Any]:
        return self._get("/v1/health")
    
    def list_cameras(self) -> Dict[str, Any]:
        return self._get("/v1/cameras")
    
    def live_hls(self, ip: str, profile: str = "sub") -> Dict[str, Any]:
        return self._get(f"/v1/cameras/{ip}/live-hls?profile={profile}")
```

**CPE "接管" NVR 的方式**:
1. **代理 API 请求**: CPE 作为中间层，App 通过 CPE 访问 NVR
2. **URL 重写**: 将 RTSP URL 重写为通过 CPE 统一入口访问
3. **HLS 流代理**: 代理 HLS 播放列表和切片文件

**URL 重写逻辑** (`routes/nvr.py:19-65`):
```python
def _rewrite_stream_urls_for_public(data: dict, ip: str) -> dict:
    """将 RTSP URL 中的主机和端口重写为 NVR 统一入口地址"""
    # 计算外部端口：9550 + (最后一段 IP - 100)
    # 例如: 192.168.11.103 -> 端口 9553
    external_port = config.NVR_PUBLIC_SUB_BASE_PORT + offset
    public_host = config.NVR_PUBLIC_HOST
    # 重写 URL: rtsp://192.168.11.103:554 -> rtsp://192.168.99.1:9553
```

### 3.2 App 与 CPE 通信 API

**API 基础信息**:
- **基础 URL**: `http://192.168.99.1:8000`
- **API 前缀**: `/v1`
- **认证**: 可选（通过 `AUTH_REQUIRED` 环境变量控制）

#### 3.2.1 系统信息接口

| 端点 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/v1/health` | GET | 健康检查 | 否 |
| `/v1/version` | GET | 版本信息 | 否 |
| `/v1/base/info` | GET | 主机系统信息 | 否 |
| `/v1/info` | GET | 模组基本信息 | 可选 |
| `/v1/live` | GET | 实时网络状态 | 可选 |
| `/v1/gnss/live` | GET | GNSS 实时数据 | 可选 |

#### 3.2.2 控制接口

| 端点 | 方法 | 说明 | 危险级别 |
|------|------|------|----------|
| `/v1/ctrl/reboot` | POST | 模组重启 | 危险 |
| `/v1/ctrl/usb_net` | POST | USB 网络模式切换 | 危险 |
| `/v1/ctrl/apn` | POST | APN 配置 | 危险 |
| `/v1/ctrl/network_mode` | GET/POST | 网络模式选择 | 安全 |
| `/v1/ctrl/band_preference` | GET/POST | 频段偏好设置 | 安全 |
| `/v1/ctrl/band` | POST | 频段锁定 | 危险 |
| `/v1/ctrl/cell_lock` | POST | 小区锁定 | 危险 |
| `/v1/ctrl/ca` | POST | 载波聚合开关 | 安全 |
| `/v1/ctrl/roaming` | GET/POST | 数据漫游控制 | 安全 |
| `/v1/ctrl/gnss` | POST | GNSS 控制 | 安全 |
| `/v1/ctrl/reset_profile` | POST | 一键恢复默认配置 | 危险 |

#### 3.2.3 NVR 代理接口

| 端点 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/v1/nvr/health` | GET | NVR 健康状态 | 否 |
| `/v1/nvr/cameras` | GET | 摄像头列表 | 否 |
| `/v1/nvr/cameras/{ip}/stream` | GET | 摄像头 RTSP 流信息 | 否 |
| `/v1/nvr/cameras/{ip}/live-hls` | GET | HLS 播放地址 | 否 |
| `/v1/nvr/recordings` | GET | 录像列表 | 否 |
| `/v1/nvr/recordings/{ip}/days` | GET | 某摄像头日期列表 | 否 |
| `/v1/nvr/recordings/{ip}/days/{date}/segments` | GET | 某天片段列表 | 否 |
| `/v1/nvr/recordings/{ip}/files/{date}/{filename}` | GET | 录像文件流 | 否 |

#### 3.2.4 HLS 静态文件代理

| 端点 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/live/{ip}/{profile}/index.m3u8` | GET | HLS 播放列表 | 否 |
| `/live/{ip}/{profile}/{filename:path}` | GET | HLS 切片文件 | 否 |

#### 3.2.5 网络管理接口

| 端点 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/v1/net/uplink` | GET | 查询上网出口模式 | 可选 |
| `/v1/net/uplink` | POST | 切换上网出口 (sim/wifi) | 可选 |

#### 3.2.6 认证接口

| 端点 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/v1/base/auth/check` | POST | 检查密码 | 否 |
| `/v1/base/auth/set` | POST | 设置密码 | 否 |

**完整 API 文档**: 参考 `docs/LINKSTATION_API_REFERENCE.md`

---

## 4. 代码质量分析

### 4.1 代码规模统计

**主要文件行数**:
- `routes/live.py`: **1,171 行** ⚠️
- `routes/serving_parsers.py`: **1,003 行** ⚠️
- `routes/ctrl.py`: **990 行** ⚠️
- `routes/schemas.py`: **440 行**
- `routes/base.py`: **376 行**
- `core/serial_port.py`: **275 行**
- `routes/nvr.py`: **262 行**
- `routes/net.py`: **237 行**

### 4.2 代码异味 (Code Smells)

#### ⚠️ 超长函数

**问题函数**: `routes/live.py:_build_live_response()`

**行数**: **489 行** (远超 100 行建议)

**问题分析**:
- 函数职责过多：AT 指令执行、数据解析、响应组装
- 包含大量 try-except 块，错误处理分散
- 难以测试和维护

**建议重构**:
```python
# 建议拆分为：
def _build_live_response(verbose: bool, ts: int) -> LiveResponse:
    # 1. 执行 AT 指令
    at_responses = _execute_live_at_commands()
    # 2. 解析数据
    parsed_data = _parse_live_responses(at_responses)
    # 3. 组装响应
    return _assemble_live_response(parsed_data, verbose, ts)
```

#### ⚠️ 潜在死循环

**位置**: `core/serial_port.py:147-169`

```python
def _open(self, wait_for_device: float = 0.0):
    deadline = time.time() + wait_for_device if wait_for_device else None
    last_exc: Optional[Exception] = None
    while True:  # ⚠️ 无限循环
        try:
            # ... 打开串口
            return
        except Exception as exc:
            last_exc = exc
        if deadline and time.time() < deadline:
            time.sleep(1.0)
            continue
        raise last_exc  # 有退出条件，但不够明显
```

**风险评估**: **低风险** - 有 `deadline` 检查，但代码可读性差

**建议**: 改为更明确的循环条件：
```python
while deadline is None or time.time() < deadline:
    # ...
```

#### ⚠️ 另一个潜在死循环

**位置**: `core/serial_port.py:188-203`

```python
def _read_until_done(self, deadline: float) -> List[str]:
    t0 = time.time()
    buf = bytearray()
    done = False
    while True:  # ⚠️ 无限循环
        chunk = self._ser.read(_READ_CHUNK)
        if chunk:
            buf.extend(chunk)
            if _done(buf):
                done = True
                break
        # 超时保护
        if time.time() - t0 >= deadline:
            break
        if not chunk:
            time.sleep(0.01)
```

**风险评估**: **低风险** - 有超时检查，但循环条件不明确

#### ✅ 轮询循环（正常）

**位置**: `core/poller.py:48-81`

```python
def _loop():
    global _running
    while _running:  # ✅ 有明确的退出条件
        try:
            # ... 轮询逻辑
        except Exception:
            pass
        time.sleep(_POLL_INTERVAL)
```

**评估**: **正常** - 有 `_running` 标志控制退出

### 4.3 代码质量亮点

#### ✅ 线程安全
- 使用 `threading.Lock()` 保护串口操作
- 状态对象使用锁保护共享数据

#### ✅ 错误处理
- 统一的异常类型 `SerialATError`
- 自动重连机制
- 防御式编程（大量 try-except）

#### ✅ 配置管理
- 环境变量配置（`.env` 文件）
- 配置验证和默认值

#### ✅ 安全机制
- 危险操作保护（`CTRL_ALLOW_DANGEROUS`）
- 干运行模式（`dry_run`）
- 可选认证中间件

### 4.4 代码结构

**架构模式**:
- **单例模式**: `serial_at` 全局单例
- **依赖注入**: FastAPI 的 `Depends()` 机制
- **路由分离**: 按功能模块分离路由文件

**模块职责**:
- `core/`: 核心功能（串口、轮询、状态）
- `routes/`: API 路由处理
- `config.py`: 配置管理
- `nvr_client.py`: NVR 客户端封装

---

## 5. 技术架构总结

### 5.1 系统架构图

```
┌─────────────┐
│   App       │
│ (Mobile)    │
└──────┬──────┘
       │ HTTP/HTTPS
       │ 192.168.99.1:8000
       ▼
┌─────────────────────────────────┐
│   CPE (LinkStation Gen2)        │
│                                 │
│  ┌──────────────────────────┐  │
│  │  FastAPI (modem-api)     │  │
│  │  Port: 8000              │  │
│  └───────────┬──────────────┘  │
│              │                  │
│  ┌───────────▼──────────────┐  │
│  │  Serial Port (/dev/ttyUSB2)│ │
│  │  AT Commands             │  │
│  └───────────┬──────────────┘  │
│              │                  │
│  ┌───────────▼──────────────┐  │
│  │  5G Modem (Quectel)      │  │
│  │  RM520N-CN               │  │
│  └──────────────────────────┘  │
│                                 │
│  ┌──────────────────────────┐  │
│  │  NetworkManager          │  │
│  │  - usb0 (5G)             │  │
│  │  - wlan0 (WiFi)          │  │
│  │  - eth0 (NVR)            │  │
│  └──────────────────────────┘  │
└───────────┬────────────────────┘
            │
            │ eth0 (192.168.99.0/24)
            │ NAT Masquerade
            ▼
┌─────────────┐
│   NVR       │
│ 192.168.99.11│
│ Port: 8787  │
└─────────────┘
```

### 5.2 关键技术栈

- **Web 框架**: FastAPI (Python)
- **串口通信**: pyserial
- **HTTP 客户端**: requests
- **数据验证**: Pydantic v2
- **防火墙**: nftables
- **网络管理**: NetworkManager + iproute2
- **服务管理**: systemd

### 5.3 数据流

**App → CPE → NVR**:
1. App 请求: `GET /v1/nvr/cameras/192.168.11.103/live-hls`
2. CPE 代理: `GET http://192.168.99.11:8787/v1/cameras/192.168.11.103/live-hls`
3. NVR 返回: `{"hls": {"playlist": "/live/192.168.11.103/main/index.m3u8"}}`
4. CPE 返回: 保持相对路径，App 通过 CPE 访问静态文件

**5G 模组 → CPE → App**:
1. 轮询线程: 每秒执行 AT 指令查询网络状态
2. 状态更新: 更新到 `state` 对象
3. App 请求: `GET /v1/live`
4. CPE 返回: 从 `state` 对象读取最新状态

---

## 6. 风险评估与建议

### 6.1 高风险项

#### ⚠️ 1. 超长函数 (`_build_live_response`)
- **风险**: 难以维护、测试困难
- **影响**: 中等
- **建议**: 重构为多个小函数

#### ⚠️ 2. 缺少拨号失败检测
- **风险**: 网络断开时无法自动恢复
- **影响**: 中等
- **建议**: 添加网络注册状态监控，检测到长时间未注册时触发重连

#### ⚠️ 3. 无限循环可读性差
- **风险**: 代码维护困难
- **影响**: 低
- **建议**: 改为明确的循环条件

### 6.2 中风险项

#### ⚠️ 4. 错误处理过于宽泛
- **位置**: `core/poller.py:78-80`
```python
except Exception:
    # 出错也不影响下一轮
    pass
```
- **风险**: 可能掩盖重要错误
- **建议**: 记录错误日志，区分可忽略和不可忽略的错误

#### ⚠️ 5. 配置文件权限
- **位置**: `config/base_auth.json` (root:root)
- **风险**: 服务以 root 运行，权限过大
- **建议**: 考虑以非 root 用户运行服务

### 6.3 低风险项

#### ✅ 6. 线程安全
- **状态**: 良好
- **实现**: 使用锁保护共享资源

#### ✅ 7. 超时保护
- **状态**: 良好
- **实现**: AT 指令有超时限制（1.2秒）

### 6.4 改进建议

1. **代码重构**:
   - 拆分超长函数（`_build_live_response`）
   - 提取公共解析逻辑到独立模块

2. **监控增强**:
   - 添加网络注册状态监控
   - 添加串口健康检查
   - 添加 NVR 连接状态监控

3. **错误处理**:
   - 区分错误类型（可重试 vs 不可重试）
   - 添加错误统计和告警

4. **测试覆盖**:
   - 添加单元测试
   - 添加集成测试
   - 添加串口模拟测试

5. **文档完善**:
   - API 文档已完善 ✅
   - 添加架构设计文档
   - 添加部署运维文档

---

## 7. 总结

### 7.1 系统特点

- ✅ **模块化设计**: 功能模块清晰分离
- ✅ **自动恢复**: 串口自动重连机制
- ✅ **安全机制**: 危险操作保护、可选认证
- ✅ **代理架构**: CPE 作为 App 和 NVR 的中间层

### 7.2 技术债务

- ⚠️ **代码复杂度**: 部分函数过长，需要重构
- ⚠️ **监控不足**: 缺少网络状态自动恢复机制
- ⚠️ **错误处理**: 部分错误处理过于宽泛

### 7.3 总体评价

**代码质量**: **良好** (7/10)
- 功能完整，架构清晰
- 有自动恢复机制
- 需要重构超长函数

**可维护性**: **中等** (6/10)
- 模块化良好
- 但部分函数过长，影响可读性

**稳定性**: **良好** (7/10)
- 有自动重连机制
- 有超时保护
- 缺少网络状态监控

---

**报告生成时间**: 2025-12-18  
**审计人员**: AI Assistant  
**版本**: 1.0

