# 应用重启说明

## 问题
新添加的 API 路由（`/v1/ctrl/network_mode` 和 `/v1/ctrl/band_preference`）返回 404，因为应用需要重启才能加载新的路由。

## 解决方案

### 方法1：如果使用 systemd 服务
```bash
sudo systemctl restart linkstation-modem-api
```

### 方法2：如果手动启动的应用
1. 找到运行中的进程：
```bash
ps aux | grep uvicorn
```

2. 停止应用（替换 PID 为实际进程号）：
```bash
kill <PID>
# 或者
kill -9 <PID>  # 强制停止
```

3. 重新启动应用：
```bash
cd /opt/linkstation/modem-api
source .venv/bin/activate  # 如果使用虚拟环境
uvicorn app:app --host 0.0.0.0 --port 8000
```

### 方法3：如果使用 supervisor 或其他进程管理工具
```bash
sudo supervisorctl restart linkstation-modem-api
# 或
sudo supervisorctl restart all
```

## 验证
重启后，测试新 API 是否可用：
```bash
# 测试网络模式查询
curl http://192.168.71.48:8000/v1/ctrl/network_mode

# 应该返回类似：
# {"ok":true,"ts":...,"mode":{"mode_pref":"AUTO"},...}
```

如果仍然返回 404，请检查：
1. 应用日志是否有错误
2. 确认代码已保存
3. 确认路由文件已正确更新

