# Quectel RM520/RG 系列控制类 AT 命令清单

**总计**: 72 条控制类命令  

**来源**: Quectel RM520/RG Series AT Commands Manual  

**提取日期**: 2024  

## 📊 统计信息

### 按 API 分组

| API 分类 | 命令数量 | 说明 |
|---------|---------|------|
| ctrl/config | 24 | 通用配置 |
| ctrl/file | 2 | 文件操作 |
| ctrl/firmware | 1 | 固件更新 |
| ctrl/gpio | 1 | GPIO 控制 |
| ctrl/lock | 4 | 网络/频段锁定 |
| ctrl/pdp | 6 | PDP 上下文管理 |
| ctrl/power | 4 | 功耗管理 |
| ctrl/radio | 26 | 射频参数配置 |
| ctrl/reboot | 2 | 重启/关机相关 |
| ctrl/reset | 2 | 恢复出厂 |

### 优先级分布

| 优先级 | 命令数量 | 说明 |
|--------|---------|------|
| High | 12 | 高风险操作，需谨慎使用 |
| Medium | 11 | 中等风险，可能影响连接 |
| Low | 49 | 低风险，常规配置 |

## ⚠️ 高优先级命令（High Priority）

| 命令 | 用途 | 语法 | 阻塞 | 危险等级 | 副作用 | 推荐 API |
|------|------|------|------|---------|--------|---------|
| AT+CFUN | 射频开关/模组功能控制（设置功能级别，可重启模组）... | AT+CFUN=<fun>[,<rst>]... | 是 | medium | 可能重启模组，断开所有连接 | ctrl/reboot |
| AT+QCFG="factory" | 恢复出厂设置（完整重置）... | AT+QCFG="factory"... | 是 | high | 完全恢复出厂状态，包括文件系统，模组会重启 | ctrl/reset |
| AT+QCFG="imei" | IMEI 配置（修改 IMEI，需授权）... | AT+QCFG="imei",<imei>... | 否 | high | 修改 IMEI 可能违反法规，需要特殊授权 | ctrl/config |
| AT+QCFG="lte/txpower" | LTE 发射功率配置... | AT+QCFG="lte/txpower",<power>... | 否 | high | 改变 LTE 发射功率 | ctrl/radio |
| AT+QCFG="nr5g/txpower" | 5G 发射功率配置... | AT+QCFG="nr5g/txpower",<power>... | 否 | high | 改变 5G 发射功率 | ctrl/radio |
| AT+QCFG="reset" | 恢复出厂设置（重置所有配置）... | AT+QCFG="reset"... | 是 | high | 所有配置恢复默认值，模组会重启 | ctrl/reset |
| AT+QCFG="thermal" | 热管理配置... | AT+QCFG="thermal",<mode>... | 否 | high | 禁用保护可能导致过热损坏 | ctrl/config |
| AT+QCFG="txpower" | 发射功率配置... | AT+QCFG="txpower",<power>... | 否 | high | 改变发射功率可能影响信号质量和法规合规 | ctrl/radio |
| AT+QFDEL | 文件删除（删除模组内文件）... | AT+QFDEL=<path>... | 否 | high | 删除文件不可恢复 | ctrl/file |
| AT+QFWUPD | 固件更新（通过文件或 URL）... | AT+QFWUPD=<mode>,<source>... | 是 | high | 更新过程中模组会重启，更新失败可能导致变砖 | ctrl/firmware |
| AT+QNWLOCK | 网络/制式锁定（锁定到 LTE/5G/WCDMA 等）... | AT+QNWLOCK=<mode>,<rat>... | 否 | high | 锁定后只能使用指定制式，可能导致无法注册 | ctrl/lock |
| AT+QPOWD | 模组关机（完全断电）... | AT+QPOWD=<mode>... | 是 | high | 模组完全断电，所有功能停止，需外部唤醒 | ctrl/reboot |

## 📋 完整命令列表

