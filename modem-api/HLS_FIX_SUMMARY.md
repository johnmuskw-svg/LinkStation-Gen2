# HLS 播放链路修复总结

## 修复内容

### 1. ✅ 修复 `live-hls` 接口
- **文件**: `routes/nvr.py`
- **问题**: 
  - 缺少 `profile` 查询参数支持
  - 将相对路径补全为完整URL，导致App直接访问NVR
- **修复**:
  - 添加 `profile` 查询参数支持（`sub`/`main`）
  - 保持相对路径返回，不补全为完整URL
  - 添加参数验证

### 2. ✅ 更新 `nvr_client.py`
- **文件**: `nvr_client.py`
- **修复**: `live_hls` 方法支持 `profile` 参数传递

### 3. ✅ 添加 HLS 静态文件代理路由
- **文件**: `routes/hls.py` (新建)
- **功能**: 
  - `/live/{ip}/{profile}/index.m3u8` - 播放列表代理
  - `/live/{ip}/{profile}/{filename:path}` - 切片文件代理
- **特性**:
  - 转发请求到NVR
  - 保持原始Content-Type
  - 添加适当的缓存头

### 4. ✅ 更新 `app.py`
- **文件**: `app.py`
- **修复**: 注册 HLS 路由（无前缀，直接 `/live/*`）

## 当前问题

### ⚠️ 服务需要重启
当前运行的服务还在使用旧代码，需要重启才能生效：

```bash
# 如果使用 systemd
sudo systemctl restart modem-api.service

# 或者手动重启 uvicorn 进程
pkill -f "uvicorn app:app"
cd /opt/linkstation/modem-api
source .venv/bin/activate
nohup uvicorn app:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
```

### ⚠️ 测试发现的问题
1. **playlist 返回完整URL**: 服务还在使用旧代码，重启后会返回相对路径
2. **profile 参数未生效**: 服务还在使用旧代码，重启后会正确传递
3. **播放列表代理404**: 服务还在使用旧代码，重启后会正常工作

## 修复后的预期行为

### API 端点
```
GET /v1/nvr/cameras/{ip}/live-hls?profile=main
```

**返回示例**:
```json
{
  "ok": true,
  "ts": 1766059279663,
  "camera": {...},
  "hls": {
    "playlist": "/live/192.168.11.103/main/index.m3u8",
    "profile": "main",
    "segment_seconds": 1,
    "window_seconds": 6
  }
}
```

### 静态文件代理
```
GET /live/192.168.11.103/main/index.m3u8
GET /live/192.168.11.103/main/seg_00991.ts
```

## 完整播放链路

1. **App 请求播放地址**:
   ```
   GET http://modem-api:8000/v1/nvr/cameras/192.168.11.103/live-hls?profile=main
   ```
   返回: `{"hls": {"playlist": "/live/192.168.11.103/main/index.m3u8"}}`

2. **App 请求播放列表**:
   ```
   GET http://modem-api:8000/live/192.168.11.103/main/index.m3u8
   ```
   modem-api 代理到: `http://192.168.99.11:8787/live/192.168.11.103/main/index.m3u8`

3. **App 请求切片文件**:
   ```
   GET http://modem-api:8000/live/192.168.11.103/main/seg_00991.ts
   ```
   modem-api 代理到: `http://192.168.99.11:8787/live/192.168.11.103/main/seg_00991.ts`

## 测试脚本

使用 `test_hls_chain.sh` 测试完整链路：

```bash
cd /opt/linkstation/modem-api
./test_hls_chain.sh
```

## 注意事项

1. **相对路径**: App 需要使用相对路径访问播放列表，通过 modem-api 代理
2. **profile 参数**: 支持 `sub`（子码流）和 `main`（主码流）
3. **错误处理**: 如果 NVR 不可用，返回 502 Bad Gateway
4. **缓存策略**: 播放列表不缓存，切片文件缓存1小时

