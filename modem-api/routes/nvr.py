from typing import Any, Dict, Optional
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException, Request, Query, Header
from fastapi.responses import StreamingResponse, Response
import requests

import config
from nvr_client import NvrClient

router = APIRouter(prefix="/nvr", tags=["nvr"])


def get_client() -> NvrClient:
    if not config.NVR_ENABLED:
        raise HTTPException(status_code=503, detail="NVR integration disabled")
    return NvrClient()


def _rewrite_stream_urls_for_public(data: dict, ip: str) -> dict:
    """
    将 RTSP URL 中的主机和端口重写为 NVR 统一入口地址
    """
    stream = data.get("stream") or {}
    url = stream.get("url")
    main_url = stream.get("main_url")

    if not url:
        return data

    # 计算外部端口：9550 + (最后一段 IP - 100)
    try:
        last_octet = int(ip.split(".")[-1])
    except (ValueError, IndexError):
        return data

    offset = last_octet - 100
    if offset < 1:
        return data

    external_port = config.NVR_PUBLIC_SUB_BASE_PORT + offset
    public_host = config.NVR_PUBLIC_HOST

    def _rewrite_one(original: str) -> str:
        parsed = urlparse(original)
        # netloc 里可能有 user:pass@
        host_port = parsed.netloc
        if "@" in host_port:
            userinfo, _ = host_port.split("@", 1)
            new_netloc = f"{userinfo}@{public_host}:{external_port}"
        else:
            new_netloc = f"{public_host}:{external_port}"
        return urlunparse((
            parsed.scheme,
            new_netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        ))

    stream["url"] = _rewrite_one(url)
    if main_url:
        stream["main_url"] = _rewrite_one(main_url)
    data["stream"] = stream
    return data


@router.get("/health")
def nvr_health(client: NvrClient = Depends(get_client)) -> Dict[str, Any]:
    """
    代理 NVR /v1/health
    """
    try:
        data = client.health()
        return {
            "ok": True,
            "ts": data.get("ts"),
            "nvr": data,
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"NVR health failed: {exc}") from exc


@router.get("/cameras")
def nvr_cameras(client: NvrClient = Depends(get_client)) -> Dict[str, Any]:
    """
    代理 NVR /v1/cameras，直接透传 NVR 的完整响应（不做任何解析、过滤或转换）。
    
    返回结构（完全透传 NVR 原始响应，支持 List 或 Map 两种结构）：
    
    结构1 - List 格式：
    {
      "ok": true,
      "ts": ...,
      "cameras": [
        {
          "ip": "192.168.11.101",
          "model": "...",
          "auth_status": "...",  # 新增字段
          "main_stream_uri": "...",  # 新增字段
          ...
        },
        ...
      ],
      "error": null
    }
    
    结构2 - Map 格式（以 IP 为键）：
    {
      "ok": true,
      "ts": ...,
      "cameras": {
        "192.168.11.101": {
          "ip": "192.168.11.101",
          "model": "...",
          "auth_status": "...",
          "main_stream_uri": "...",
          ...
        },
        "192.168.11.102": {...},
        ...
      },
      "error": null
    }
    
    重要：CPE 作为"诚实的传话筒"，无论 NVR 返回 List 还是 Map，都原样转发给 App。
    不做任何字段过滤、类型校验或结构转换，确保 NVR 新增的字段能完整传递。
    """
    try:
        # 直接透传 NVR 的完整响应，不进行任何解析、过滤或转换
        # 不管 NVR 返回的是 List 还是 Map，都原样转发
        data = client.list_cameras()
        return data
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"NVR cameras failed: {exc}") from exc


@router.get("/cameras/{ip}/stream")
def nvr_camera_stream(
    ip: str,
    client: NvrClient = Depends(get_client),
) -> Dict[str, Any]:
    """
    代理 NVR /v1/cameras/{ip}/stream，返回指定摄像头的 RTSP 预览流信息
    将 RTSP URL 重写为通过 NVR 统一入口访问
    """
    try:
        data = client.stream(ip)
        data = _rewrite_stream_urls_for_public(data, ip)
        return data
    except Exception as exc:  # noqa: BLE001
        # 保持和其他 NVR 路由一样的错误风格
        raise HTTPException(
            status_code=502,
            detail=f"NVR stream failed: {exc}",
        ) from exc


