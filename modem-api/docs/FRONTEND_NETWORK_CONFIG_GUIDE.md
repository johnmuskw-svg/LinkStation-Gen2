# 网络模式配置 API 前端对接文档

本文档说明如何在手机 app 中使用网络模式选择、频段偏好设置和载波聚合控制等 API。

## 基础信息

- **Base URL**: `http://<设备IP>:<端口>/ctrl`
- **所有 API 均为安全设置命令**，可以直接执行，无需特殊权限
- **支持 dry_run 模式**：设置 `dry_run: true` 可以预览将要执行的命令，不会真正执行

---

## 1. 网络模式选择 API

### 1.1 查询当前网络模式

**接口**: `GET /ctrl/network_mode`

**请求示例**:
```bash
GET http://192.168.1.1:8080/ctrl/network_mode
```

**响应示例**:
```json
{
  "ok": true,
  "ts": 1704067200000,
  "error": null,
  "mode": {
    "mode_pref": "AUTO"
  },
  "raw": [
    "+QNWPREFCFG: \"mode_pref\",AUTO",
    "OK"
  ]
}
```

**mode_pref 可能的值**:
- `"AUTO"` - 自动选择（WCDMA & LTE & 5G）
- `"WCDMA"` - 仅 WCDMA
- `"LTE"` - 仅 LTE
- `"NR5G"` - 仅 5G
- `"LTE:NR5G"` - LTE 和 5G 组合
- `"WCDMA:LTE"` - WCDMA 和 LTE 组合

---

### 1.2 设置网络模式

**接口**: `POST /ctrl/network_mode`

**请求体**:
```json
{
  "mode_pref": "LTE:NR5G",
  "dry_run": false
}
```

**请求参数说明**:
- `mode_pref` (string, 可选): 网络搜索模式
  - 如果省略此字段，则仅查询当前模式
  - 可选值：`"AUTO"`, `"WCDMA"`, `"LTE"`, `"NR5G"`, `"LTE:NR5G"` 等
- `dry_run` (boolean, 默认 false): 是否仅预览不执行

**响应示例**:
```json
{
  "ok": true,
  "ts": 1704067200000,
  "error": null,
  "mode": {
    "mode_pref": "LTE:NR5G"
  },
  "raw": [
    "+QNWPREFCFG: \"mode_pref\",LTE:NR5G",
    "OK"
  ]
}
```

**前端使用示例** (JavaScript):
```javascript
// 设置网络模式为 LTE + 5G
async function setNetworkMode(mode) {
  const response = await fetch('http://192.168.1.1:8080/ctrl/network_mode', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      mode_pref: mode,  // 例如: "LTE:NR5G"
      dry_run: false
    })
  });
  
  const data = await response.json();
  if (data.ok) {
    console.log('当前网络模式:', data.mode.mode_pref);
    return data.mode.mode_pref;
  } else {
    console.error('设置失败:', data.error);
    throw new Error(data.error);
  }
}

// 查询当前网络模式
async function getNetworkMode() {
  const response = await fetch('http://192.168.1.1:8080/ctrl/network_mode');
  const data = await response.json();
  return data.mode.mode_pref;
}
```

---

## 2. 频段偏好设置 API

### 2.1 查询当前频段偏好

**接口**: `GET /ctrl/band_preference`

**请求示例**:
```bash
GET http://192.168.1.1:8080/ctrl/band_preference
```

**响应示例**:
```json
{
  "ok": true,
  "ts": 1704067200000,
  "error": null,
  "bands": {
    "lte_bands": [1, 3, 7, 8, 20, 28, 38, 40, 41],
    "nsa_nr5g_bands": [1, 3, 41, 78],
    "nr5g_bands": [1, 3, 41, 78]
  },
  "raw": [...]
}
```

**说明**:
- `lte_bands`: LTE 频段列表（整数数组，如 [1, 3, 7] 表示 B1, B3, B7）
- `nsa_nr5g_bands`: 5G NSA 频段列表（整数数组，如 [1, 41, 78] 表示 n1, n41, n78）
- `nr5g_bands`: 5G SA 频段列表（整数数组）

---

### 2.2 设置频段偏好

**接口**: `POST /ctrl/band_preference`

**请求体**:
```json
{
  "lte_bands": [1, 3, 7],
  "nsa_nr5g_bands": [1, 41, 78],
  "nr5g_bands": [1, 41, 78],
  "dry_run": false
}
```

**请求参数说明**:
- `lte_bands` (array of integers, 可选): LTE 频段列表
  - 设置为空数组 `[]` 或省略表示使用所有支持的频段
  - 例如: `[1, 3, 7]` 表示只使用 B1, B3, B7
- `nsa_nr5g_bands` (array of integers, 可选): 5G NSA 频段列表
- `nr5g_bands` (array of integers, 可选): 5G SA 频段列表
- `dry_run` (boolean, 默认 false): 是否仅预览不执行

**响应示例**:
```json
{
  "ok": true,
  "ts": 1704067200000,
  "error": null,
  "bands": {
    "lte_bands": [1, 3, 7],
    "nsa_nr5g_bands": [1, 41, 78],
    "nr5g_bands": [1, 41, 78]
  },
  "raw": [...]
}
```

