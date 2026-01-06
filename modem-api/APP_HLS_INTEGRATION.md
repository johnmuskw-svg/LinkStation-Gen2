# App 端 HLS 实时播放对接说明

## 概述

App 通过 modem-api（二代主机）访问 NVR 的实时监控画面，使用 HLS 协议进行流媒体播放。

**架构**: `App` → `modem-api (192.168.99.1:8000)` → `NVR (192.168.99.11:8787)`

---

## 1. 获取播放地址

### API 端点
```
GET http://modem-api地址:8000/v1/nvr/cameras/{摄像头IP}/live-hls?profile={流类型}
```

### 请求参数
- `摄像头IP` (路径参数): 例如 `192.168.11.103`
- `profile` (查询参数，可选):
  - `sub` (默认): 子码流，低延迟，用于预览
  - `main`: 主码流，高画质

### 请求示例
```bash
# 获取子码流（默认）
GET http://192.168.99.1:8000/v1/nvr/cameras/192.168.11.103/live-hls

# 获取主码流
GET http://192.168.99.1:8000/v1/nvr/cameras/192.168.11.103/live-hls?profile=main
```

### 响应示例
```json
{
  "ok": true,
  "ts": 1703001234567,
  "camera": {
    "ip": "192.168.11.103",
    "online": true,
    ...
  },
  "hls": {
    "playlist": "/live/192.168.11.103/main/index.m3u8",
    "profile": "main",
    "segment_seconds": 1,
    "window_seconds": 6
  },
  "error": null
}
```

---

## 2. 播放 HLS 流

### 关键字段
- `hls.playlist`: 播放列表的相对路径，例如 `/live/192.168.11.103/main/index.m3u8`

### URL 拼接规则

**重要**: `playlist` 字段返回的是**相对路径**，App 需要拼接 modem-api 的完整地址。

**拼接公式**:
```
完整播放列表URL = http://modem-api地址:8000 + hls.playlist
```

**示例**:
```javascript
// API 返回
{
  "hls": {
    "playlist": "/live/192.168.11.103/main/index.m3u8"
  }
}

// App 拼接后的完整URL
const modemApiBase = "http://192.168.99.1:8000";
const playlistUrl = modemApiBase + "/live/192.168.11.103/main/index.m3u8";
// 结果: http://192.168.99.1:8000/live/192.168.11.103/main/index.m3u8
```

---

## 3. 完整播放流程

### 步骤 1: 获取播放地址
```javascript
// 请求
GET http://192.168.99.1:8000/v1/nvr/cameras/192.168.11.103/live-hls?profile=main

// 响应
{
  "hls": {
    "playlist": "/live/192.168.11.103/main/index.m3u8"
  }
}
```

### 步骤 2: 拼接完整URL并播放
```javascript
const playlistUrl = "http://192.168.99.1:8000" + response.hls.playlist;
// 结果: http://192.168.99.1:8000/live/192.168.11.103/main/index.m3u8

// 使用 HLS 播放器播放
player.loadSource(playlistUrl);
```

### 步骤 3: 播放器自动处理
- 播放器会自动请求播放列表 (`index.m3u8`)
- 播放器会自动请求切片文件 (`seg_*.ts`)
- modem-api 会自动代理所有请求到 NVR

---

## 4. 注意事项

### ✅ 正确做法
1. **使用相对路径拼接**: `modem-api地址 + playlist相对路径`
2. **保持 profile 参数**: 根据需求选择 `sub` 或 `main`
3. **错误处理**: 检查 `ok` 字段和 `error` 字段
4. **网络异常处理**: 处理 502/503 等错误码

### ❌ 错误做法
1. **不要直接使用 NVR 地址**: 不要将 `playlist` 路径直接拼接到 NVR 地址
2. **不要忽略相对路径**: `playlist` 字段是相对路径，必须以 `/` 开头
3. **不要缓存播放列表URL**: 播放列表会持续更新，但 URL 格式不变

---

## 5. 错误处理

