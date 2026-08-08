"""Streamlit 前端：登录 / BYOK / 上传同步 / 对话（风格保持小红书粉红）。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import httpx
import streamlit as st

# 加载项目根目录 .env
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
except ImportError:
    pass

API_BASE = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")

from branding import LOGO_FILE, inject_global_brand, logo_img_tag
from auth_persist import (
    clear_access_token,
    get_cookie_manager,
    load_access_token,
    save_access_token,
)

st.set_page_config(
    page_title="小红书收藏智能助手",
    page_icon=str(LOGO_FILE),
    layout="wide",
)

inject_global_brand()

st.markdown(
    """
<style>
/* 侧边栏优化：干净的白底 */
section[data-testid="stSidebar"] {
    background: #FFFFFF;
    border-right: 1px solid #F8E5E7;
}
/* 侧边栏标题 */
section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 {
    color: #333333 !important;
    font-weight: 700;
    font-size: 1.2rem;
}
/* 主标题样式 */
.app-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 2px;
}
.xhs-title {
    font-size: 1.8rem;
    margin: 0;
    background: linear-gradient(90deg, #FF2442, #FF6B81);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800;
}
.app-subtitle {
    color: #666666;
    font-size: 0.95rem;
    margin: 6px 0 25px 0;
}
/* 卡片与按钮 */
.stButton button {
    border-radius: 12px;
    border: 1px solid #FFD5DB;
    color: #444;
    background: #FFF;
    font-weight: 600;
    transition: all 0.2s;
}
.stButton button:hover {
    background: #FF2442;
    color: #FFF;
    border-color: #FF2442;
}
/* 聊天气泡 */
[data-testid="stChatMessage"] {
    border-radius: 16px;
    padding: 10px 15px;
    background: #FFFFFF;
    box-shadow: 0 2px 12px rgba(255, 36, 66, 0.03);
    border: 1px solid #F8E5E7;
    margin-bottom: 15px;
}
.trace-box {
    color: #888888;
    font-size: 0.85rem;
    line-height: 1.6;
    background: #FAFAFA;
    border-left: 3px solid #FFD5DB;
    padding: 12px 15px;
    border-radius: 8px;
}
/* 标签胶囊 */
.info-pill {
    display: inline-block;
    background: #FFF0F1;
    border: 1px solid #FFD5DB;
    color: #FF2442;
    border-radius: 999px;
    padding: 4px 12px;
    font-size: 0.85rem;
    margin-right: 8px;
    font-weight: 600;
}
.auth-status-ok {
    text-align: center;
    color: #2e7d32;
    font-size: 0.85rem;
    margin-bottom: 15px;
    font-weight: 500;
}
.auth-status-bad {
    text-align: center;
    color: #c62828;
    font-size: 0.85rem;
    margin-bottom: 15px;
    line-height: 1.5;
}
/* 旋转加载动画 */
@keyframes xhs-spin {
    to { transform: rotate(360deg); }
}
.xhs-loading {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: #FF2442;
    font-size: 0.95rem;
    padding: 6px 0;
    font-weight: 500;
}
.xhs-loading .spinner {
    width: 13px;
    height: 13px;
    border: 2px solid #FFD5DB;
    border-top-color: #FF2442;
    border-radius: 50%;
    animation: xhs-spin 0.7s linear infinite;
    flex-shrink: 0;
}
div[data-testid="stSpinner"] > div, .stSpinner > div {
    animation: xhs-spin 0.7s linear infinite !important;
}
.stApp[data-test-script-state="running"] [data-testid="stAppViewContainer"],
.stApp[data-test-script-state="running"] [data-testid="stChatMessage"] {
    opacity: 1 !important;
    filter: none !important;
}
/* 底部输入区外层白底透明（灰色输入框保持）；白底在 stBottom 的直接子 div */
[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stBottomBlockContainer"] {
    background: transparent !important;
    background-color: transparent !important;
    background-image: none !important;
    box-shadow: none !important;
    border-top: none !important;
}
/* logo span 本身没有设置背景色，理论上天然透明；这里只是双重保险，
   防止 Streamlit 默认主题给 span 加任何背景/阴影 */
.xhs-logo {
    background-color: transparent !important;
    box-shadow: none !important;
    border-radius: 0 !important;
}
</style>
""",
    unsafe_allow_html=True,
)


def _init_state() -> None:
    defaults = {
        "access_token": None,
        "user": None,
        "messages": [],
        "auth_mode": "login",
        "pending_user_text": None,
        "pending_clear_memory": False,
        "chat_epoch": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def show_loading(text: str = "加载中...") -> None:
    st.markdown(
        f'<div class="xhs-loading"><span class="spinner"></span><span>{text}</span></div>',
        unsafe_allow_html=True,
    )


def render_messages() -> None:
    epoch = st.session_state.get("chat_epoch", 0)
    for i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"], avatar="🧑‍💻" if msg["role"] == "user" else "📕"):
            if msg["role"] == "assistant" and msg.get("error"):
                st.error(msg["content"], icon="⚠️")
                if i > 0 and st.session_state.messages[i - 1]["role"] == "user":
                    retry_text = st.session_state.messages[i - 1]["content"]
                    if st.button("🔄 重试这个问题", key=f"retry_{epoch}_{i}"):
                        st.session_state.messages = st.session_state.messages[: i - 1]
                        st.session_state.messages.append(
                            {"role": "user", "content": retry_text}
                        )
                        st.session_state.pending_user_text = retry_text
                        st.session_state.chat_epoch = epoch + 1
                        st.rerun()
            else:
                st.markdown(msg["content"])
                if msg["role"] == "assistant" and msg.get("trace"):
                    render_trace(msg["trace"])


def fetch_assistant_reply(user_text: str) -> dict:
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages[:-1]
        if m["role"] in ("user", "assistant")
    ]
    try:
        resp = api_request(
            "POST",
            "/api/v1/chat",
            json_body={"message": user_text, "history": history},
            timeout=180.0,
        )
        if resp.status_code >= 400:
            detail = (
                resp.json().get("detail", resp.text)
                if resp.headers.get("content-type", "").startswith("application/json")
                else resp.text
            )
            return {"role": "assistant", "content": f"⚠️ {detail}", "trace": "", "error": True}
        data = resp.json()
        return {
            "role": "assistant",
            "content": data.get("final", ""),
            "trace": data.get("trace", ""),
            "error": bool(data.get("error")),
        }
    except Exception as e:
        return {
            "role": "assistant",
            "content": f"⚠️ 请求失败：{e}",
            "trace": "",
            "error": True,
        }


def api_request(
        method: str,
        path: str,
        *,
        json_body: Any = None,
        files: Any = None,
        token: Optional[str] = None,
        timeout: float = 120.0,
) -> httpx.Response:
    headers = {}
    tok = token if token is not None else st.session_state.get("access_token")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    url = f"{API_BASE}{path}"
    # VPN / 系统代理会劫持 127.0.0.1 并返回 502，必须直连本地 API
    return httpx.request(
        method,
        url,
        json=json_body,
        files=files,
        headers=headers,
        timeout=timeout,
        trust_env=False,
    )


def check_api_health() -> tuple[bool, str]:
    try:
        resp = httpx.get(
            f"{API_BASE}/api/v1/health",
            timeout=3.0,
            trust_env=False,
        )
        if resp.status_code == 200:
            return True, "服务器连接正常"
        if resp.status_code == 502:
            return (
                False,
                "HTTP 502：多半是 VPN/代理拦截了本地地址。请确认已运行 start_api.ps1，"
                "并刷新本页（前端已改为直连，不走代理）。",
            )
        return False, f"后端返回 HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)


def render_header(subtitle: str) -> None:
    st.markdown(
        f"""
<div class="app-header">
    <h1 class="xhs-title">小红书收藏智能助手</h1>
</div>
<div class="app-subtitle">{subtitle}</div>
""",
        unsafe_allow_html=True,
    )


def render_trace(trace: str) -> None:
    with st.expander("💭 查看助手的思考过程", expanded=False):
        st.markdown(
            f'<div class="trace-box">{trace.replace(chr(10), "<br>")}</div>',
            unsafe_allow_html=True,
        )


def refresh_me() -> bool:
    try:
        resp = api_request("GET", "/api/v1/me")
        if resp.status_code == 200:
            st.session_state.user = resp.json()
            return True
        st.session_state.access_token = None
        st.session_state.user = None
        return False
    except Exception:
        return False


def page_auth() -> None:
    if "auth_view" not in st.session_state:
        st.session_state.auth_view = "login"  # login | register

    # Streamlit 1.60：主内容区是 stMainBlockContainer（仍带 block-container class）
    # 用 :has(#auth-page-marker) 限定只在登录页生效，避免影响登录后的主界面
    _auth_css = """
<style>
/* ===== 登录页悬浮白卡片（Streamlit 1.60） ===== */
body:has(#auth-page-marker) [data-testid="stMain"],
body:has(#auth-page-marker) .stMain {
    background: transparent !important;
    overflow: visible !important;
}
body:has(#auth-page-marker) [data-testid="stMainBlockContainer"],
body:has(#auth-page-marker) div.stMainBlockContainer,
body:has(#auth-page-marker) div.block-container {
    width: 530px !important;
    max-width: 530px !important;
    min-width: 530px !important;
    margin-left: auto !important;
    margin-right: auto !important;
    margin-top: 10vh !important;
    margin-bottom: 12vh !important;
    padding: 2.0rem 2.6rem 1.0rem 2.6rem !important;
    background: #ffffff !important;
    background-color: #ffffff !important;
    border: none !important;
    border-radius: 20px !important;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.06) !important;
    filter: drop-shadow(0 10px 24px rgba(0, 0, 0, 0.08)) !important;
    transition: box-shadow 0.25s ease, transform 0.25s ease, filter 0.25s ease !important;
    position: relative !important;
    z-index: 2 !important;
}
body:has(#auth-page-marker) [data-testid="stMainBlockContainer"]:hover,
body:has(#auth-page-marker) div.stMainBlockContainer:hover,
body:has(#auth-page-marker) div.block-container:hover {
    box-shadow: 0 14px 36px rgba(0, 0, 0, 0.16), 0 6px 14px rgba(0, 0, 0, 0.08) !important;
    filter: drop-shadow(0 16px 28px rgba(0, 0, 0, 0.12)) !important;
    transform: translateY(-3px) !important;
}
body:has(#auth-page-marker) [data-testid="stForm"] {
    border: none !important;
    background: transparent !important;
}
body:has(#auth-page-marker) [data-testid="stVerticalBlockBorderWrapper"] {
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    padding: 0 !important;
}
body:has(#auth-page-marker) [data-testid="stButton"] > button,
body:has(#auth-page-marker) .stFormSubmitButton > button,
body:has(#auth-page-marker) button[kind="primaryFormSubmit"],
body:has(#auth-page-marker) button[kind="secondaryFormSubmit"] {
    border-radius: 999px !important;
    min-height: 2.55rem !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    border: 1px solid #FFD5DB !important;
    background: #FFFFFF !important;
    color: #444444 !important;
    box-shadow: none !important;
    filter: none !important;
}
body:has(#auth-page-marker) [data-testid="stButton"] > button:hover,
body:has(#auth-page-marker) .stFormSubmitButton > button:hover,
body:has(#auth-page-marker) button[kind="primaryFormSubmit"]:hover,
body:has(#auth-page-marker) button[kind="secondaryFormSubmit"]:hover {
    background: #FF2442 !important;
    color: #FFFFFF !important;
    border-color: #FF2442 !important;
}
body:has(#auth-page-marker) [data-testid="stTextInput"] button,
body:has(#auth-page-marker) [data-testid="stTextInput"] [data-testid="stBaseButton-secondary"] {
    border-radius: 0.5rem !important;
    min-height: unset !important;
    height: 2rem !important;
    width: 2rem !important;
    padding: 0 !important;
    border: none !important;
    background: transparent !important;
    color: rgba(49, 51, 63, 0.6) !important;
    font-weight: 400 !important;
    box-shadow: none !important;
    filter: none !important;
}
body:has(#auth-page-marker) [data-testid="stTextInput"] button:hover {
    background: rgba(151, 166, 195, 0.15) !important;
    color: rgba(49, 51, 63, 0.8) !important;
    border: none !important;
}
.auth-subtitle {
    color: #888888;
    font-size: 0.88rem;
    margin-top: 8px;
}
.auth-inline-tip {
    color: #888888;
    font-size: 0.88rem;
    text-align: right;
    margin: 0;
    padding-top: 0.7rem;
    white-space: nowrap;
    line-height: 1.2;
}
.auth-health {
    text-align: center;
    color: #888888;
    font-size: 0.88rem;
    margin: 14px 0 2px 0;
    font-weight: 400;
}
.auth-health-bad {
    text-align: center;
    color: #888888;
    font-size: 0.88rem;
    margin: 14px 0 2px 0;
    font-weight: 400;
    line-height: 1.45;
}
</style>
<div id="auth-page-marker" style="display:none"></div>
"""
    # 1.60 推荐 st.html 注入样式，比 markdown 更稳
    try:
        st.html(_auth_css)
    except Exception:
        st.markdown(_auth_css, unsafe_allow_html=True)

    ok, health_msg = check_api_health()
    is_login = st.session_state.auth_view == "login"

    st.markdown(
        f"""
<div style="text-align:center;margin-bottom:18px;">
  <div style="line-height:1.2;margin-bottom:8px;">{logo_img_tag("xhs-logo xhs-logo-auth")}</div>
  <div class="xhs-title" style="font-size:1.55rem;">
    小红书智能收藏助手
  </div>
  <div class="auth-subtitle">
    {"登录后即可整理与对话你的专属收藏" if is_login else "创建账号后，用你自己的模型 Key 开始使用"}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    with st.form("auth_form", clear_on_submit=False):
        email = st.text_input("邮箱账号", key="auth_email", placeholder="you@example.com")
        password = st.text_input(
            "密码",
            type="password",
            key="auth_password",
            placeholder="********" if is_login else "至少 6 位密码",
        )
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        submitted = st.form_submit_button(
            "登录" if is_login else "注册",
            use_container_width=True,
        )

    if submitted:
        if not email.strip() or not password:
            st.error("请输入完整的邮箱和密码")
        elif len(password) < 6 and not is_login:
            st.error("为了安全，密码请至少设置 6 位")
        elif not ok:
            st.error("服务暂时未启动，请先运行 start_api.ps1")
        else:
            path = "/api/v1/auth/login" if is_login else "/api/v1/auth/register"
            try:
                resp = api_request(
                    "POST",
                    path,
                    json_body={"email": email.strip(), "password": password},
                    token="",
                )
                if resp.status_code >= 400:
                    detail = (
                        resp.json().get("detail", resp.text)
                        if resp.headers.get("content-type", "").startswith("application/json")
                        else resp.text
                    )
                    st.error(f"验证失败：{detail}")
                else:
                    st.session_state.access_token = resp.json()["access_token"]
                    save_access_token(st.session_state["_cookie_manager"], st.session_state.access_token)
                    refresh_me()
                    st.session_state.messages = []
                    st.rerun()
            except Exception as e:
                st.error(f"网络连接异常：{e}")

    if is_login:
        pad_l, tip_col, btn_col, pad_r = st.columns([0.9, 1.35, 1.15, 0.9])
        with tip_col:
            st.markdown(
                '<p class="auth-inline-tip">还没有账号？</p>',
                unsafe_allow_html=True,
            )
        with btn_col:
            if st.button("立即注册", key="goto_register", use_container_width=True):
                st.session_state.auth_view = "register"
                st.rerun()
    else:
        pad_l, tip_col, btn_col, pad_r = st.columns([0.9, 1.35, 1.15, 0.9])
        with tip_col:
            st.markdown(
                '<p class="auth-inline-tip">已有账号？</p>',
                unsafe_allow_html=True,
            )
        with btn_col:
            if st.button("去登录", key="goto_login", use_container_width=True):
                st.session_state.auth_view = "login"
                st.rerun()

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("使用教程", key="auth_guide", use_container_width=True):
            st.switch_page("pages/1_使用教程.py")
    with c2:
        if st.button("检测后端", key="auth_recheck", use_container_width=True):
            st.rerun()

    if ok:
        st.markdown(
            f'<p class="auth-health">{health_msg}</p>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<p class="auth-health-bad">无法连接服务器 · 请先运行 start_api.ps1</p>',
            unsafe_allow_html=True,
        )

def page_main() -> None:
    user = st.session_state.user or {}

    if st.session_state.pop("pending_clear_memory", False):
        try:
            resp = api_request("POST", "/api/v1/memory/clear", timeout=30.0)
            if resp.status_code == 200:
                st.session_state.memory_clear_notice = "success"
            else:
                st.session_state.memory_clear_notice = "fail"
        except Exception:
            st.session_state.memory_clear_notice = "fail"

    render_header("欢迎回来！设置好大模型并同步收藏后，即可在下方开始对话。")

    notice = st.session_state.pop("memory_clear_notice", None)
    if notice == "success":
        st.success("✅ 记忆已清除，助手将重新认识你！")
        st.toast("✅ 记忆已清除", icon="🧠")
    elif notice == "fail":
        st.error("❌ 清除记忆失败，请稍后重试")

    example_clicked = None
    with st.sidebar:
        st.header("👤 我的账号")
        st.caption(user.get("email", ""))
        try:
            stats_resp = api_request("GET", "/api/v1/stats")
            if stats_resp.status_code == 200:
                stats = stats_resp.json()
                st.markdown(
                    f'<span class="info-pill">📌 已同步收藏笔记 {stats.get("total_items", 0)} 篇</span>'
                    f'<span class="info-pill">🔍 已加载智能索引 {stats.get("vector_index_count", 0)} 条</span>',
                    unsafe_allow_html=True,
                )
                if not stats.get("has_llm_config"):
                    st.warning("⚠️ 你还未配置 AI 大模型，对话功能暂不可用哦。")
        except Exception:
            st.caption("暂无法获取收藏统计数据")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 刷新收藏状态", use_container_width=True):
            # 同步助手上传后点此即可更新统计，无需整页刷新
            refresh_me()
            st.rerun()

        if st.button("🚪 退出登录", use_container_width=True):
            clear_access_token(st.session_state["_cookie_manager"])
            st.session_state.access_token = None
            st.session_state.user = None
            st.session_state.messages = []
            st.rerun()

        st.divider()

        # 面向非技术用户的模型设置
        st.header("🔑 AI 大模型设置")
        st.caption("填入你的模型 API Key 即可开启智能对话，产生费用由该提供商收取。")
        llm_get = api_request("GET", "/api/v1/settings/llm")
        current = llm_get.json() if llm_get.status_code == 200 else {}

        api_key = st.text_input("我的 API Key", type="password", key="byok_key", placeholder="例如：sk-xxxx...")

        # 将难懂的技术参数折叠起来
        with st.expander("⚙️ 高级设置 (非开发者无需修改)"):
            base_url = st.text_input(
                "Base URL",
                value=current.get("base_url") or "https://api-inference.modelscope.cn/v1",
                key="byok_base",
            )
            model_id = st.text_input(
                "Model ID",
                value=current.get("model_id") or "deepseek-ai/DeepSeek-V4-Flash-0731",
                key="byok_model",
            )

        if st.button("💾 保存模型设置", use_container_width=True):
            if not api_key.strip():
                st.error("请填写你的 API Key 哦")
            else:
                resp = api_request(
                    "PUT",
                    "/api/v1/settings/llm",
                    json_body={
                        "api_key": api_key.strip(),
                        "base_url": base_url.strip(),
                        "model_id": model_id.strip(),
                    },
                )
                if resp.status_code >= 400:
                    st.error(resp.json().get("detail", resp.text))
                else:
                    st.success("配置保存成功！")
                    refresh_me()

        st.divider()
        st.header("🔗 我的同步口令")
        st.caption("将这段代码复制到「同步助手」中使用")
        sync_token = user.get("sync_token", "")
        st.code(sync_token or "(暂无)", language=None)
        if st.button("🔄 刷新生成新口令", use_container_width=True):
            resp = api_request("POST", "/api/v1/me/sync-token/regenerate")
            if resp.status_code == 200:
                st.session_state.user = resp.json()
                st.success("新口令已生成！")
                st.rerun()
            else:
                st.error("生成失败，请重试")

        st.info("不知道怎么同步？请点击左上角的 **「使用教程」** 查看图文步骤。")

        st.divider()
        st.header("💡 试试这样问我")
        examples = [
            "给我关于穿搭的帖子",
            "找出点赞超过100的",
            "要美食类且点赞大于50的",
            "总结一下我的偏好",
            "找找有清冷感的帖子",
            "显示标签为旅行的所有帖子",
        ]
        for i, ex in enumerate(examples):
            if st.button(ex, key=f"example_{i}", use_container_width=True):
                example_clicked = ex

        st.divider()
        if st.button("🧠 让助手忘记我的偏好 (清除记忆)", use_container_width=True):
            st.session_state.messages = []
            st.session_state.pending_user_text = None
            st.session_state.pending_clear_memory = True
            st.session_state.chat_epoch = int(st.session_state.get("chat_epoch", 0)) + 1
            st.rerun()

        # 针对开发者的功能折叠隐藏
        with st.expander("🛠️ 收藏夹增量更新"):
            st.caption("本机一键拉取 (要求后端与Chrome在同一台电脑)")
            xhs_id = st.text_input("小红书用户 ID", key="xhs_user_id_input")
            num_notes = st.number_input("帖子数量", min_value=1, max_value=500, value=20, step=5)
            if st.button("🚀 本机拉取更新", use_container_width=True):
                if not str(xhs_id).strip():
                    st.error("请输入小红书用户 ID")
                else:
                    status = st.empty()
                    with status.container():
                        show_loading("正在同步收藏，这可能需要一点时间…")
                    resp = api_request(
                        "POST",
                        "/api/v1/sync/local-socai",
                        json_body={"xhs_user_id": str(xhs_id).strip(), "num_notes": int(num_notes)},
                        timeout=300.0,
                    )
                    status.empty()
                    if resp.status_code >= 400:
                        st.error(resp.json().get("detail", resp.text))
                    else:
                        data = resp.json()
                        st.success(
                            f"同步完成：新增 {data.get('new_items', 0)} 篇，合计 {data.get('total_items', 0)} 篇"
                        )

    # 聊天区域
    prompt = st.chat_input("输入你的问题，例如：帮我找找关于探店的帖子...")

    render_messages()

    def _complete_assistant(user_text: str) -> None:
        with st.chat_message("assistant", avatar="📕"):
            placeholder = st.empty()
            with placeholder:
                show_loading("助手正在努力思考中…")
            reply = fetch_assistant_reply(user_text)
            placeholder.empty()
            if reply.get("error"):
                st.error(reply["content"], icon="⚠️")
            else:
                st.markdown(reply["content"])
                if reply.get("trace"):
                    render_trace(reply["trace"])
        st.session_state.messages.append(reply)

    pending_text = st.session_state.pop("pending_user_text", None)
    if pending_text:
        _complete_assistant(pending_text)
        st.rerun()

    new_text = (example_clicked or prompt or "").strip()
    if new_text:
        st.session_state.messages.append({"role": "user", "content": new_text})
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(new_text)
        _complete_assistant(new_text)
        st.rerun()

    st.divider()
    if st.button("🗑️ 清空当前对话记录", use_container_width=False):
        st.session_state.messages = []
        st.session_state.pending_user_text = None
        st.session_state.chat_epoch = int(st.session_state.get("chat_epoch", 0)) + 1
        st.rerun()


_init_state()

# Cookie 持久化登录（刷新页面保持登录）
_cookie_manager = get_cookie_manager()
st.session_state["_cookie_manager"] = _cookie_manager
_saved_token = load_access_token(_cookie_manager)
if _saved_token and not st.session_state.access_token:
    st.session_state.access_token = _saved_token

if st.session_state.access_token and not st.session_state.user:
    refresh_me()
    # 仅当 token 被判定失效时才清 Cookie；网络抖动不要踢登录
    if not st.session_state.access_token:
        clear_access_token(_cookie_manager)

if not st.session_state.access_token or not st.session_state.user:
    page_auth()
else:
    page_main()