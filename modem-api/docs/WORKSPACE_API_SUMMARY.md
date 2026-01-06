# LinkStation Modem API - Workspace 总结

## 1. 目录结构

### `core/` - 核心功能模块
- `serial_port.py`: 串口通信管理，实现 AT 指令发送、自动重连、设备检测
- `state.py`: 状态管理（缓存查询结果）
- `poller.py`: 后台轮询机制

### `routes/` - API 路由模块
- `health.py`: 健康检查和版本信息
- `info.py`: 静态信息查询（模组信息、SIM卡信息）
- `live.py`: 实时信息查询（网络状态、信号质量、CA信息）
- `ctrl.py`: 控制接口（网络模式、频段、CA、漫游等）
- `schemas.py`: Pydantic 数据模型定义
- `serving_parsers.py`: AT 响应解析器
- `deps.py`: 依赖注入（认证中间件）

### `docs/` - 文档目录
- API 参考文档、前端对接指南、测试结果等

## 2. API 路由概览

### 健康检查
- `GET /v1/health` - 服务健康状态、运行时间
- `GET /v1/version` - API 版本、配置信息

### 信息查询（需认证）
- `GET /v1/info` - 模组信息（厂商、型号、固件版本、IMEI、SIM卡信息）
- `GET /v1/live` - 实时信息（注册状态、信号质量、小区信息、CA信息、温度等）

### 控制接口（部分需危险权限）
- `POST /v1/ctrl/reboot` - 模组重启（危险）
- `POST /v1/ctrl/usbnet` - USB 网络模式切换（危险）
- `POST /v1/ctrl/apn` - APN 配置（危险）
- `GET /v1/ctrl/roaming` - 查询数据漫游状态（安全）
- `POST /v1/ctrl/roaming` - 设置数据漫游（安全）
- `POST /v1/ctrl/band` - 频段锁定（危险）
- `POST /v1/ctrl/cell_lock` - 小区锁定（危险）
- `POST /v1/ctrl/ca` - 载波聚合开关（安全）
- `POST /v1/ctrl/gnss` - GNSS 控制（安全）
- `GET /v1/ctrl/network_mode` - 查询网络模式（安全）
- `POST /v1/ctrl/network_mode` - 设置网络模式（安全）
- `GET /v1/ctrl/band_preference` - 查询频段偏好（安全）
- `POST /v1/ctrl/band_preference` - 设置频段偏好（安全）
- `POST /v1/ctrl/reset_profile` - 一键恢复默认配置（危险）

## 3. 核心功能

### 串口自动重连机制
- 自动检测 USB 串口设备（通过 `/sys/class/tty/` 和 USB 接口路径）
- 设备断开时自动重连，支持热插拔
- 使用线程锁保证 AT 指令串行执行
- 超时保护（默认 1.2 秒）

### AT 指令执行机制
- 单例模式管理串口连接
- 互斥锁保证线程安全
- 自动识别 OK/ERROR 响应
- 返回原始回显行列表供解析器处理

### 配置字段（.env）
- `SERIAL_PORT`: 串口路径（默认 `/dev/ttyUSB2`）
- `BAUDRATE`: 波特率（默认 115200）
- `API_PREFIX`: API 前缀（默认 `/v1`）
- `AUTH_TOKEN`: 认证令牌
- `AUTH_REQUIRED`: 是否启用认证（0/1）
- `LINKSTATION_CTRL_ENABLE`: 控制接口总开关
- `LINKSTATION_CTRL_ALLOW_DANGEROUS`: 是否允许危险操作
- `POLL_INTERVAL`: 轮询间隔
- `CORS_ORIGINS`: CORS 允许来源

## 4. 已完成功能

### 信息查询
- ✅ 模组基本信息（厂商、型号、固件、IMEI）
- ✅ SIM 卡信息（IMSI、ICCID、MSISDN）
- ✅ 实时网络状态（注册状态、信号质量、小区信息）
- ✅ 载波聚合信息（PCC、SCC 详细信息）
- ✅ 温度监控

### 控制功能
- ✅ 网络模式选择（AUTO/WCDMA/LTE/NR5G）
- ✅ 频段偏好设置（LTE/5G NSA/5G SA）
- ✅ 频段锁定
- ✅ 载波聚合开关
- ✅ 数据漫游控制
- ✅ APN 配置
- ✅ GNSS 控制
- ✅ 一键恢复默认配置

### 安全机制
- ✅ 危险操作保护（dry_run 模式）
- ✅ 认证中间件（可选）
- ✅ 配置开关控制

## 5. 未完成/待优化

### 代码注释中的待办
- `schemas.py`: `raw` 字段未来将包含 AT 回显（当前部分实现）

### 功能增强空间
- 健康检查可接入串口状态自检（`health.py` 注释中提到）
- 更多 AT 命令解析器（当前已覆盖主要功能）
- 错误重试机制可进一步优化

### 文档
- ✅ API 参考文档已完善
- ✅ 前端对接文档已提供
- ⚠️ 部分新 API 需要应用重启后才能使用

