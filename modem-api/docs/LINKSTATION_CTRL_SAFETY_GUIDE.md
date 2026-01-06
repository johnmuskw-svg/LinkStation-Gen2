# LinkStation 控制接口与 AT 安全规范

## 1. 角色说明
- 面向对象：需要远程操控 5G 模组的 App / Web 控制台 / 自动化脚本开发者。
- 风险提示：所有 `/v1/ctrl/*` 接口都会直接生成 Quectel AT 命令并可能改变联网状态、频段或硬件模式；任何误操作都可能导致断网、不可逆重启或额外费用，务必仅在明确场景下调用。

## 2. 统一控制返回结构
控制 API 均返回 `CtrlBaseResponse`：
- `ok`：语义层是否成功（计划生成或执行过程中未抛出异常）
- `ts`：毫秒级时间戳
- `action`：动作名（`"roaming"` 等）
- `error`：异常文本（若 `ok=false`）
- `raw`：当真正执行 AT 时，记录 `{ "AT+XXX": [...] }`
- `detail`：`CtrlActionDetail`
  - `dry_run`：本次是否仅为演练
  - `dangerous`：动作是否在危险名单
  - `executed`：是否已发送且全部 AT 成功
  - `blocked_reason`：如 `CTRL_ENABLE=0`
  - `planned`：即将执行/已执行的 AT 列表
  - `errors`：逐条 AT 错误
  - `extra`：预留

### `/v1/ctrl/roaming` 实例

#### GET 请求示例
查询当前漫游状态：
```bash
curl -s http://192.168.1.254:8000/v1/ctrl/roaming | jq
```

典型响应：
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

#### POST 请求示例
设置漫游开关：
```bash
curl -X POST http://192.168.1.254:8000/v1/ctrl/roaming \
  -H 'Content-Type: application/json' \
  -d '{"enable": true, "dry_run": false}' | jq
```

在默认配置下（`CTRL_ENABLE=1` 且动作为安全动作），典型响应：
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

**注意**：`/v1/ctrl/roaming` 使用 `RoamingResponse` 响应模型（而非 `CtrlBaseResponse`），因此响应结构与其他控制接口略有不同，不包含 `action` 和 `detail` 字段，而是直接返回 `roaming.enabled` 状态。

若 `CTRL_ENABLE=0` 或请求使用 `dry_run=true`，不会真正执行 AT 命令，仅返回当前查询到的状态。

## 3. 安全总开关说明
| 开关 | 环境变量 | 默认值 | 影响 |
| --- | --- | --- | --- |
| `CTRL_ENABLE` | `LINKSTATION_CTRL_ENABLE` | `True` | 设为 `0` 时所有控制接口都被动变成 dry-run，仅返回计划，不会调用串口；`detail.blocked_reason="CTRL_ENABLE=0"` |
| `CTRL_ALLOW_DANGEROUS` | `LINKSTATION_CTRL_ALLOW_DANGEROUS` | `False` | 针对危险动作（`reboot`/`usbnet`/`apn`/`band`/`cell_lock`/`ca`/`reset_profile`）的执行许可。为 `0` 时即使客户端 `dry_run=false` 也只会得到计划，`blocked_reason="CTRL_ALLOW_DANGEROUS=0"` |

推荐配置：
- **生产环境**：`CTRL_ENABLE=1`，`CTRL_ALLOW_DANGEROUS=0`，仅允许通过 dry-run 查看计划或执行安全动作（`roaming`/`gnss`）。在需要执行危险动作时，由现场工程师临时设置为 `1`，完成后立即恢复。
- **测试/实验环境**：可在受控网络内设置 `CTRL_ALLOW_DANGEROUS=1`，但需结合 ACL/IP 白名单或 VPN 保护。

## 4. 控制接口语义 & 用法
以下摘要均源自 `routes/ctrl.py` 中的 `_plan_*` 函数。风险等级以 `【高风险】` / `【中风险】` / `【低风险】` 标注。

### `/v1/ctrl/reboot` 【高风险】
- **语义**：通过 `AT+CFUN` 软重启、全重启或关闭射频（`mode=soft/full/rf_off`）。
- **典型用法**：远程复位模组或临时关闭 RF（相当于飞行模式）。
- **影响**：所有数据会话会被强制断开，`mode=full` 会触发完全重启，可能需要 30 秒以上恢复。

### `/v1/ctrl/usbnet` 【高风险】
- **语义**：`AT+QCFG="usbnet",<mode>` 切换 RNDIS/ECM/NCM/MBIM，并可选 `reboot_modem=true` 追加 `AT+CFUN=1,1`。
- **典型用法**：在不同宿主系统之间切换 USB 网络协议。
- **风险**：切换后宿主 OS 需要重新枚举 USB，可能导致远程链路瞬断甚至失联。

### `/v1/ctrl/apn` 【高风险】
- **语义**：组合 `AT+CGDCONT`, `AT+CGAUTH`, `AT+CGACT` 配置/激活 PDP APN、认证方式、CID。
- **典型用法**：切换企业专用 APN、配置专线/物联网卡。
- **风险**：错误 APN/认证会导致完全掉线；需要了解运营商配置。

### `/v1/ctrl/roaming` 【中风险】（费用风险）
- **语义**：使用 `AT+QNWPREFCFG="roam_pref",<value>` 控制数据漫游偏好。
  - `GET /v1/ctrl/roaming`：查询当前漫游状态（`AT+QNWPREFCFG="roam_pref"`）
  - `POST /v1/ctrl/roaming`：设置漫游偏好
    - `enable=true` → `roam_pref=255`（允许漫游到任意网络）
    - `enable=false` → `roam_pref=1`（仅 home 网络，不允许漫游）