@router.get("/cameras/{ip}/live-hls")
def nvr_camera_live_hls(
    ip: str,
    profile: str = Query("sub", description="流类型：'sub'（子码流）或 'main'（主码流）"),
    client: NvrClient = Depends(get_client),
) -> Dict[str, Any]:
    """
    代理 NVR /v1/cameras/{ip}/live-hls，返回 HLS 播放地址。

    请求参数：
    - ip: 摄像头IP地址（路径参数）
    - profile: 流类型（查询参数），'sub'（子码流，默认）或 'main'（主码流）

    NVR 返回结构：
    {
      "ok": true,
      "ts": ...,
      "camera": {
        "ip": "192.168.11.101",
        "online": true,  # 强制设置为 true（成功获取 HLS 说明设备在线）
        "auth": "ok",  # 强制设置为 "ok"（成功获取 HLS 说明认证成功）
        "auth_status": "ok",
        "main_stream_uri": "...",
        ...
      },
      "hls": {
        "playlist": "/live/192.168.11.101/sub/index.m3u8",
        "profile": "sub",
        "segment_seconds": 1,
        "window_seconds": 6
      },
      "error": null
    }
    
    重要逻辑：
    - 成功调用 nvr_client.live_hls(...) 并拿到结果，说明 NVR 认为该设备在线且认证成功
    - 强制将 camera.online 设为 True，camera.auth 设为 'ok'
    - 不依赖本地缓存状态，以前端请求这一刻的成功为准
    - 确保 App 收到 online: true 和 auth: ok，从而启动播放器
    
    注意：playlist 保持相对路径，App 需要通过 modem-api 代理访问。
    """
    try:
        # 验证 profile 参数
        if profile not in ("sub", "main"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid profile: {profile}. Must be 'sub' or 'main'"
            )
        
        # 调用 NVR API 获取 HLS 播放列表
        # 如果成功返回，说明设备在线且认证成功
        data = client.live_hls(ip, profile=profile)
        
        # 强制设置状态：成功获取 HLS 说明设备在线且认证成功
        # 不依赖缓存，以前端请求这一刻的成功为准
        if isinstance(data, dict):
            camera = data.get("camera")
            if isinstance(camera, dict):
                # 强制设置在线状态和认证状态
                camera["online"] = True
                camera["auth"] = "ok"
                # 如果存在 auth_status 字段，也设置为 ok
                if "auth_status" in camera:
                    camera["auth_status"] = "ok"
        
        return data
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"NVR live-hls failed: {exc}",
        ) from exc


@router.get("/recordings")
def nvr_recordings_list(
    client: NvrClient = Depends(get_client),
) -> Dict[str, Any]:
    """
    代理 NVR /v1/recordings，列出有录像的摄像头
    """
    try:
        data = client.recordings()
        # 直接透传 NVR 的 JSON：
        # {
        #   "ok": true,
        #   "ts": ...,
        #   "cameras": [...],
        #   "error": null
        # }
        return data
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"NVR recordings list failed: {exc}",
        ) from exc


@router.get("/recordings/{ip}/days")
def nvr_recordings_days(
    ip: str,
    client: NvrClient = Depends(get_client),
) -> Dict[str, Any]:
    """
    代理 NVR /v1/recordings/{ip}/days，列出某个摄像头的日期列表
    """
    try:
        data = client.recordings_days(ip)
        return data
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"NVR recordings days failed: {exc}",
        ) from exc


