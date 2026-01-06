# App 连接问题排查与修复

## 问题现象
- App 无法连接到主机
- 提示重新设置密码
- 设置密码不成功

## 问题原因

### 1. ✅ 服务启动失败（已修复）
**问题**: 重启后服务无法启动，报错 `NameError: name 'hls_router' is not defined`

**原因**: `app.py` 中使用了 `hls_router` 但没有导入

**修复**: 已在 `app.py` 中添加导入：
```python
from routes.hls import router as hls_router
```

### 2. ✅ 服务状态（已正常）
- 服务状态: `active (running)`
- 端口监听: `0.0.0.0:8000` ✅
- 健康检查: 正常 ✅

### 3. ✅ 认证配置（正常）
- 配置文件: `/opt/linkstation/modem-api/config/base_auth.json`
- 当前配置: `{"enabled": true, "password": "12345678"}`
- 文件权限: `root:root` (644)
- 接口测试: 正常 ✅

## 当前状态

### 服务信息
- **服务名称**: `modem-api.service`
- **状态**: `active (running)`
- **监听地址**: `0.0.0.0:8000`
- **主机IP**: `192.168.99.1` (eth0)

### 认证接口
- **检查密码**: `POST /v1/base/auth/check`
- **设置密码**: `POST /v1/base/auth/set`
- **当前密码**: `12345678`
- **认证状态**: 已启用

## 测试结果

### 1. 健康检查
```bash
curl http://127.0.0.1:8000/v1/health
# ✅ 正常返回
```

### 2. 认证检查
```bash
curl -X POST http://127.0.0.1:8000/v1/base/auth/check \
  -H "Content-Type: application/json" \
  -d '{"password":"12345678"}'
# ✅ 返回: {"ok": true, "matched": true}
```

### 3. 设置密码
```bash
curl -X POST http://127.0.0.1:8000/v1/base/auth/set \
  -H "Content-Type: application/json" \
  -d '{"enabled":true,"password":"12345678"}'
# ✅ 返回: {"ok": true, "detail": {"enabled": true}}
```

## 可能的问题

### 1. App 端连接地址错误
**检查**: App 是否使用正确的地址
- 正确地址: `http://192.168.99.1:8000`
- 或使用: `http://192.168.99.1:8000/v1/base/auth/check`

### 2. 网络连接问题
**检查**: App 是否能访问主机
```bash
# 从 App 端测试
ping 192.168.99.1
curl http://192.168.99.1:8000/v1/health
```

### 3. 文件权限问题（已修复）
**问题**: 配置文件是 `root:root`，但服务以 `root` 运行，应该没问题
**状态**: ✅ 正常

### 4. 服务重启后配置丢失
**检查**: 配置文件在重启后是否还在
```bash
cat /opt/linkstation/modem-api/config/base_auth.json
# ✅ 文件存在，内容正确
```

## 修复步骤

### 1. 确认服务运行
```bash
sudo systemctl status modem-api.service
# 应该显示: Active: active (running)
```

### 2. 测试接口
```bash
# 健康检查
curl http://192.168.99.1:8000/v1/health

# 认证检查
curl -X POST http://192.168.99.1:8000/v1/base/auth/check \
  -H "Content-Type: application/json" \
  -d '{"password":"12345678"}'
```

### 3. 如果设置密码失败
```bash
# 检查文件权限
ls -la /opt/linkstation/modem-api/config/base_auth.json

# 手动设置（如果需要）
sudo chmod 644 /opt/linkstation/modem-api/config/base_auth.json
sudo chown root:root /opt/linkstation/modem-api/config/base_auth.json

# 重启服务
sudo systemctl restart modem-api.service
```

## App 端对接说明

### 认证接口
1. **检查密码**:
   ```
   POST http://192.168.99.1:8000/v1/base/auth/check
   Body: {"password": "12345678"}
   ```

2. **设置密码**:
   ```
   POST http://192.168.99.1:8000/v1/base/auth/set
   Body: {"enabled": true, "password": "新密码"}
   ```

### 连接流程
1. App 连接主机: `http://192.168.99.1:8000`
2. 检查认证状态: `POST /v1/base/auth/check`
3. 如果需要设置密码: `POST /v1/base/auth/set`
4. 使用密码访问其他接口

## 下一步排查

如果 App 仍然无法连接，请检查：

1. **网络连接**:
   ```bash
   # 从 App 端
   ping 192.168.99.1
   curl http://192.168.99.1:8000/v1/health
   ```

2. **防火墙规则**:
   ```bash
   # 检查防火墙
   sudo iptables -L -n | grep 8000
   sudo nft list ruleset | grep 8000
   ```

3. **服务日志**:
   ```bash
   sudo journalctl -u modem-api.service -f
   ```

4. **App 端错误信息**:
   - 记录具体的错误码和错误信息
   - 检查网络请求日志

## 总结

✅ **已修复**:
- 服务启动失败问题（添加了 hls_router 导入）
- 服务现在正常运行

✅ **正常状态**:
- 服务运行正常
- 认证配置正常
- 接口测试通过

⚠️ **需要 App 端检查**:
- 连接地址是否正确
- 网络是否可达
- 请求格式是否正确


