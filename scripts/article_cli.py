#!/usr/bin/env python3
# [v0.2] WeChat article lifecycle CLI — draft management + publish management
#
# Terminology: wewrite uses "article", mkt-sns skill uses "note".
# This CLI wraps both existing wewrite functions (create_draft, get_draft,
# upload_image) and new v0.2 functions (freepublish_*, delete_draft).
#
# Usage:
#     python3 article_cli.py draft_add    --input article.md --cover cover.jpg --title "标题" --json
#     python3 article_cli.py draft_get    --media_id <id> --json
#     python3 article_cli.py draft_delete --media_id <id>
#     python3 article_cli.py freepublish_batchget --json
#     python3 article_cli.py freepublish_getarticle --article_id <id> --json
#     python3 article_cli.py freepublish_submit   --media_id <id>
#     python3 article_cli.py freepublish_delete   --article_id <id>
#
# Requires: wechat appid/secret in config.yaml or env vars (WECHAT_APPID, WECHAT_SECRET)

import argparse
import json
import os
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SKILL_DIR / "toolkit"))
from config import load_config, get_wechat_credentials
from wechat_api import get_access_token, upload_image, upload_thumb
from publisher import create_draft, get_draft, delete_draft
from wechat_api import delete_material, get_material
from converter import WeChatConverter
from theme import load_theme
from publish_api import (
    freepublish_submit, freepublish_get, freepublish_batchget,
    freepublish_getarticle, freepublish_delete,
)


def _print_json(obj):
    """Print dataclass or dict as JSON to stdout (UTF-8 safe)."""
    if hasattr(obj, "__dataclass_fields__"):
        payload = json.dumps(obj.__dict__, ensure_ascii=False, indent=2)
    elif isinstance(obj, (dict, list)):
        payload = json.dumps(obj, ensure_ascii=False, indent=2)
    else:
        payload = str(obj)
    sys.stdout.buffer.write(payload.encode("utf-8") + b"\n")


# ---------------------------------------------------------------------------
# draft_add — wraps wewrite's existing create_draft pipeline
# (Markdown→HTML convert + image upload + draft/create API)
# ---------------------------------------------------------------------------

