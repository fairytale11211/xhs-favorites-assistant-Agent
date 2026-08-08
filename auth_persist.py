"""登录状态持久化：用浏览器 Cookie 记住 JWT，刷新页面无需重新登录。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import streamlit as st

COOKIE_NAME = "xhs_access_token"
COOKIE_DAYS = 7


def get_cookie_manager():
    """CookieManager 必须在每次脚本运行时无路径调用一次。"""
    import extra_streamlit_components as stx

    return stx.CookieManager(key="xhs_auth_cookies")


def save_access_token(cookie_manager, token: str) -> None:
    if not token:
        return
    cookie_manager.set(
        COOKIE_NAME,
        token,
        expires_at=datetime.now() + timedelta(days=COOKIE_DAYS),
        same_site="lax",
    )


def clear_access_token(cookie_manager) -> None:
    try:
        cookie_manager.delete(COOKIE_NAME)
    except Exception:
        # 部分环境下 delete 失败时用空值覆盖
        cookie_manager.set(
            COOKIE_NAME,
            "",
            expires_at=datetime.now() - timedelta(days=1),
            same_site="lax",
        )


def load_access_token(cookie_manager) -> Optional[str]:
    """从 Cookie 读取 token；组件首次挂载时可能返回 None，随后会自动 rerun。"""
    try:
        value = cookie_manager.get(COOKIE_NAME)
    except Exception:
        return None
    if not value or not str(value).strip():
        return None
    return str(value).strip()