- **典型用法**：跨境或多运营商场景控制漫游。App 可在"常用控制"页面提供开关，进入页面时调用 GET 查询状态，切换开关时调用 POST 设置。
- **注意**：
  - 这是**安全动作**，不需要 `CTRL_ALLOW_DANGEROUS=1` 即可执行
  - 漫游可能产生额外费用，但不会立即断线（若仍在本地网络）
  - 设置成功后会自动重新查询状态以确认生效

### `/v1/ctrl/band` 【高风险】
- **语义**：`AT+QCFG="band",<RAT>,"B1,B3"` 等命令锁定 LTE/NR5G 频段；`reset=true` 时清空（`AT+QCFG="lte/band","0"` 等）。
- **典型用法**：现场干扰排查、定点驻留测试。
- **风险**：在覆盖较差区域可能导致完全搜不到网，恢复需人工解锁。

### `/v1/ctrl/cell_lock` 【高风险】
- **语义**：`AT+QNWLOCK=1,"LTE"` 等命令限制到特定 RAT/PCI/TAC；`enable=false` 时 `AT+QNWLOCK=0` 解锁。
- **典型用法**：实验室锁定单小区做性能测试。
- **风险**：错误的锁定参数会导致设备无法注册，且部分固件只有物理复位才能解锁。

### `/v1/ctrl/ca` 【高风险】
- **语义**：`AT+QCFG="lte/ca",<0|1>`、`AT+QCFG="nr5g/ca",<0|1>` 或全局 `AT+QCFG="ca",<0|1>` 控制载波聚合。
- **典型用法**：排查 CA 兼容性、降低功耗。
- **风险**：关闭 CA 可能降低吞吐或影响运营商策略；错误开启可能引发不稳定。

### `/v1/ctrl/gnss` 【中风险】
- **语义**：`AT+QCFG="gnss",<mode>,<enable>` 控制 GNSS；支持 `mode` 指定 `standalone/assisted` 等。
- **典型用法**：远程开启 GNSS 采集位置信息或关闭以节能。
- **风险**：开启 GNSS 会增加功耗；关闭可能影响依赖定位的应用。

### `/v1/ctrl/reset_profile` 【高风险】
- **语义**：为 profile `modem_safe` 生成固定计划：
  1. `AT+QCFG="lte/band","0"` / `AT+QCFG="nr5g/band","0"`
  2. `AT+QNWLOCK=0`
  3. 打开 `LTE/NR5G` CA
  4. `AT+QNWPREFCFG="roam_pref",255`（开启数据漫游）
  5. `AT+QCFG="usbnet",1`（RNDIS）
- **典型用法**：远程恢复标准配置。
- **风险**：相当于"清空"自定义频段/小区锁/USB 模式，可能破坏定制化设置；不会触及 APN/GNSS。

> 注：以上列表需与 routes/ctrl.py 中所有 `@router.post` 动作保持一致，若新增 action 请同步更新。

## 5. dry_run 的推荐使用方式
1. **先 dry-run**：所有前端/自动化脚本在执行危险或未知动作前，应发送 `{"dry_run": true}` 请求，读取 `detail.planned` 列表展示给用户（或记录日志）。
2. **用户确认**：UI 层建议在展示 AT 列表后提供“确认执行”按钮；自动化流程可在多重校验后才发送 `dry_run=false`。
3. **危险开关的影响**：在默认配置（`CTRL_ALLOW_DANGEROUS=0`）下，即使第二次请求 `dry_run=false`，危险动作也依旧只返回计划；只有当环境变量改为 `1` 并重启服务后，才会真正执行。

## 6. 风险分级建议
| Action | 风险等级 | UI 建议 |
| --- | --- | --- |
| reboot | 【高风险】 | 必须二次确认（输入 `CONFIRM`）
| usbnet | 【高风险】 | 显示宿主断链风险提示
| apn | 【高风险】 | 要求管理员口令
| band | 【高风险】 | 强制 dry-run + 二次确认
| cell_lock | 【高风险】 | 标记“实验功能”，需显式勾选
| reset_profile | 【高风险】 | 提示将覆盖自定义配置
| ca | 【高风险】 | 警示吞吐/稳定性变化
| roaming | 【中风险】 | 提醒漫游费用，允许快捷切换
| gnss | 【中风险】 | 提醒功耗变化

## 7. 如何验证本规范与实现保持一致
1. **函数比对**：定期查看 `routes/ctrl.py` 中的 `_plan_*` 与 `_execute_plan()`，确认命令顺序、危险标记与本文描述一致。
2. **脚本自检**：运行 `tools/ctrl_smoketest.sh`（若存在）或自建脚本，依次对所有 action 发送 `dry_run=true` 请求，确认 `detail.planned` 与 `blocked_reason` 符合预期。
3. **接口冒烟**：对至少一个安全动作（如 `roaming`、`gnss`）执行 `dry_run=false`，检查 `raw` 是否回带真实 AT 回显；危险动作在 `CTRL_ALLOW_DANGEROUS=0` 时应被阻止。
4. **变更同步**：每当新增/删除控制端点或变更请求字段、危险等级，必须同时更新本 Markdown，尤其是风险表、动作清单与示例响应。