| 命令 | 用途 | 语法 | 阻塞 | 危险等级 | 推荐 API | 优先级 |
|------|------|------|------|---------|---------|--------|
| AT+CFUN | 射频开关/模组功能控制（设置功能级别，可重启模组）... | AT+CFUN=<fun>[,<rst>]... | 是 | medium | ctrl/reboot | High |
| AT+QCFG="factory" | 恢复出厂设置（完整重置）... | AT+QCFG="factory"... | 是 | high | ctrl/reset | High |
| AT+QCFG="imei" | IMEI 配置（修改 IMEI，需授权）... | AT+QCFG="imei",<imei>... | 否 | high | ctrl/config | High |
| AT+QCFG="lte/txpower" | LTE 发射功率配置... | AT+QCFG="lte/txpower",<power>... | 否 | high | ctrl/radio | High |
| AT+QCFG="nr5g/txpower" | 5G 发射功率配置... | AT+QCFG="nr5g/txpower",<power>... | 否 | high | ctrl/radio | High |
| AT+QCFG="reset" | 恢复出厂设置（重置所有配置）... | AT+QCFG="reset"... | 是 | high | ctrl/reset | High |
| AT+QCFG="thermal" | 热管理配置... | AT+QCFG="thermal",<mode>... | 否 | high | ctrl/config | High |
| AT+QCFG="txpower" | 发射功率配置... | AT+QCFG="txpower",<power>... | 否 | high | ctrl/radio | High |
| AT+QFDEL | 文件删除（删除模组内文件）... | AT+QFDEL=<path>... | 否 | high | ctrl/file | High |
| AT+QFWUPD | 固件更新（通过文件或 URL）... | AT+QFWUPD=<mode>,<source>... | 是 | high | ctrl/firmware | High |
| AT+QNWLOCK | 网络/制式锁定（锁定到 LTE/5G/WCDMA 等）... | AT+QNWLOCK=<mode>,<rat>... | 否 | high | ctrl/lock | High |
| AT+QPOWD | 模组关机（完全断电）... | AT+QPOWD=<mode>... | 是 | high | ctrl/reboot | High |
| AT+CGDCONT | PDP 上下文定义（设置 APN、IP 类型等）... | AT+CGDCONT=<cid>[,<pdp_type>[,<apn>... | 否 | low | ctrl/pdp | Low |
| AT+QCFG="antenna" | 天线选择配置... | AT+QCFG="antenna",<antenna>... | 否 | low | ctrl/radio | Low |
| AT+QCFG="apn" | APN 配置（设置默认 APN）... | AT+QCFG="apn",<cid>,<apn_name>... | 否 | low | ctrl/pdp | Low |
| AT+QCFG="apn2" | 第二 APN 配置... | AT+QCFG="apn2",<cid>,<apn_name>... | 否 | low | ctrl/pdp | Low |
| AT+QCFG="autocell" | 自动小区选择配置... | AT+QCFG="autocell",<enable>... | 否 | low | ctrl/config | Low |
| AT+QCFG="ca" | 载波聚合配置... | AT+QCFG="ca",<enable>... | 否 | low | ctrl/radio | Low |
| AT+QCFG="data_roaming" | 数据漫游开关... | AT+QCFG="data_roaming",<enable>... | 否 | low | ctrl/config | Low |
| AT+QCFG="edrx" | eDRX 配置（扩展不连续接收）... | AT+QCFG="edrx",<rat>,<enable>,<cycl... | 否 | low | ctrl/power | Low |
| AT+QCFG="fastboot" | 快速启动配置... | AT+QCFG="fastboot",<enable>... | 否 | low | ctrl/config | Low |
| AT+QCFG="gnss" | GNSS 配置（GPS/北斗等）... | AT+QCFG="gnss",<system>,<enable>... | 否 | low | ctrl/config | Low |
| AT+QCFG="gpio" | GPIO 配置（引脚功能设置）... | AT+QCFG="gpio",<pin>,<mode>,<value>... | 否 | low | ctrl/gpio | Low |
| AT+QCFG="ims" | IMS 配置（VoLTE/VoNR 相关）... | AT+QCFG="ims",<enable>... | 否 | low | ctrl/config | Low |
| AT+QCFG="lowpower" | 低功耗模式配置... | AT+QCFG="lowpower",<enable>... | 否 | low | ctrl/power | Low |
| AT+QCFG="lte/antenna" | LTE 天线选择... | AT+QCFG="lte/antenna",<antenna>... | 否 | low | ctrl/radio | Low |
| AT+QCFG="lte/bandwidth" | LTE 带宽配置... | AT+QCFG="lte/bandwidth",<bw>... | 否 | low | ctrl/radio | Low |
| AT+QCFG="lte/ca" | LTE 载波聚合配置... | AT+QCFG="lte/ca",<enable>... | 否 | low | ctrl/radio | Low |
| AT+QCFG="lte/cellreselection" | LTE 小区重选配置... | AT+QCFG="lte/cellreselection",<enab... | 否 | low | ctrl/radio | Low |
| AT+QCFG="lte/dlca" | LTE 下行载波聚合配置... | AT+QCFG="lte/dlca",<enable>... | 否 | low | ctrl/radio | Low |
| AT+QCFG="lte/mimo" | LTE MIMO 配置... | AT+QCFG="lte/mimo",<mode>... | 否 | low | ctrl/radio | Low |
| AT+QCFG="lte/qrxlevmin" | LTE 最小接收电平配置... | AT+QCFG="lte/qrxlevmin",<value>... | 否 | low | ctrl/radio | Low |
| AT+QCFG="lte/ulca" | LTE 上行载波聚合配置... | AT+QCFG="lte/ulca",<enable>... | 否 | low | ctrl/radio | Low |
| AT+QCFG="mimo" | MIMO 配置... | AT+QCFG="mimo",<mode>... | 否 | low | ctrl/radio | Low |
| AT+QCFG="netlight" | 网络指示灯配置... | AT+QCFG="netlight",<enable>... | 否 | low | ctrl/config | Low |
| AT+QCFG="nr5g/antenna" | 5G 天线选择... | AT+QCFG="nr5g/antenna",<antenna>... | 否 | low | ctrl/radio | Low |
| AT+QCFG="nr5g/bandwidth" | 5G 带宽配置... | AT+QCFG="nr5g/bandwidth",<bw>... | 否 | low | ctrl/radio | Low |
| AT+QCFG="nr5g/ca" | 5G 载波聚合配置... | AT+QCFG="nr5g/ca",<enable>... | 否 | low | ctrl/radio | Low |
| AT+QCFG="nr5g/cellreselection" | 5G 小区重选配置... | AT+QCFG="nr5g/cellreselection",<ena... | 否 | low | ctrl/radio | Low |
| AT+QCFG="nr5g/dlca" | 5G 下行载波聚合配置... | AT+QCFG="nr5g/dlca",<enable>... | 否 | low | ctrl/radio | Low |
| AT+QCFG="nr5g/mimo" | 5G MIMO 配置... | AT+QCFG="nr5g/mimo",<mode>... | 否 | low | ctrl/radio | Low |
| AT+QCFG="nr5g/qrxlevmin" | 5G 最小接收电平配置... | AT+QCFG="nr5g/qrxlevmin",<value>... | 否 | low | ctrl/radio | Low |
| AT+QCFG="nr5g/ulca" | 5G 上行载波聚合配置... | AT+QCFG="nr5g/ulca",<enable>... | 否 | low | ctrl/radio | Low |
| AT+QCFG="nwscanmode" | 网络扫描模式配置（自动/手动）... | AT+QCFG="nwscanmode",<mode>... | 否 | low | ctrl/config | Low |
| AT+QCFG="nwscanseq" | 网络扫描序列配置（优先扫描顺序）... | AT+QCFG="nwscanseq",<seq>... | 否 | low | ctrl/config | Low |
| AT+QCFG="pcm" | PCM 音频配置... | AT+QCFG="pcm",<enable>,<sample_rate... | 否 | low | ctrl/config | Low |
| AT+QCFG="pdp/auth" | PDP 认证配置... | AT+QCFG="pdp/auth",<cid>,<auth_type... | 否 | low | ctrl/pdp | Low |
| AT+QCFG="pdp/type" | PDP 类型配置... | AT+QCFG="pdp/type",<cid>,<type>... | 否 | low | ctrl/pdp | Low |
| AT+QCFG="roamservice" | 漫游服务配置（启用/禁用漫游）... | AT+QCFG="roamservice",<enable>... | 否 | low | ctrl/config | Low |
| AT+QCFG="rrc" | RRC 配置（无线资源控制）... | AT+QCFG="rrc",<mode>... | 否 | low | ctrl/radio | Low |
| AT+QCFG="servicetype" | 服务类型配置（CS/PS/CS+PS）... | AT+QCFG="servicetype",<type>... | 否 | low | ctrl/config | Low |
| AT+QCFG="sim" | SIM 卡配置（SIM 选择等）... | AT+QCFG="sim",<slot>... | 否 | low | ctrl/config | Low |
| AT+QCFG="urc/cellind" | 小区指示 URC 配置... | AT+QCFG="urc/cellind",<enable>... | 否 | low | ctrl/config | Low |
| AT+QCFG="urc/ri" | RI（Ring Indicator）配置... | AT+QCFG="urc/ri",<pin>,<mode>... | 否 | low | ctrl/config | Low |
| AT+QCFG="usbnet" | 设置 USB 网络模式（ECM/RNDIS/NCM）... | AT+QCFG="usbnet",<mode>... | 否 | low | ctrl/config | Low |
| AT+QCFG="usbspeed" | 设置 USB 速率模式（USB 2.0/3.1 Gen1/Gen2）... | AT+QCFG="usbspeed",<speed>... | 否 | low | ctrl/config | Low |
| AT+QCFG="volte" | VoLTE 配置... | AT+QCFG="volte",<enable>... | 否 | low | ctrl/config | Low |
| AT+QCFG="vonr" | VoNR 配置（5G 语音）... | AT+QCFG="vonr",<enable>... | 否 | low | ctrl/config | Low |
| AT+QFLST | 文件列表（列出模组内文件）... | AT+QFLST=<path>... | 否 | low | ctrl/file | Low |
| AT+QPRTPARA | 打印参数设置（控制 URC 输出）... | AT+QPRTPARA=<mode>... | 否 | low | ctrl/config | Low |
| AT+QSCLK | 睡眠模式控制（进入/退出睡眠）... | AT+QSCLK=<enable>... | 否 | low | ctrl/power | Low |
| AT+CGACT | PDP 上下文激活/去激活... | AT+CGACT=<state>[,<cid>[,<cid>[,<ci... | 否 | low | ctrl/pdp | Medium |
| AT+QCFG="band" | 频段锁定配置（锁定到指定 LTE/NR 频段）... | AT+QCFG="band",<rat>,<band_list>... | 否 | medium | ctrl/lock | Medium |
| AT+QCFG="iotopmode" | IoT 操作模式配置（Cat-M/NB-IoT 等）... | AT+QCFG="iotopmode",<mode>... | 否 | medium | ctrl/config | Medium |
| AT+QCFG="lte/band" | LTE 频段锁定（详细配置）... | AT+QCFG="lte/band",<band_mask>... | 否 | medium | ctrl/lock | Medium |
| AT+QCFG="lte/handover" | LTE 切换配置... | AT+QCFG="lte/handover",<enable>... | 否 | medium | ctrl/radio | Medium |
| AT+QCFG="nr5g/band" | 5G 频段锁定（详细配置）... | AT+QCFG="nr5g/band",<band_mask>... | 否 | medium | ctrl/lock | Medium |
| AT+QCFG="nr5g/handover" | 5G 切换配置... | AT+QCFG="nr5g/handover",<enable>... | 否 | medium | ctrl/radio | Medium |
| AT+QCFG="psm" | PSM 配置（省电模式）... | AT+QCFG="psm",<enable>,<tau>,<activ... | 否 | medium | ctrl/power | Medium |
| AT+QCFG="rat" | RAT 优先级配置... | AT+QCFG="rat",<rat_list>... | 否 | medium | ctrl/config | Medium |
| AT+QCFG="sar" | SAR 配置（比吸收率限制）... | AT+QCFG="sar",<level>... | 否 | medium | ctrl/radio | Medium |
| AT+QCFG="uart" | UART 配置（波特率、数据位等）... | AT+QCFG="uart",<baudrate>,<databits... | 否 | medium | ctrl/config | Medium |