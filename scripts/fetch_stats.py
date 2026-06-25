#!/usr/bin/env python3
"""
Fetch WeChat article & account statistics.

Uses WeChat Data Analytics API (new endpoints):
  Account-level:
    - /datacube/getusersummary   (daily new/cancel users, max 7d)
    - /datacube/getusercumulate  (daily cumulative users, max 7d)
  Note-level:
    - /datacube/getarticletotaldetail (per-article detail with daily stats, 1d query)

DEPRECATED (kept for backward compat):
    - /datacube/getarticlesummary
    - /datacube/getarticletotal

Usage:
    python3 fetch_stats.py --days 7                          # default: notes only
    python3 fetch_stats.py --days 7 --type account            # account only
    python3 fetch_stats.py --days 7 --type all                # both
    python3 fetch_stats.py --days 7 --json                    # machine-readable JSON output
    python3 fetch_stats.py --days 7 --type all --json --account-id yqbc  # with account label

Requires: wechat appid/secret in config.yaml or env vars (WECHAT_APPID, WECHAT_SECRET)
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# 确保 stdout 使用 UTF-8，防止 subprocess 管道中中文乱码
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import requests
import yaml

SKILL_DIR = Path(__file__).parent.parent

sys.path.insert(0, str(SKILL_DIR / "toolkit"))
from config import load_config, get_wechat_credentials

API_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------

def _get_access_token(appid: str, secret: str) -> str:
    resp = requests.get(
        "https://api.weixin.qq.com/cgi-bin/token",
        params={"grant_type": "client_credential", "appid": appid, "secret": secret},
        timeout=API_TIMEOUT,
    )
    data = resp.json()
    if "access_token" not in data:
        raise ValueError(f"Token error: {data}")
    return data["access_token"]


# ---------------------------------------------------------------------------
# Account-level APIs (NEW)
# ---------------------------------------------------------------------------

def fetch_user_summary(token: str, begin_date: str, end_date: str) -> list[dict]:
    """
    Daily user growth/shrink.
    API: POST /datacube/getusersummary  (max 7 days)
    Returns list of {ref_date, user_source, new_user, cancel_user}
    """
    resp = requests.post(
        "https://api.weixin.qq.com/datacube/getusersummary",
        params={"access_token": token},
        json={"begin_date": begin_date, "end_date": end_date},
        timeout=API_TIMEOUT,
    )
    data = resp.json()
    if "list" not in data:
        errcode = data.get("errcode", "unknown")
        if errcode == 61500 or errcode == 61501:
            return []
        print(f"[warn] getusersummary error: {errcode} {data.get('errmsg','')}", file=sys.stderr)
        return []
    return data["list"]


def fetch_user_cumulate(token: str, begin_date: str, end_date: str) -> list[dict]:
    """
    Daily cumulative user count.
    API: POST /datacube/getusercumulate  (max 7 days)
    Returns list of {ref_date, cumulate_user}
    """
    resp = requests.post(
        "https://api.weixin.qq.com/datacube/getusercumulate",
        params={"access_token": token},
        json={"begin_date": begin_date, "end_date": end_date},
        timeout=API_TIMEOUT,
    )
    data = resp.json()
    if "list" not in data:
        errcode = data.get("errcode", "unknown")
        if errcode == 61500 or errcode == 61501:
            return []
        print(f"[warn] getusercumulate error: {errcode} {data.get('errmsg','')}", file=sys.stderr)
        return []
    return data["list"]


# ---------------------------------------------------------------------------
# Note-level API (NEW — replaces deprecated getarticlesummary)
# ---------------------------------------------------------------------------

def fetch_article_total_detail(token: str, date_str: str) -> list[dict]:
    """
    Per-article detailed stats published on date_str, with daily breakdown.
    API: POST /datacube/getarticletotaldetail  (1 day query)
    Returns list of articles, each with detail_list of per-day cumulative stats.
    """
    resp = requests.post(
        "https://api.weixin.qq.com/datacube/getarticletotaldetail",
        params={"access_token": token},
        json={"begin_date": date_str, "end_date": date_str},
        timeout=API_TIMEOUT,
    )
    data = resp.json()
    if "list" not in data:
        errcode = data.get("errcode", "unknown")
        if errcode == 61500:
            return []
        print(f"[warn] getarticletotaldetail error ({date_str}): {errcode} {data.get('errmsg','')}",
              file=sys.stderr)
        return []
    return data["list"]


# ---------------------------------------------------------------------------
# Deprecated APIs (kept for backward compat)
# ---------------------------------------------------------------------------

def fetch_article_summary(token: str, date: str) -> list[dict]:
    """DEPRECATED — use fetch_article_total_detail instead."""
    resp = requests.post(
        "https://api.weixin.qq.com/datacube/getarticlesummary",
        params={"access_token": token},
        json={"begin_date": date, "end_date": date},
        timeout=API_TIMEOUT,
    )
    data = resp.json()
    if "list" not in data:
        errcode = data.get("errcode", "unknown")
        errmsg = data.get("errmsg", "")
        if errcode == 61500:
            return []
        print(f"[warn] getarticlesummary error: {errcode} {errmsg}", file=sys.stderr)
        return []
    return data["list"]


def fetch_article_total(token: str, date: str) -> list[dict]:
    """DEPRECATED — cumulative stats."""
    resp = requests.post(
        "https://api.weixin.qq.com/datacube/getarticletotal",
        params={"access_token": token},
        json={"begin_date": date, "end_date": date},
        timeout=API_TIMEOUT,
    )
    data = resp.json()
    if "list" not in data:
        return []
    return data["list"]


# ---------------------------------------------------------------------------
# Collect
# ---------------------------------------------------------------------------

def collect_account_data(token: str, days: int) -> list[dict]:
    """Collect account-level KPI data for last N days."""
    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    results = []

    # Chunk by 7-day windows (API limit)
    chunk_start = datetime.now() - timedelta(days=days)
    while chunk_start < datetime.now():
        chunk_end = chunk_start + timedelta(days=6)
        begin = chunk_start.strftime("%Y-%m-%d")
        end = min(chunk_end, datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        # User summary
        for item in fetch_user_summary(token, begin, end):
            results.append({
                "type": "user_summary",
                "ref_date": item["ref_date"],
                "user_source": item.get("user_source", 0),
                "new_user": item.get("new_user", 0),
                "cancel_user": item.get("cancel_user", 0),
            })

        # User cumulate
        for item in fetch_user_cumulate(token, begin, end):
            results.append({
                "type": "user_cumulate",
                "ref_date": item["ref_date"],
                "cumulate_user": item.get("cumulate_user", 0),
            })

        chunk_start = chunk_end + timedelta(days=1)

    return results


def collect_note_data(token: str, days: int) -> list[dict]:
    """Collect note-level KPI data for last N days."""
    results = []
    for i in range(days):
        date_str = (datetime.now() - timedelta(days=i + 1)).strftime("%Y-%m-%d")
        articles = fetch_article_total_detail(token, date_str)
        for article in articles:
            for stat in article.get("detail_list", []):
                results.append({
                    "type": "note_detail",
                    "ref_date": article.get("ref_date", date_str),
                    "msgid": article.get("msgid", ""),
                    "title": article.get("title", ""),
                    "content_url": article.get("content_url", ""),
                    "publish_type": article.get("publish_type", 0),
                    "stat_date": stat.get("stat_date", ""),
                    "read_user": stat.get("read_user", 0),
                    "share_user": stat.get("share_user", 0),
                    "zaikan_user": stat.get("zaikan_user", 0),
                    "like_user": stat.get("like_user", 0),
                    "comment_count": stat.get("comment_count", 0),
                    "collection_user": stat.get("collection_user", 0),
                    "praise_money": stat.get("praise_money", 0),
                    "read_subscribe_user": stat.get("read_subscribe_user", 0),
                    "read_delivery_rate": stat.get("read_delivery_rate", 0.0),
                    "read_finish_rate": stat.get("read_finish_rate", 0.0),
                    "read_avg_activetime": stat.get("read_avg_activetime", 0.0),
                })
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fetch WeChat KPI stats")
    parser.add_argument("--days", type=int, default=7, help="Days to look back (default: 7)")
    parser.add_argument("--type", choices=["note", "account", "all"], default="note",
                        help="Data type: note, account, or all (default: note)")
    parser.add_argument("--json", action="store_true", help="Output as JSON (machine-readable)")
    parser.add_argument("--account-id", default=None, help="Account label for output metadata")
    parser.add_argument("--output", default=None, help="Write JSON to file (avoids pipe encoding issues)")
    args = parser.parse_args()

    try:
        appid, secret = get_wechat_credentials()
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    token = _get_access_token(appid, secret)
    results = []

    if args.type in ("account", "all"):
        account_data = collect_account_data(token, args.days)
        results.extend(account_data)

    if args.type in ("note", "all"):
        note_data = collect_note_data(token, args.days)
        results.extend(note_data)

    if args.json:
        output = {
            "account_id": args.account_id or "",
            "query_days": args.days,
            "query_type": args.type,
            "count": len(results),
            "data": results,
        }
        if args.output:
            # 写入文件（避免管道编码问题）
            Path(args.output).write_text(
                json.dumps(output, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"Written to {args.output}", file=sys.stderr)
        else:
            # stdout 输出（仅当 stdout 是 UTF-8 终端时可靠）
            sys.stdout.buffer.write(
                json.dumps(output, ensure_ascii=False, indent=2).encode("utf-8")
            )
            sys.stdout.buffer.write(b"\n")
    else:
        # Human-readable summary
        account_items = [r for r in results if r["type"] in ("user_summary", "user_cumulate")]
        note_items = [r for r in results if r["type"] == "note_detail"]
        print(f"Fetched {len(results)} records ({len(account_items)} account, {len(note_items)} note)")
        for r in results[:20]:
            if r["type"] == "user_summary":
                print(f"  [{r['ref_date']}] +{r['new_user']} -{r['cancel_user']} fans")
            elif r["type"] == "user_cumulate":
                print(f"  [{r['ref_date']}] cumulate={r['cumulate_user']}")
            elif r["type"] == "note_detail":
                print(f"  [{r['stat_date']}] {r['title'][:30]} reads={r['read_user']} likes={r['like_user']}")
        if len(results) > 20:
            print(f"  ... and {len(results) - 20} more records")


if __name__ == "__main__":
    main()
