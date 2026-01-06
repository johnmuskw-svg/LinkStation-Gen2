import logging
from typing import Any, Dict

import requests

import config

logger = logging.getLogger(__name__)


class NvrClient:
    def __init__(self) -> None:
        self.base_url = config.NVR_BASE_URL
        self.timeout = config.NVR_TIMEOUT

    def _get(self, path: str) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        logger.info("NVR GET %s", url)
        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def health(self) -> Dict[str, Any]:
        return self._get("/v1/health")

    def list_cameras(self) -> Dict[str, Any]:
        return self._get("/v1/cameras")

    def stream(self, ip: str) -> Dict[str, Any]:
        """
        获取指定摄像头的 RTSP 流信息（转发 NVR /v1/cameras/{ip}/stream）
        """
        return self._get(f"/v1/cameras/{ip}/stream")

    def live_hls(self, ip: str, profile: str = "sub") -> Dict[str, Any]:
        """
        代理 NVR 的 /v1/cameras/{ip}/live-hls 接口，
        返回包含 hls.playlist 的 JSON。
        
        Args:
            ip: 摄像头IP地址
            profile: 流类型，'sub' 或 'main'，默认 'sub'
        """
        return self._get(f"/v1/cameras/{ip}/live-hls?profile={profile}")

    def recordings(self) -> Dict[str, Any]:
        """代理 NVR: GET /v1/recordings"""
        return self._get("/v1/recordings")

    def recordings_days(self, ip: str) -> Dict[str, Any]:
        """代理 NVR: GET /v1/recordings/{ip}/days"""
        return self._get(f"/v1/recordings/{ip}/days")

    def recordings_segments(self, ip: str, date: str) -> Dict[str, Any]:
        """代理 NVR: GET /v1/recordings/{ip}/days/{date}/segments"""
        return self._get(f"/v1/recordings/{ip}/days/{date}/segments")

    def recordings_file(
        self, 
        ip: str, 
        date: str, 
        filename: str,
        headers: dict = None
    ) -> requests.Response:
        """代理 NVR: GET /v1/recordings/{ip}/files/{date}/{filename}

        返回 requests.Response，供后端直接 Streaming 给客户端
        
        Args:
            ip: 摄像头IP地址
            date: 日期（格式：YYYY-MM-DD）
            filename: 文件名
            headers: 要透传的请求头（如 Range、If-Range）
        """
        url = f"{self.base_url}/v1/recordings/{ip}/files/{date}/{filename}"
        logger.info("NVR GET (file) %s", url)
        
        # 使用30秒超时（mp4首包/网络抖动可能超过3秒）
        file_timeout = 30.0
        
        # 构建请求头（透传 Range、If-Range 等）
        request_headers = {}
        if headers:
            # 只透传 Range 和 If-Range 头（requests 库需要首字母大写的键名）
            if "range" in headers or "Range" in headers:
                request_headers["Range"] = headers.get("Range") or headers.get("range")
            if "if-range" in headers or "If-Range" in headers:
                request_headers["If-Range"] = headers.get("If-Range") or headers.get("if-range")
        
        resp = requests.get(
            url, 
            timeout=file_timeout, 
            stream=True,
            headers=request_headers if request_headers else None
        )
        resp.raise_for_status()
        return resp
