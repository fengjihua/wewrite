#!/usr/bin/env python3
# [v0.2] WeChat freepublish API wrappers — follow same pattern as publisher.py
"""
WeChat freepublish (发布能力) API functions.

Usage (import):
    from publish_api import (
        freepublish_submit, freepublish_get, freepublish_batchget,
        freepublish_getarticle, freepublish_delete,
    )
"""

import json
import requests
from dataclasses import dataclass


@dataclass
class PublishSubmitResult:
    publish_id: str
    msg_data_id: str


@dataclass
class PublishStatusResult:
    publish_id: str
    publish_status: int
    article_id: str
    article_url: str
    fail_idx: list[int]


@dataclass
class PublishBatchResult:
    total_count: int
    item_count: int
    items: list[dict]  # [{article_id, content, update_time}, ...]


@dataclass
class PublishArticleResult:
    news_item: list[dict]  # [{title, author, digest, content, thumb_url, url, is_deleted, ...}]


def freepublish_submit(access_token: str, media_id: str) -> PublishSubmitResult:
    """
    Submit a draft for publishing.
    API: POST https://api.weixin.qq.com/cgi-bin/freepublish/submit
    Returns PublishSubmitResult with publish_id and msg_data_id.
    Raise ValueError on API error.
    """
    resp = requests.post(
        "https://api.weixin.qq.com/cgi-bin/freepublish/submit",
        params={"access_token": access_token},
        json={"media_id": media_id},
    )
    resp.encoding = "utf-8"
    data = resp.json()
    errcode = data.get("errcode", 0)  # absent means success
    if errcode != 0:
        errmsg = data.get("errmsg", "unknown error")
        raise ValueError(
            f"WeChat freepublish_submit error: errcode={errcode}, errmsg={errmsg}"
        )
    return PublishSubmitResult(
        publish_id=str(data.get("publish_id", "")),
        msg_data_id=str(data.get("msg_data_id", "")),
    )


def freepublish_get(access_token: str, publish_id: str) -> PublishStatusResult:
    """
    Query the status of a publish task.
    API: POST https://api.weixin.qq.com/cgi-bin/freepublish/get
    Returns PublishStatusResult.
    Raise ValueError on API error.
    """
    resp = requests.post(
        "https://api.weixin.qq.com/cgi-bin/freepublish/get",
        params={"access_token": access_token},
        json={"publish_id": publish_id},
    )
    resp.encoding = "utf-8"
    data = resp.json()
    errcode = data.get("errcode", 0)  # absent means success
    if errcode != 0:
        errmsg = data.get("errmsg", "unknown error")
        raise ValueError(
            f"WeChat freepublish_get error: errcode={errcode}, errmsg={errmsg}"
        )
    return PublishStatusResult(
        publish_id=str(data.get("publish_id", publish_id)),
        publish_status=data.get("publish_status", -1),
        article_id=str(data.get("article_id", "")),
        article_url=str(
            (data.get("article_detail", {}).get("item", [{}])[0].get("article_url", ""))
            if data.get("publish_status") == 0
            else ""
        ),
        fail_idx=data.get("fail_idx", []),
    )


def freepublish_batchget(
    access_token: str,
    offset: int = 0,
    count: int = 20,
    no_content: int = 0,
) -> PublishBatchResult:
    """
    Get a list of successfully published articles.
    API: POST https://api.weixin.qq.com/cgi-bin/freepublish/batchget
    Returns PublishBatchResult.
    Raise ValueError on API error.
    """
    resp = requests.post(
        "https://api.weixin.qq.com/cgi-bin/freepublish/batchget",
        params={"access_token": access_token},
        json={"offset": offset, "count": count, "no_content": no_content},
    )
    resp.encoding = "utf-8"
    data = resp.json()
    errcode = data.get("errcode", 0)  # absent means success
    if errcode != 0:
        errmsg = data.get("errmsg", "unknown error")
        raise ValueError(
            f"WeChat freepublish_batchget error: errcode={errcode}, errmsg={errmsg}"
        )
    return PublishBatchResult(
        total_count=data.get("total_count", 0),
        item_count=data.get("item_count", 0),
        items=data.get("item", []),
    )


def freepublish_getarticle(access_token: str, article_id: str) -> PublishArticleResult:
    """
    Get full detail of a published article.
    API: POST https://api.weixin.qq.com/cgi-bin/freepublish/getarticle
    Returns PublishArticleResult.
    Raise ValueError on API error.
    """
    resp = requests.post(
        "https://api.weixin.qq.com/cgi-bin/freepublish/getarticle",
        params={"access_token": access_token},
        json={"article_id": article_id},
    )
    resp.encoding = "utf-8"
    data = resp.json()
    errcode = data.get("errcode", 0)  # absent means success
    if errcode != 0:
        errmsg = data.get("errmsg", "unknown error")
        raise ValueError(
            f"WeChat freepublish_getarticle error: errcode={errcode}, errmsg={errmsg}"
        )
    return PublishArticleResult(news_item=data.get("news_item", []))


def freepublish_delete(
    access_token: str,
    article_id: str,
    index: int = 1,
) -> dict:
    """
    Delete a published article.
    API: POST https://api.weixin.qq.com/cgi-bin/freepublish/delete
    Returns the full API response dict.
    Raise ValueError on API error.
    """
    body = {"article_id": article_id}
    if index:
        body["index"] = index
    resp = requests.post(
        "https://api.weixin.qq.com/cgi-bin/freepublish/delete",
        params={"access_token": access_token},
        json=body,
    )
    resp.encoding = "utf-8"
    data = resp.json()
    errcode = data.get("errcode", 0)  # absent means success
    if errcode != 0:
        errmsg = data.get("errmsg", "unknown error")
        raise ValueError(
            f"WeChat freepublish_delete error: errcode={errcode}, errmsg={errmsg}"
        )
    return data