**前端使用示例** (JavaScript):
```javascript
// 设置频段偏好
async function setBandPreference(lteBands, nsaBands, saBands) {
  const response = await fetch('http://192.168.1.1:8080/ctrl/band_preference', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      lte_bands: lteBands || null,        // 例如: [1, 3, 7]
      nsa_nr5g_bands: nsaBands || null,   // 例如: [1, 41, 78]
      nr5g_bands: saBands || null,        // 例如: [1, 41, 78]
      dry_run: false
    })
  });
  
  const data = await response.json();
  if (data.ok) {
    console.log('频段偏好设置成功');
    return data.bands;
  } else {
    console.error('设置失败:', data.error);
    throw new Error(data.error);
  }
}

// 查询当前频段偏好
async function getBandPreference() {
  const response = await fetch('http://192.168.1.1:8080/ctrl/band_preference');
  const data = await response.json();
  return data.bands;
}
```

**注意**: 
- 频段偏好设置是**非锁定**的，模组会优先搜索指定的频段，但如果这些频段不可用，仍会搜索其他频段
- 这与频段锁定（`/ctrl/band`）不同，频段锁定会强制只使用指定的频段

---

## 3. 载波聚合（CA）控制 API

### 3.1 设置载波聚合开关

**接口**: `POST /ctrl/ca`

**请求体**:
```json
{
  "lte_ca_enable": true,
  "nr_ca_enable": true,
  "dry_run": false
}
```

**请求参数说明**:
- `lte_ca_enable` (boolean, 可选): 是否启用 LTE 载波聚合
- `nr_ca_enable` (boolean, 可选): 是否启用 5G 载波聚合
- `dry_run` (boolean, 默认 false): 是否仅预览不执行

**响应示例**:
```json
{
  "ok": true,
  "ts": 1704067200000,
  "action": "ca",
  "error": null,
  "detail": {
    "dry_run": false,
    "dangerous": false,
    "executed": true,
    "blocked_reason": null,
    "planned": [
      "AT+QCFG=\"lte/ca\",1",
      "AT+QCFG=\"nr5g/ca\",1"
    ],
    "errors": []
  },
  "raw": {
    "AT+QCFG=\"lte/ca\",1": ["OK"],
    "AT+QCFG=\"nr5g/ca\",1": ["OK"]
  }
}
```

**前端使用示例** (JavaScript):
```javascript
// 设置载波聚合
async function setCarrierAggregation(lteEnable, nrEnable) {
  const response = await fetch('http://192.168.1.1:8080/ctrl/ca', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      lte_ca_enable: lteEnable,  // true/false
      nr_ca_enable: nrEnable,    // true/false
      dry_run: false
    })
  });
  
  const data = await response.json();
  if (data.ok && data.detail.executed) {
    console.log('载波聚合设置成功');
    return true;
  } else {
    console.error('设置失败:', data.error || data.detail.blocked_reason);
    return false;
  }
}
```

---

## 4. 完整使用示例

### 4.1 设置模组为 LTE + 5G 模式，并启用载波聚合

```javascript
async function configureModemForLTE5G() {
  try {
    // 1. 设置网络模式为 LTE + 5G
    await setNetworkMode('LTE:NR5G');
    console.log('网络模式已设置为 LTE:NR5G');
    
    // 2. 设置频段偏好（可选）
    await setBandPreference(
      [1, 3, 7, 20, 28],      // LTE 频段
      [1, 41, 78],            // 5G NSA 频段
      [1, 41, 78]             // 5G SA 频段
    );
    console.log('频段偏好已设置');
    
    // 3. 启用载波聚合
    await setCarrierAggregation(true, true);
    console.log('载波聚合已启用');
    
    return true;
  } catch (error) {
    console.error('配置失败:', error);
    return false;
  }
}
```

### 4.2 查询当前所有配置

```javascript
async function getCurrentConfig() {
  try {
    const [mode, bands] = await Promise.all([
      getNetworkMode(),
      getBandPreference()
    ]);
    
    return {
      networkMode: mode,
      bandPreference: bands
    };
  } catch (error) {
    console.error('查询失败:', error);
    return null;
  }
}
```

---

## 5. 错误处理

所有 API 在失败时都会返回 `ok: false` 和 `error` 字段：

```json
{
  "ok": false,
  "ts": 1704067200000,
  "error": "错误信息描述",
  ...
}
```

**常见错误**:
- 模组未连接或未响应
- 参数格式错误
- 模组不支持该功能

**前端错误处理示例**:
```javascript
async function safeApiCall(apiFunction) {
  try {
    const result = await apiFunction();
    if (!result.ok) {
      throw new Error(result.error || '未知错误');
    }
    return result;
  } catch (error) {
    console.error('API 调用失败:', error);
    // 显示错误提示给用户
    alert('操作失败: ' + error.message);
    throw error;
  }
}
```

---

## 6. 注意事项

1. **所有 API 都是安全设置命令**，可以直接执行，不会导致模组无法使用
2. **配置会保存到 NVM**，重启后仍然有效
3. **设置后可能需要几秒钟生效**，建议设置后等待 5-10 秒再查询状态
4. **频段偏好 vs 频段锁定**:
   - 频段偏好（`/ctrl/band_preference`）：模组会优先搜索指定频段，但其他频段仍可用
   - 频段锁定（`/ctrl/band`）：模组只能使用指定频段，可能导致无法注册网络
5. **dry_run 模式**：设置 `dry_run: true` 可以预览将要执行的命令，不会真正执行，适合测试

---

## 7. API 列表总结

| API | 方法 | 功能 | 是否安全 |
|-----|------|------|---------|
| `/ctrl/network_mode` | GET | 查询网络模式 | ✅ |
| `/ctrl/network_mode` | POST | 设置网络模式 | ✅ |
| `/ctrl/band_preference` | GET | 查询频段偏好 | ✅ |
| `/ctrl/band_preference` | POST | 设置频段偏好 | ✅ |
| `/ctrl/ca` | POST | 设置载波聚合 | ✅ |

所有 API 均为安全设置命令，可以直接使用。