### 常见错误码
- `200`: 成功
- `400`: 参数错误（如 profile 不是 sub/main）
- `502`: NVR 服务不可用或网络错误
- `503`: NVR 集成已禁用

### 错误响应示例
```json
{
  "ok": false,
  "error": "NVR live-hls failed: Connection timeout",
  ...
}
```

---

## 6. 代码示例

### JavaScript/TypeScript
```typescript
async function getHlsPlaylist(cameraIp: string, profile: 'sub' | 'main' = 'sub') {
  const modemApiBase = 'http://192.168.99.1:8000';
  const url = `${modemApiBase}/v1/nvr/cameras/${cameraIp}/live-hls?profile=${profile}`;
  
  const response = await fetch(url);
  const data = await response.json();
  
  if (!data.ok) {
    throw new Error(data.error || 'Failed to get HLS playlist');
  }
  
  // 拼接完整播放列表URL
  const playlistUrl = `${modemApiBase}${data.hls.playlist}`;
  
  return {
    playlistUrl,
    profile: data.hls.profile,
    segmentSeconds: data.hls.segment_seconds,
    windowSeconds: data.hls.window_seconds
  };
}

// 使用示例
const { playlistUrl } = await getHlsPlaylist('192.168.11.103', 'main');
// playlistUrl = "http://192.168.99.1:8000/live/192.168.11.103/main/index.m3u8"

// 使用 HLS.js 或其他播放器播放
player.loadSource(playlistUrl);
```

### Swift (iOS)
```swift
func getHlsPlaylist(cameraIp: String, profile: String = "sub") async throws -> String {
    let modemApiBase = "http://192.168.99.1:8000"
    let url = URL(string: "\(modemApiBase)/v1/nvr/cameras/\(cameraIp)/live-hls?profile=\(profile)")!
    
    let (data, _) = try await URLSession.shared.data(from: url)
    let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]
    
    guard let ok = json["ok"] as? Bool, ok else {
        throw NSError(domain: "HLS", code: -1, userInfo: [NSLocalizedDescriptionKey: "API error"])
    }
    
    let hls = json["hls"] as! [String: Any]
    let playlist = hls["playlist"] as! String
    
    // 拼接完整URL
    return "\(modemApiBase)\(playlist)"
}

// 使用示例
let playlistUrl = try await getHlsPlaylist(cameraIp: "192.168.11.103", profile: "main")
// 使用 AVPlayer 播放
let player = AVPlayer(url: URL(string: playlistUrl)!)
```

### Kotlin (Android)
```kotlin
suspend fun getHlsPlaylist(cameraIp: String, profile: String = "sub"): String {
    val modemApiBase = "http://192.168.99.1:8000"
    val url = "$modemApiBase/v1/nvr/cameras/$cameraIp/live-hls?profile=$profile"
    
    val response = httpClient.get(url).body<JsonObject>()
    
    if (!response["ok"].asBoolean) {
        throw Exception("API error: ${response["error"]}")
    }
    
    val playlist = response["hls"]["playlist"].asString
    
    // 拼接完整URL
    return "$modemApiBase$playlist"
}

// 使用示例
val playlistUrl = getHlsPlaylist("192.168.11.103", "main")
// 使用 ExoPlayer 播放
exoPlayer.setMediaItem(MediaItem.fromUri(playlistUrl))
```

---

## 7. 测试检查清单

- [ ] API 请求返回 `ok: true`
- [ ] `playlist` 字段是相对路径（以 `/live/` 开头）
- [ ] 正确拼接了 modem-api 地址和相对路径
- [ ] 播放列表URL可以正常访问（返回 M3U8 格式）
- [ ] 播放器可以正常加载和播放
- [ ] 网络错误时正确处理（502/503）

---

## 8. 技术支持

如有问题，请检查：
1. modem-api 服务是否正常运行
2. 网络连接是否正常
3. 摄像头IP是否正确
4. URL拼接是否正确（相对路径 + modem-api地址）

