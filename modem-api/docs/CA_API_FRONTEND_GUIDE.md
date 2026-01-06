# 载波聚合（CA）API 前端对接指南

本文档说明如何在手机App中对接载波聚合相关的API，包括开关控制和状态查询功能。

## 目录

1. [API概览](#api概览)
2. [载波聚合开关控制](#载波聚合开关控制)
3. [载波聚合状态查询](#载波聚合状态查询)
4. [请求/响应格式](#请求响应格式)
5. [错误处理](#错误处理)
6. [完整示例](#完整示例)

---

## API概览

### 基础URL
```
http://192.168.1.254:8000/v1
```

### 相关接口

| 接口 | 方法 | 用途 | 危险级别 |
|------|------|------|----------|
| `/ctrl/ca` | POST | 设置载波聚合开关 | 危险（需配置） |
| `/live` | GET | 查询载波聚合状态 | 安全 |

---

## 载波聚合开关控制

### 接口：`POST /v1/ctrl/ca`

用于启用或禁用载波聚合功能。可以分别控制LTE和5G的载波聚合。

#### 请求格式

**URL**: `POST http://192.168.1.254:8000/v1/ctrl/ca`

**Headers**:
```
Content-Type: application/json
```

**请求体** (`CtrlCaRequest`):
```json
{
  "dry_run": false,
  "lte_ca_enable": true,    // 可选，LTE载波聚合开关
  "nr_ca_enable": true      // 可选，5G载波聚合开关
}
```

**字段说明**:
- `dry_run` (boolean, 可选): 
  - `true`: 仅模拟执行，不真正执行AT命令（用于测试）
  - `false`: 真正执行AT命令（需要配置 `LINKSTATION_CTRL_ALLOW_DANGEROUS=1`）
  
- `lte_ca_enable` (boolean, 可选):
  - `true`: 启用LTE载波聚合
  - `false`: 禁用LTE载波聚合
  - `null` 或省略: 不修改LTE设置
  
- `nr_ca_enable` (boolean, 可选):
  - `true`: 启用5G载波聚合
  - `false`: 禁用5G载波聚合
  - `null` 或省略: 不修改5G设置

**注意**: 
- 如果同时指定了 `lte_ca_enable` 和 `nr_ca_enable`，会分别设置LTE和5G的CA
- 如果只指定其中一个，会使用全局CA配置
- 如果两个都不指定，默认启用全局CA

#### 响应格式

**成功响应** (`CtrlBaseResponse`):
```json
{
  "ok": true,
  "ts": 1732004455000,
  "error": null,
  "action": {
    "name": "ca",
    "dry_run": false,
    "commands": [
      "AT+QCFG=\"lte/ca\",1",
      "AT+QCFG=\"nr5g/ca\",1"
    ],
    "raw": [
      "AT+QCFG=\"lte/ca\",1",
      "OK",
      "AT+QCFG=\"nr5g/ca\",1",
      "OK"
    ]
  }
}
```

**字段说明**:
- `ok` (boolean): 请求是否成功
- `ts` (number): 毫秒级时间戳
- `error` (string|null): 错误信息，成功时为 `null`
- `action.name` (string): 操作名称，固定为 `"ca"`
- `action.dry_run` (boolean): 是否为模拟执行
- `action.commands` (array): 计划执行的AT命令列表
- `action.raw` (array): 实际执行的AT命令和响应

**错误响应**:
```json
{
  "ok": false,
  "ts": 1732004455000,
  "error": "CTRL功能未启用或不允许执行危险操作",
  "action": null
}
```

#### 请求示例

**示例1: 启用LTE和5G载波聚合**
```bash
curl -X POST http://192.168.1.254:8000/v1/ctrl/ca \
  -H "Content-Type: application/json" \
  -d '{
    "dry_run": false,
    "lte_ca_enable": true,
    "nr_ca_enable": true
  }'
```

**示例2: 仅禁用LTE载波聚合**
```bash
curl -X POST http://192.168.1.254:8000/v1/ctrl/ca \
  -H "Content-Type: application/json" \
  -d '{
    "dry_run": false,
    "lte_ca_enable": false
  }'
```

**示例3: 仅启用5G载波聚合**
```bash
curl -X POST http://192.168.1.254:8000/v1/ctrl/ca \
  -H "Content-Type: application/json" \
  -d '{
    "dry_run": false,
    "nr_ca_enable": true
  }'
```

---

## 载波聚合状态查询

### 接口：`GET /v1/live`

查询当前载波聚合状态，包括PCC（主载波）和SCC（辅载波）信息。

#### 请求格式

**URL**: `GET http://192.168.1.254:8000/v1/live?verbose=false`

**查询参数**:
- `verbose` (boolean, 可选): 是否返回原始AT回显，默认 `false`

#### 响应格式

**成功响应** (`LiveResponse`):
```json
{
  "ok": true,
  "ts": 1732004455000,
  "error": null,
  "ca": {
    "pcc": {
      "rat": "LTE",
      "arfcn": 300,
      "dl_bw_mhz": 20,
      "band": "LTE BAND 1",
      "rsrp": -66,
      "rsrq": -12,
      "sinr": 30
    },
    "scc": [
      {
        "idx": 1,
        "rat": "LTE",
        "arfcn": 1575,
        "dl_bw_mhz": 20,
        "band": "LTE BAND 3",
        "rsrp": -64,
        "rsrq": -7,
        "sinr": 30
      }
    ],
    "summary": "LTE CA: 2CC (B1+B3)"
  }
}
```

**字段说明**:

**`ca` 对象**:
- `pcc` (object|null): 主载波（Primary Component Carrier）信息
  - `rat` (string|null): 制式类型，如 "LTE" 或 "NR"
  - `arfcn` (number|null): 载波频率（EARFCN/NRARFCN）
  - `dl_bw_mhz` (number|null): 下行带宽（MHz）
  - `band` (string|null): 频段信息，如 "LTE BAND 1"
  - `rsrp` (number|null): 参考信号接收功率（dBm）
  - `rsrq` (number|null): 参考信号接收质量（dB）
  - `sinr` (number|null): 信噪比（dB）

- `scc` (array): 辅载波（Secondary Component Carrier）列表
  - 每个元素结构与 `pcc` 相同
  - `idx` (number): 辅载波索引（从1开始）

- `summary` (string|null): 载波聚合摘要信息，如 "LTE CA: 2CC (B1+B3)"

**注意**: 
- 如果当前没有启用载波聚合，`scc` 数组为空
- 如果模组未注册网络，`pcc` 可能为 `null`
- 某些字段可能为 `null`，取决于模组返回的数据

#### 请求示例

**示例1: 查询载波聚合状态**
```bash
curl http://192.168.1.254:8000/v1/live | jq '.ca'
```

**示例2: 查询并显示原始AT回显**
```bash
curl "http://192.168.1.254:8000/v1/live?verbose=true" | jq '.raw."AT+QCAINFO"'
```

---

## 请求/响应格式

### 完整的请求流程

1. **设置载波聚合开关**
   ```javascript
   // JavaScript示例
   const response = await fetch('http://192.168.1.254:8000/v1/ctrl/ca', {
     method: 'POST',
     headers: {
       'Content-Type': 'application/json',
     },
     body: JSON.stringify({
       dry_run: false,
       lte_ca_enable: true,
       nr_ca_enable: true
     })
   });
   
   const result = await response.json();
   if (result.ok) {
     console.log('载波聚合设置成功');
   } else {
     console.error('设置失败:', result.error);
   }
   ```

2. **查询载波聚合状态**
   ```javascript
   // JavaScript示例
   const response = await fetch('http://192.168.1.254:8000/v1/live');
   const data = await response.json();
   
   if (data.ok && data.ca) {
     const { pcc, scc, summary } = data.ca;
     console.log('主载波:', pcc);
     console.log('辅载波数量:', scc.length);
     console.log('摘要:', summary);
   }
   ```

---

## 错误处理

### 常见错误

1. **CTRL功能未启用**
   ```json
   {
     "ok": false,
     "error": "CTRL功能未启用或不允许执行危险操作"
   }
   ```
   **解决方案**: 确保后端配置了 `LINKSTATION_CTRL_ALLOW_DANGEROUS=1`

2. **dry_run模式**
   ```json
   {
     "ok": true,
     "action": {
       "dry_run": true,
       "commands": [...]
     }
   }
   ```
   **说明**: 如果 `dry_run=true`，命令不会真正执行，仅用于测试

3. **网络错误**
   - 检查设备IP地址是否正确
   - 检查设备是否在线
   - 检查防火墙设置

### 错误处理示例

```javascript
async function setCarrierAggregation(lteEnable, nrEnable) {
  try {
    const response = await fetch('http://192.168.1.254:8000/v1/ctrl/ca', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dry_run: false,
        lte_ca_enable: lteEnable,
        nr_ca_enable: nrEnable
      })
    });
    
    const result = await response.json();
    
    if (!result.ok) {
      throw new Error(result.error || '未知错误');
    }
    
    if (result.action?.dry_run) {
      console.warn('警告: 当前为模拟模式，未真正执行');
    }
    
    return result;
  } catch (error) {
    console.error('设置载波聚合失败:', error);
    throw error;
  }
}
```

---

## 完整示例

### React Native / JavaScript 完整示例

```javascript
class CarrierAggregationAPI {
  constructor(baseURL = 'http://192.168.1.254:8000/v1') {
    this.baseURL = baseURL;
  }
  
  /**
   * 设置载波聚合开关
   * @param {Object} options - 配置选项
   * @param {boolean} options.lteEnable - LTE载波聚合开关
   * @param {boolean} options.nrEnable - 5G载波聚合开关
   * @param {boolean} options.dryRun - 是否仅模拟执行
   * @returns {Promise<Object>} API响应
   */
  async setCA({ lteEnable, nrEnable, dryRun = false }) {
    const response = await fetch(`${this.baseURL}/ctrl/ca`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dry_run: dryRun,
        lte_ca_enable: lteEnable,
        nr_ca_enable: nrEnable
      })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP错误: ${response.status}`);
    }
    
    const result = await response.json();
    if (!result.ok) {
      throw new Error(result.error || '设置失败');
    }
    
    return result;
  }
  
  /**
   * 查询载波聚合状态
   * @param {boolean} verbose - 是否返回原始AT回显
   * @returns {Promise<Object>} 载波聚合状态
   */
  async getCAStatus(verbose = false) {
    const response = await fetch(
      `${this.baseURL}/live?verbose=${verbose}`
    );
    
    if (!response.ok) {
      throw new Error(`HTTP错误: ${response.status}`);
    }
    
    const data = await response.json();
    if (!data.ok) {
      throw new Error(data.error || '查询失败');
    }
    
    return data.ca;
  }
  
  /**
   * 启用载波聚合并等待生效
   * @param {Object} options - 配置选项
   * @returns {Promise<Object>} 最终状态
   */
  async enableCAAndWait(options = {}) {
    // 1. 设置载波聚合
    await this.setCA({ ...options, dryRun: false });
    
    // 2. 等待生效（建议等待5-10秒）
    await new Promise(resolve => setTimeout(resolve, 5000));
    
    // 3. 查询状态确认
    const status = await this.getCAStatus();
    
    return status;
  }
}

// 使用示例
const caAPI = new CarrierAggregationAPI();

// 启用LTE和5G载波聚合
caAPI.setCA({
  lteEnable: true,
  nrEnable: true,
  dryRun: false
}).then(result => {
  console.log('设置成功:', result);
  
  // 查询状态
  return caAPI.getCAStatus();
}).then(status => {
  console.log('当前状态:', status);
  console.log('主载波:', status.pcc);
  console.log('辅载波数量:', status.scc.length);
}).catch(error => {
  console.error('操作失败:', error);
});
```

### 状态显示示例

```javascript
function displayCAStatus(ca) {
  if (!ca || !ca.pcc) {
    return '未检测到载波聚合';
  }
  
  const { pcc, scc } = ca;
  let status = `主载波: ${pcc.band || '未知'}`;
  
  if (pcc.arfcn) {
    status += ` (ARFCN: ${pcc.arfcn})`;
  }
  
  if (pcc.rsrp !== null) {
    status += ` | RSRP: ${pcc.rsrp} dBm`;
  }
  
  if (scc.length > 0) {
    status += `\n辅载波: ${scc.length}个`;
    scc.forEach((carrier, index) => {
      status += `\n  ${index + 1}. ${carrier.band || '未知'}`;
      if (carrier.arfcn) {
        status += ` (ARFCN: ${carrier.arfcn})`;
      }
    });
  } else {
    status += '\n辅载波: 无（未启用载波聚合）';
  }
  
  return status;
}

// 使用
caAPI.getCAStatus().then(status => {
  console.log(displayCAStatus(status));
});
```

---

## 注意事项

1. **权限要求**: 
   - 设置载波聚合需要后端配置 `LINKSTATION_CTRL_ALLOW_DANGEROUS=1`
   - 查询状态无需特殊权限

2. **生效时间**:
   - 设置后建议等待5-10秒再查询状态
   - 某些设置可能需要模组重新注册网络才能生效

3. **网络要求**:
   - 查询状态需要模组已注册网络
   - 未注册时 `pcc` 可能为 `null`

4. **错误处理**:
   - 始终检查 `ok` 字段
   - 处理网络超时情况
   - 提供用户友好的错误提示

5. **性能考虑**:
   - `/live` 接口会查询多个AT命令，响应时间可能较长
   - 建议使用轮询间隔不少于3秒

---

## 相关AT命令参考

底层使用的AT命令：

- **查询状态**: `AT+QCAINFO`
- **设置LTE CA**: `AT+QCFG="lte/ca",<0|1>`
- **设置5G CA**: `AT+QCFG="nr5g/ca",<0|1>`
- **查询LTE CA**: `AT+QCFG="lte/ca"`
- **查询5G CA**: `AT+QCFG="nr5g/ca"`

更多详细信息请参考 `ctrl_commands_summary.json` 文件。

---

## 更新日志

- **2024-12**: 初始版本，支持LTE和5G载波聚合的开关控制和状态查询

