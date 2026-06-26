import time
import mimetypes
import requests
from pathlib import Path
from dataclasses import dataclass

# Token cache
_token_cache: dict = {}

# Unified timeout for WeChat API calls
API_TIMEOUT = 30


@dataclass
class TokenResult:
    access_token: str
    expires_at: float  # unix timestamp
    appid: str
    secret: str


def get_access_token(appid: str, secret: str, force_refresh: bool = False) -> str:
    """
    Get access_token with caching and auto-refresh.
    Cache key: appid
    API: GET https://api.weixin.qq.com/cgi-bin/token
    Cache until expires_in - 300 seconds (5 min buffer).
    Raise ValueError on API error.
    """
    now = time.time()

    if not force_refresh and appid in _token_cache:
        cached: TokenResult = _token_cache[appid]
        if now < cached.expires_at:
            return cached.access_token

    resp = requests.get(
        "https://api.weixin.qq.com/cgi-bin/token",
        params={
            "grant_type": "client_credential",
            "appid": appid,
            "secret": secret,
        },
        timeout=API_TIMEOUT,
    )
    data = resp.json()

    if "access_token" not in data:
        errcode = data.get("errcode", "unknown")
        errmsg = data.get("errmsg", "unknown error")
        raise ValueError(f"WeChat API error: errcode={errcode}, errmsg={errmsg}")

    access_token = data["access_token"]
    expires_in = data.get("expires_in", 7200)

    _token_cache[appid] = TokenResult(
        access_token=access_token,
        expires_at=now + expires_in - 300,
        appid=appid,
        secret=secret,
    )

    return access_token


def ensure_valid_token(appid: str, secret: str) -> str:
    """Get a valid token, force-refreshing if near expiry.

    Use this instead of get_access_token for long-running operations
    where the token may have expired since initial acquisition.
    """
    now = time.time()
    if appid in _token_cache:
        cached = _token_cache[appid]
        if now >= cached.expires_at:
            return get_access_token(appid, secret, force_refresh=True)
        return cached.access_token
    return get_access_token(appid, secret)


def _guess_content_type(file_path: str) -> str:
    """Detect content type from file extension."""
    content_type, _ = mimetypes.guess_type(file_path)
    return content_type or "application/octet-stream"


def upload_image(access_token: str, image_path: str) -> str:
    """
    Upload image for use inside article content.
    API: POST https://api.weixin.qq.com/cgi-bin/media/uploadimg
    Returns the url string.
    Raise ValueError on error.
    """
    path = Path(image_path)
    content_type = _guess_content_type(image_path)

    with open(path, "rb") as f:
        resp = requests.post(
            "https://api.weixin.qq.com/cgi-bin/media/uploadimg",
            params={"access_token": access_token},
            files={"media": (path.name, f, content_type)},
            timeout=API_TIMEOUT,
        )

    data = resp.json()

    if "url" not in data:
        errcode = data.get("errcode", "unknown")
        errmsg = data.get("errmsg", "unknown error")
        raise ValueError(f"WeChat upload_image error: errcode={errcode}, errmsg={errmsg}")

    return data["url"]


def upload_thumb(access_token: str, image_path: str) -> str:
    """
    Upload cover image as permanent material.
    API: POST https://api.weixin.qq.com/cgi-bin/material/add_material
    Returns media_id string.
    Raise ValueError on error.
    """
    path = Path(image_path)
    content_type = _guess_content_type(image_path)

    with open(path, "rb") as f:
        resp = requests.post(
            "https://api.weixin.qq.com/cgi-bin/material/add_material",
            params={"access_token": access_token, "type": "image"},
            files={"media": (path.name, f, content_type)},
            timeout=API_TIMEOUT,
        )

    data = resp.json()

    if "media_id" not in data:
        errcode = data.get("errcode", "unknown")
        errmsg = data.get("errmsg", "unknown error")
        raise ValueError(f"WeChat upload_thumb error: errcode={errcode}, errmsg={errmsg}")

    return data["media_id"]


# [v0.2] delete permanent material by media_id
def delete_material(access_token: str, media_id: str) -> dict:
    """
    Delete a permanent material by media_id.
    API: POST https://api.weixin.qq.com/cgi-bin/material/del_material
    Returns the full API response dict.
    Raise ValueError on API error.
    """
    resp = requests.post(
        "https://api.weixin.qq.com/cgi-bin/material/del_material",
        params={"access_token": access_token},
        json={"media_id": media_id},
    )
    data = resp.json()
    errcode = data.get("errcode", -1)
    if errcode != 0:
        errmsg = data.get("errmsg", "unknown error")
        raise ValueError(
            f"WeChat delete_material error: errcode={errcode}, errmsg={errmsg}"
        )
    return data


# [v0.2] get permanent material info by media_id
def get_material(access_token: str, media_id: str) -> dict:
    """
    Get permanent material metadata by media_id.
    API: POST https://api.weixin.qq.com/cgi-bin/material/get_material
    For image type, returns the image file bytes.
    For news type, returns news_item dict.
    Raise ValueError on API error.
    """
    resp = requests.post(
        "https://api.weixin.qq.com/cgi-bin/material/get_material",
        params={"access_token": access_token},
        json={"media_id": media_id},
    )
    # Image/video material returns raw binary, news returns JSON
    content_type = resp.headers.get("Content-Type", "")
    if "application/json" in content_type or "text/plain" in content_type:
        resp.encoding = "utf-8"
        data = resp.json()
        errcode = data.get("errcode", -1)
        if errcode != 0 and "errcode" in data:
            errmsg = data.get("errmsg", "unknown error")
            raise ValueError(
                f"WeChat get_material error: errcode={errcode}, errmsg={errmsg}"
            )
        return data
    # Binary response (image/voice/video)
    return {"content_type": content_type, "body": resp.content}
