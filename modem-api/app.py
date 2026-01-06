# app.py  —— 主应用装配
from fastapi import FastAPI, Depends
import config

from routes.info import router as info_router
from routes.live import router as live_router
from routes.health import router as health_router
from routes.ctrl import router as ctrl_router
from routes.base import router as base_router
from routes.gnss import router as gnss_router
from routes import nvr as nvr_router
from routes.net import router as net_router
from routes.hls import router as hls_router
from routes.deps import require_token  # ← 第四步新增的依赖

app = FastAPI(title=config.API_TITLE)

# 只有当 .env 里 AUTH_REQUIRED=1 才启用鉴权
_guard = [Depends(require_token)] if config.AUTH_REQUIRED else []

# 1) 健康/版本信息始终开放（便于自检和联调）
app.include_router(health_router, prefix=config.API_PREFIX)
app.include_router(ctrl_router, prefix=config.API_PREFIX)   # /v1/ctrl/*

# 2) 业务路由：按开关决定是否启用 X-Api-Token 校验
app.include_router(info_router, prefix=config.API_PREFIX, dependencies=_guard)  # /v1/info
app.include_router(live_router, prefix=config.API_PREFIX, dependencies=_guard)  # /v1/live
app.include_router(base_router, prefix=config.API_PREFIX)
app.include_router(gnss_router, prefix=config.API_PREFIX, dependencies=_guard)  # /v1/gnss
app.include_router(nvr_router.router, prefix=config.API_PREFIX)  # /v1/nvr
app.include_router(net_router, prefix=config.API_PREFIX, dependencies=_guard)  # /v1/net
app.include_router(hls_router)  # /live/* - HLS 静态文件代理（无前缀）
