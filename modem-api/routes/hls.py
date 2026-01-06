"""
HLS 静态文件代理路由
用于代理 NVR 的 HLS 播放列表和切片文件
使用 StreamingResponse 实现高效的流式传输
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
import requests

import config

router = APIRouter(tags=["hls"])


@router.get("/live/{ip}/{profile}/index.m3u8")
def nvr_hls_playlist(
    ip: str,
    profile: str,
    request: Request,
) -> StreamingResponse:
    """
    代理 NVR 的 HLS 播放列表文件 /live/{ip}/{profile}/index.m3u8
    
    使用 StreamingResponse 进行流式传输，确保高效传输。
    
    路径：/live/{ip}/{profile}/index.m3u8
    - ip: 摄像头IP地址，例如 192.168.11.103
    - profile: 流类型，'sub'（子码流）或 'main'（主码流）
    """
    if not config.NVR_ENABLED:
        raise HTTPException(status_code=503, detail="NVR integration disabled")
    
    try:
        # 验证 profile 参数
        if profile not in ("sub", "main"):
            raise HTTPException(status_code=400, detail=f"Invalid profile: {profile}")
        
        # 构建 NVR 的完整 URL
        nvr_url = f"{config.get_nvr_base_url()}/live/{ip}/{profile}/index.m3u8"
        
        # 转发请求到 NVR，使用 stream=True 进行流式传输
        resp = requests.get(nvr_url, timeout=config.NVR_TIMEOUT, stream=True)
        resp.raise_for_status()
        
        # 定义生成器函数，逐块传输数据
        def iter_content():
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        
        # 返回流式响应，保持原始 Content-Type
        return StreamingResponse(
            iter_content(),
            media_type=resp.headers.get("Content-Type", "application/vnd.apple.mpegurl"),
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        )
    except requests.exceptions.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"NVR HLS playlist failed: {exc}",
        ) from exc


@router.get("/live/{ip}/{profile}/{filename:path}")
def nvr_hls_segment(
    ip: str,
    profile: str,
    filename: str,
    request: Request,
) -> StreamingResponse:
    """
    代理 NVR 的 HLS 切片文件 /live/{ip}/{profile}/{filename}
    
    使用 StreamingResponse 进行流式传输，确保视频切片文件高效传输到 App。
    
    路径：/live/{ip}/{profile}/{filename}
    - ip: 摄像头IP地址，例如 192.168.11.103
    - profile: 流类型，'sub'（子码流）或 'main'（主码流）
    - filename: 切片文件名，例如 seg_00991.ts
    """
    if not config.NVR_ENABLED:
        raise HTTPException(status_code=503, detail="NVR integration disabled")
    
    try:
        # 验证 profile 参数
        if profile not in ("sub", "main"):
            raise HTTPException(status_code=400, detail=f"Invalid profile: {profile}")
        
        # 构建 NVR 的完整 URL
        nvr_url = f"{config.get_nvr_base_url()}/live/{ip}/{profile}/{filename}"
        
        # 转发请求到 NVR，使用 stream=True 进行流式传输
        resp = requests.get(nvr_url, timeout=config.NVR_TIMEOUT, stream=True)
        resp.raise_for_status()
        
        # 定义生成器函数，逐块传输数据
        def iter_content():
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        
        # 返回流式响应，保持原始 Content-Type
        return StreamingResponse(
            iter_content(),
            media_type=resp.headers.get("Content-Type", "video/mp2t"),
            headers={
                "Cache-Control": "public, max-age=3600",
            }
        )
    except requests.exceptions.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"NVR HLS segment failed: {exc}",
        ) from exc