@router.get("/recordings/{ip}/days/{date}/segments")
def nvr_recordings_segments(
    ip: str,
    date: str,
    request: Request,
    client: NvrClient = Depends(get_client),
) -> Dict[str, Any]:
    """
    代理 NVR /v1/recordings/{ip}/days/{date}/segments，列出某天的所有片段
    并将每个 segment 的 url 字段改写成 Gen2 的地址
    """
    try:
        data = client.recordings_segments(ip, date)
        
        # 获取 Gen2 的基础 URL（用于重写 segment URL）
        # 从请求中获取 scheme 和 host
        scheme = request.url.scheme
        host = request.url.hostname
        port = request.url.port
        if port:
            gen2_base = f"{scheme}://{host}:{port}"
        else:
            gen2_base = f"{scheme}://{host}"
        
        # 重写 segments 中的 url 字段
        if isinstance(data, dict) and "segments" in data:
            segments = data["segments"]
            if isinstance(segments, list):
                for segment in segments:
                    if isinstance(segment, dict) and "url" in segment:
                        # 保存原始 URL（调试用）
                        original_url = segment.get("url")
                        if original_url:
                            segment["origin_url"] = original_url
                        
                        # 重写为 Gen2 地址
                        # 从原始 URL 中提取 filename（如果可能）
                        # 或者从 segment 的其他字段中获取
                        filename = segment.get("filename")
                        if filename:
                            segment["url"] = f"{gen2_base}/v1/nvr/recordings/{ip}/files/{date}/{filename}"
                        elif original_url:
                            # 如果原始 URL 是完整路径，尝试提取文件名
                            try:
                                parsed = urlparse(original_url)
                                path_parts = parsed.path.strip("/").split("/")
                                if path_parts:
                                    filename = path_parts[-1]
                                    segment["url"] = f"{gen2_base}/v1/nvr/recordings/{ip}/files/{date}/{filename}"
                            except Exception:
                                # 解析失败，保持原样或使用原始 URL
                                pass
        
        return data
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"NVR recordings segments failed: {exc}",
        ) from exc


@router.get("/recordings/{ip}/files/{date}/{filename}")
def nvr_recordings_file(
    ip: str,
    date: str,
    filename: str,
    request: Request,
    range_header: Optional[str] = Header(None, alias="Range"),
    if_range_header: Optional[str] = Header(None, alias="If-Range"),
    client: NvrClient = Depends(get_client),
) -> StreamingResponse:
    """
    代理 NVR 录像文件，流式传输给客户端
    
    支持 Range 请求（断点续传），透传请求头和响应头
    """
    try:
        # 构建要透传的请求头
        headers = {}
        if range_header:
            headers["range"] = range_header
        if if_range_header:
            headers["if-range"] = if_range_header
        
        # 调用 NVR 客户端（使用30秒超时）
        resp = client.recordings_file(ip, date, filename, headers=headers)
    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=504,
            detail="NVR recording file request timeout",
        )
    except requests.exceptions.RequestException as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"NVR recording file failed: {exc}",
        ) from exc

    # 流式转发内容（不要一次性读入内存）
    def iter_content():
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                yield chunk

    # 构建响应头（透传关键响应头）
    response_headers = {}
    
    # 透传 Content-Type
    if "Content-Type" in resp.headers:
        response_headers["Content-Type"] = resp.headers["Content-Type"]
    
    # 透传 Content-Length（如果存在）
    if "Content-Length" in resp.headers:
        response_headers["Content-Length"] = resp.headers["Content-Length"]
    
    # 透传 Content-Range（Range 请求时会有）
    if "Content-Range" in resp.headers:
        response_headers["Content-Range"] = resp.headers["Content-Range"]
    
    # 透传 Accept-Ranges
    if "Accept-Ranges" in resp.headers:
        response_headers["Accept-Ranges"] = resp.headers["Accept-Ranges"]
    
    # 透传 ETag（如果存在）
    if "ETag" in resp.headers:
        response_headers["ETag"] = resp.headers["ETag"]
    
    # 获取状态码（原样返回 206/200）
    status_code = resp.status_code
    
    # 确定 media_type（默认 video/mp4）
    media_type = resp.headers.get("Content-Type", "video/mp4")
    
    return StreamingResponse(
        iter_content(),
        status_code=status_code,
        media_type=media_type,
        headers=response_headers,
    )

