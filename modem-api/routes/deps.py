# routes/deps.py
from fastapi import Header, HTTPException
import config

def require_token(x_api_token: str = Header(default=None, alias="X-Api-Token")):
    # 开关没打开就直接放行
    if not config.AUTH_REQUIRED:
        return
    # 开关打开时才校验
    if not x_api_token or x_api_token != config.AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")