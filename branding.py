"""品牌资源：logo / 右下角背景装饰。"""

from __future__ import annotations

import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
LOGO_FILE = ASSETS / "logo.png"
BG_FILE = ASSETS / "bg-corner.png"


def _data_uri(path: Path) -> str:
    raw = base64.b64encode(path.read_bytes()).decode("ascii")
    suffix = path.suffix.lower().lstrip(".") or "png"
    mime = "image/png" if suffix == "png" else f"image/{suffix}"
    return f"data:{mime};base64,{raw}"


LOGO_URI = _data_uri(LOGO_FILE)
BG_URI = _data_uri(BG_FILE)


def inject_global_brand() -> None:
    """注入 logo 样式 + 右下角置底背景（页面底色层，不挡点击）。"""
    import streamlit as st

    html = f"""
<style>
/* 背景图画在 App 容器底色上 → 真正置底 */
[data-testid="stAppViewContainer"] {{
    background-color: #FFFFFF !important;
    background-image:
        url("{BG_URI}"),
        linear-gradient(180deg, #FFF0F2 0%, #FFFFFF 300px) !important;
    background-repeat: no-repeat, no-repeat !important;
    background-position: right 4px bottom 4px, 0 0 !important;
    background-size: min(250px, 28vw) auto, auto !important;
    background-attachment: fixed, scroll !important;
}}
[data-testid="stAppViewContainer"] > .main,
section.main,
[data-testid="stMain"],
[data-testid="stMainBlockContainer"] {{
    background: transparent !important;
}}
/* logo 用背景图绘制，避免 Streamlit 给 img 加白底 */
.xhs-logo {{
    display: inline-block !important;
    vertical-align: middle;
    flex-shrink: 0;
    background-color: transparent !important;
    background-image: url("{LOGO_URI}") !important;
    background-repeat: no-repeat !important;
    background-position: center !important;
    background-size: contain !important;
    box-shadow: none !important;
    border: none !important;
    border-radius: 0 !important;
}}
/* 与标题（1.8rem）视觉齐平 */
.xhs-logo-header {{
    width: 4.0rem !important;
    height: 4.0rem !important;
}}
.xhs-logo-auth {{
    width: 4rem !important;
    height: 4rem !important;
}}
/* 聊天气泡头像专用尺寸——注意：这个 class 只有在头像也走 .xhs-logo 这套机制时才会生效，
   如果哪里还在用 avatar=str(LOGO_FILE) 直接把文件路径交给 st.chat_message，
   Streamlit 会用它自己的原生头像渲染逻辑，不会应用这个 class，调这里也没用。 */
.xhs-logo-chat {{
    width: 1.6rem !important;
    height: 1.6rem !important;
}}
.app-header {{
    display: flex !important;
    align-items: center !important;
    gap: 12px !important;
}}
[data-testid="stChatMessageAvatar"], 
[data-testid="stChatMessageAvatar"] > div,
[data-testid="stChatMessage"] [data-testid="stImage"] {{
    background: transparent !important;
    background-color: transparent !important;
}}
/* 聊天气泡头像：略缩小，透明底 + contain 避免白边裁切 */
/* 覆盖现有的 [data-testid="stChatMessage"] img 样式，进一步缩小尺寸 */
[data-testid="stChatMessage"] img {{
    width: 1.0rem !important;  /* <- 从 1.4rem 调小到 1.0rem 或更小 */
    height: 1.0rem !important; /* <- 从 1.4rem 调小 */
    object-fit: contain !important;
    background: transparent !important;
    background-color: transparent !important;
    border-radius: 0 !important;
}}
/* 底部对话输入外层白底透明 */
[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stBottomBlockContainer"] {{
    background: transparent !important;
    background-color: transparent !important;
    background-image: none !important;
    box-shadow: none !important;
}}
</style>
"""
    try:
        st.html(html)
    except Exception:
        st.markdown(html, unsafe_allow_html=True)


def logo_img_tag(css_class: str = "xhs-logo xhs-logo-header") -> str:
    # 用 span + CSS 背景，彻底避开 img 白底
    return f'<span class="{css_class}" role="img" aria-label="logo"></span>'
