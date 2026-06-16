"""为每个任务构建一个独立的工作区。

布局（symlink 只读 skill 代码，可写文件单独生成）：

    <workspace>/
    ├── SKILL.md          -> 仓库根（symlink）
    ├── toolkit/          -> 仓库根（symlink）
    ├── scripts/          -> 仓库根（symlink）
    ├── references/       -> 仓库根（symlink）
    ├── personas/         -> 仓库根（symlink）
    ├── .venv/            -> 预建的工具链 venv（symlink，若有）
    ├── style.yaml        风格/人格/主题（本任务可写）
    ├── config.yaml       兜底配置（密钥主要走环境变量）
    ├── history.yaml      去重历史（空起步）
    └── output/           文章产物落地处

skill 里的 `{skill_dir}` 即此工作区根目录（= Agent 的 cwd）。
机密（微信 appid/secret、平台图片 key）通过环境变量传给 Agent 进程，
toolkit/config.py 的 env 覆盖机制会读取它们，因此不依赖 config.yaml 的物理位置。
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Optional

import yaml

from .config import Settings
from .store import Account

# 从仓库根 symlink 进工作区的只读条目
_LINK_ENTRIES = ["SKILL.md", "VERSION", "toolkit", "scripts", "references", "personas"]


def build_workspace(settings: Settings, account: Account, *, theme: str, persona: str) -> Path:
    root = settings.workspace_root
    base = str(root) if root else None
    if base:
        Path(base).mkdir(parents=True, exist_ok=True)
    ws = Path(tempfile.mkdtemp(prefix="wewrite-job-", dir=base))

    skill_dir = settings.skill_dir
    for name in _LINK_ENTRIES:
        src = skill_dir / name
        if src.exists():
            (ws / name).symlink_to(src)

    # 预建的工具链 venv（含仓库根 requirements.txt 依赖）。
    # SKILL.md 约定：python3 优先解析为 {skill_dir}/.venv/bin/python3（若存在）。
    venv = skill_dir / ".venv"
    if venv.exists():
        (ws / ".venv").symlink_to(venv)

    (ws / "output").mkdir()
    (ws / "history.yaml").write_text("articles: []\n", encoding="utf-8")

    _write_style(ws, account, theme=theme, persona=persona)
    _write_config(ws, settings, account, theme=theme)
    return ws


def _write_style(ws: Path, account: Account, *, theme: str, persona: str) -> None:
    style = {
        "account_name": account.account_name or "我的公众号",
        "writing_persona": persona,
        "theme": theme,
    }
    if account.audience:
        style["audience"] = account.audience
    if account.tone:
        style["tone"] = account.tone
    (ws / "style.yaml").write_text(
        yaml.safe_dump(style, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def _write_config(ws: Path, settings: Settings, account: Account, *, theme: str) -> None:
    """兜底 config.yaml。机密主要走 env；此处写入非敏感默认值 + 可选 image 段。"""
    cfg: dict = {"theme": theme}
    image = settings.image_config()
    if image:
        cfg["image"] = image
    (ws / "config.yaml").write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def agent_env(settings: Settings, account: Account, *, theme: str) -> dict[str, str]:
    """传给 Agent 进程的环境变量 —— toolkit 的 env 覆盖会读取它们。"""
    from .security import decrypt

    env: dict[str, str] = {}
    if settings.anthropic_api_key:
        env["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

    # 平台图片密钥池：provider 与 key 必须成对注入。
    # 若只注入 provider 而 key 为空，Step 1 会误判 skip_image_gen=false，
    # 直到 Step 6 才发现没法生成 —— 与 _write_config 一样用 image_config() gate 保持一致。
    if settings.image_config():
        env["WEWRITE_IMAGE_PROVIDER"] = settings.image_provider
        env["WEWRITE_IMAGE_API_KEY"] = settings.image_api_key
    if theme:
        env["WEWRITE_THEME"] = theme

    # 用户绑定的微信凭证（解密后注入进程环境，不落盘明文）
    if account.wechat_bound:
        env["WECHAT_APPID"] = decrypt(account.wechat_appid_enc)  # type: ignore[arg-type]
        env["WECHAT_SECRET"] = decrypt(account.wechat_secret_enc)  # type: ignore[arg-type]
        if account.wechat_author:
            env["WECHAT_AUTHOR"] = account.wechat_author
    return env


def cleanup_workspace(ws: Optional[Path]) -> None:
    if ws and ws.exists():
        shutil.rmtree(ws, ignore_errors=True)