def _cmd_draft_add(args):
    """
    [v0.2] Create a draft article from Markdown.

    Follows the same pipeline as wewrite's `cli.py publish` but stops
    at the draft stage without submitting for publish.  Reuses existing
    converter and wechat_api modules from the toolkit.
    """
    cfg = load_config()
    wechat_cfg = cfg.get("wechat", {})
    appid = args.appid or wechat_cfg.get("appid")
    secret = args.secret or wechat_cfg.get("secret")
    theme_name = args.theme or cfg.get("theme", "professional-clean")
    author = args.author or wechat_cfg.get("author")

    if not appid or not secret:
        print("Error: --appid and --secret required (or set in config.yaml)",
              file=sys.stderr)
        sys.exit(1)

    # 1. Convert Markdown → WeChat HTML
    theme = load_theme(theme_name)
    converter = WeChatConverter(theme=theme)
    result = converter.convert_file(args.input)

    title = args.title or result.title or Path(args.input).stem
    digest = args.digest or result.digest
    html = result.html

    token = get_access_token(appid, secret)

    # 2. Upload inline images referenced in article
    md_dir = Path(args.input).resolve().parent
    for img_src in result.images:
        if img_src.startswith(("http://", "https://")):
            continue
        img_path = Path(img_src)
        if not img_path.is_absolute():
            if not img_path.exists():
                img_path = md_dir / img_src
        if img_path.exists():
            wechat_url = upload_image(token, str(img_path))
            html = html.replace(img_src, wechat_url)

    # 3. Upload cover image
    thumb_media_id = None
    if args.cover:
        thumb_media_id = upload_thumb(token, args.cover)

    # 4. Create draft via existing create_draft()
    draft = create_draft(
        access_token=token,
        title=title,
        html=html,
        digest=digest,
        thumb_media_id=thumb_media_id,
        author=author,
    )

    return {
        "media_id": draft.media_id,
        "title": title,
        "thumb_media_id": thumb_media_id or "",
        "image_count": len(result.images),
        "digest": digest,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="WeChat article lifecycle CLI")
    sub = parser.add_subparsers(dest="action", required=True)

    # ---- draft stage ----
    p_draft_add = sub.add_parser("draft_add",
        help="[v0.2] Create draft from Markdown (wraps existing create_draft pipeline)")
    p_draft_add.add_argument("input", help="Markdown file path")
    p_draft_add.add_argument("--appid", default=None)
    p_draft_add.add_argument("--secret", default=None)
    p_draft_add.add_argument("--cover", help="Cover image path")
    p_draft_add.add_argument("--title", help="Override article title")
    p_draft_add.add_argument("--author", default=None)
    p_draft_add.add_argument("--digest", default=None)
    p_draft_add.add_argument("--theme", default=None)
    p_draft_add.add_argument("--json", action="store_true")

    p_draft_get = sub.add_parser("draft_get", help="Get draft content by media_id")
    p_draft_get.add_argument("--media_id", required=True)
    p_draft_get.add_argument("--json", action="store_true")

    p_draft_del = sub.add_parser("draft_delete", help="Delete draft by media_id")
    p_draft_del.add_argument("--media_id", required=True)
    p_draft_del.add_argument("--json", action="store_true")

    # ---- material management ----
    p_mat_del = sub.add_parser("material_delete", help="[v0.2] Delete permanent material by media_id")
    p_mat_del.add_argument("--media_id", required=True)
    p_mat_del.add_argument("--json", action="store_true")

    p_mat_get = sub.add_parser("material_get", help="[v0.2] Get permanent material by media_id")
    p_mat_get.add_argument("--media_id", required=True)
    p_mat_get.add_argument("--json", action="store_true")

    # ---- publish stage ----
    # 注意: freepublish_batchget 仅返回"发布但不通知"的图文列表，
    #       "群发通知"的图文不会出现在此列表中。
    p_submit = sub.add_parser("freepublish_submit", help="Submit draft for publishing")
    p_submit.add_argument("--media_id", required=True)
    p_submit.add_argument("--json", action="store_true")

    p_get = sub.add_parser("freepublish_get", help="Query publish task status")
    p_get.add_argument("--publish_id", required=True)
    p_get.add_argument("--json", action="store_true")

    p_batch = sub.add_parser("freepublish_batchget",
        help="List published articles (仅发布但不通知的图文)")
    p_batch.add_argument("--offset", type=int, default=0)
    p_batch.add_argument("--count", type=int, default=20)
    p_batch.add_argument("--no_content", type=int, default=0)
    p_batch.add_argument("--json", action="store_true")

    p_article = sub.add_parser("freepublish_getarticle",
        help="Get published article detail")
    p_article.add_argument("--article_id", required=True)
    p_article.add_argument("--json", action="store_true")

    p_delete = sub.add_parser("freepublish_delete",
        help="Delete published article")
    p_delete.add_argument("--article_id", required=True)
    p_delete.add_argument("--index", type=int, default=1)
    p_delete.add_argument("--json", action="store_true")

    args = parser.parse_args()

    try:
        appid, secret = get_wechat_credentials()
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    token = get_access_token(appid, secret)

    try:
        if args.action == "draft_add":
            # [v0.2] uses same pipeline as cli.py publish, but stops at draft
            result = _cmd_draft_add(args)
            if args.json:
                _print_json(result)
            else:
                print(f"Draft created: media_id={result['media_id']}")

        elif args.action == "draft_get":
            # [v0.2] Return all fields from news_item for full UPSERT
            import requests as _requests
            resp = _requests.post(
                "https://api.weixin.qq.com/cgi-bin/draft/get",
                params={"access_token": token},
                json={"media_id": args.media_id},
            )
            resp.encoding = "utf-8"
            data = resp.json()
            news = (data.get("news_item") or [{}])[0]
            if args.json:
                _print_json({
                    "media_id": args.media_id,
                    "title": news.get("title", ""),
                    "author": news.get("author", ""),
                    "digest": news.get("digest", ""),
                    "content": news.get("content", ""),
                    "content_source_url": news.get("content_source_url", ""),
                    "thumb_media_id": news.get("thumb_media_id", ""),
                    "thumb_url": news.get("thumb_url", ""),
                    "url": news.get("url", ""),
                    "need_open_comment": news.get("need_open_comment", 0),
                    "only_fans_can_comment": news.get("only_fans_can_comment", 0),
                })
            else:
                print(news.get("content", ""))

        elif args.action == "draft_delete":
            result = delete_draft(token, args.media_id)
            if args.json:
                _print_json(result)
            else:
                print(f"Draft deleted: {args.media_id}")

        elif args.action == "material_delete":
            result = delete_material(token, args.media_id)
            if args.json:
                _print_json(result)
            else:
                print(f"Material deleted: {args.media_id}")

        elif args.action == "material_get":
            result = get_material(token, args.media_id)
            if args.json:
                if "body" in result:
                    print(f"(binary, {len(result['body'])} bytes, {result['content_type']})")
                else:
                    _print_json(result)
            else:
                print(result)

        elif args.action == "freepublish_submit":
            result = freepublish_submit(token, args.media_id)
            _print_json(result)

        elif args.action == "freepublish_get":
            result = freepublish_get(token, args.publish_id)
            _print_json(result)

        elif args.action == "freepublish_batchget":
            result = freepublish_batchget(token, args.offset, args.count, args.no_content)
            _print_json(result)

        elif args.action == "freepublish_getarticle":
            result = freepublish_getarticle(token, args.article_id)
            _print_json(result)

        elif args.action == "freepublish_delete":
            result = freepublish_delete(token, args.article_id, args.index)
            _print_json(result)

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
