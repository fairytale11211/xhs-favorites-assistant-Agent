"""完整使用教程（面向非技术用户，无需登录即可查看）。"""

from __future__ import annotations
import sys
from pathlib import Path

import streamlit as st

# 保证可从 pages/ 导入项目根目录模块
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from branding import LOGO_FILE, inject_global_brand, logo_img_tag

PACK_NAME = "xhs-favorites-sync-windows.zip"
# 百度网盘分享（同步助手安装包）
BAIDU_PAN_URL = "https://pan.baidu.com/s/1tUe7t47GCCYXmC9lIV-CJA?pwd=xhs1"
BAIDU_PAN_CODE = "xhs1"

st.set_page_config(
    page_title="使用教程 · 小红书收藏智能助手",
    page_icon=str(LOGO_FILE),
    layout="wide",
)

inject_global_brand()

st.markdown(
    """
<style>
* { transition: none !important; animation: none !important; }
.xhs-title {
    font-size: 2rem;
    margin: 0;
    background: linear-gradient(90deg, #FF2442, #FF6B81);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800;
    padding-bottom: 5px;
}
.guide-sub {
    color: #666666;
    font-size: 1.05rem;
    margin: 8px 0 25px 0;
    line-height: 1.6;
}
.dl-box {
    background: #FFFFFF;
    border: 1px solid #F8E5E7;
    border-radius: 16px;
    padding: 20px;
    margin: 15px 0 25px 0;
    box-shadow: 0 4px 16px rgba(255, 36, 66, 0.04);
}
.dl-box a {
    color: #FF2442;
    font-weight: 700;
    text-decoration: none;
    word-break: break-all;
}
.dl-box a:hover {
    text-decoration: underline;
}
.tip {
    color: #888;
    font-size: 0.9rem;
    line-height: 1.55;
    background: #FAFAFA;
    padding: 10px;
    border-radius: 8px;
    margin-top: 15px;
}
section[data-testid="stSidebar"] {
    background: #FFFFFF;
    border-right: 1px solid #F8E5E7;
}
.stButton button {
    border-radius: 12px;
    border: 1px solid #FFD5DB;
    color: #FF2442;
    background: #FFF;
    font-weight: 600;
    transition: all 0.2s;
}
.stButton button:hover {
    background: #FF2442;
    color: #FFF;
    border-color: #FF2442;
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    f"""
<div style="display:flex;align-items:center;gap:12px;">
  {logo_img_tag("xhs-logo xhs-logo-header")}
  <h1 class="xhs-title">新手使用教程</h1>
</div>
<div class="guide-sub">
  只需简单几步，即可用对话的方式整理<b>你自己的</b>小红书收藏。<br>
  网站负责聪明的智能检索，你的收藏数据则由电脑上的「同步助手」安全上传。
</div>
""",
    unsafe_allow_html=True,
)

# ---------- 下载区 ----------
st.subheader("① 下载同步助手（第一步必做）")

st.markdown(
    f"""
<div class="dl-box">
  <div style="font-weight:800;color:#333;font-size:1.1rem;margin-bottom:12px;">📦 Windows 同步包（百度网盘下载）</div>
  <div style="margin:8px 0; color: #444;">网盘链接：
    <a href="{BAIDU_PAN_URL}" target="_blank">{BAIDU_PAN_URL}</a>
  </div>
  <div style="margin:8px 0; color: #444;">提取码：<strong style="color:#FF2442; font-size:1.1rem;">{BAIDU_PAN_CODE}</strong></div>
  <div class="tip">
    💡 <b>下载后解压，你会看到三个文件：</b><code>一键同步.bat</code>、<code>sync.py</code>、<code>bin\\socai.exe</code>。稍后我们会用到它们。
  </div>
</div>
""",
    unsafe_allow_html=True,
)

col_a, col_b = st.columns(2)
with col_a:
    st.link_button("⬇️ 去百度网盘下载同步包", BAIDU_PAN_URL, use_container_width=True)
with col_b:
    st.link_button(
        "🐍 去官网下载 Python (若电脑未安装)",
        "https://www.python.org/downloads/",
        use_container_width=True,
    )

st.divider()

# ---------- 步骤 ----------
st.subheader("② 五步轻松上手")

steps = [
    (
        "步骤 1 · 注册并登录本站",
        """
1. 在左侧菜单点击 **「小红书收藏智能助手」** 返回主页。
2. 用邮箱注册一个账号并登录（密码至少 6 位）。
3. 在左侧 **「AI 大模型设置」** 中填入你的 API Key 并保存。
"""
    ),
    (
        "步骤 2 · 获取你的专属同步口令",
        """
1. 登录后，在左侧边栏找到 **「我的同步口令」**。
2. 将那串代码 **整段复制** 下来（一会儿运行助手时要用到）。
"""
    ),
    (
        "步骤 3 · 准备浏览器与小红书账号",
        """
1. 确保电脑已安装 **Google Chrome** 浏览器。
2. 打开 [小红书网页版](https://www.xiaohongshu.com)，**登录你的账号**。
3. 点击你的个人主页，在地址栏找到你的 **小红书用户 ID**：
   - 网址类似：`https://www.xiaohongshu.com/user/profile/xxxxxxxx`
   - 最后的 `xxxxxxxx` 就是你的专属 ID，请记下它。
"""
    ),
    (
        "步骤 4 · 安装 Python 环境（仅需一次）",
        """
1. 点击上方的「去官网下载 Python」按钮。
2. **⚠️ 极其重要：** 安装界面的底部，务必勾选 **Add python.exe to PATH**（添加至环境变量）。
3. 一路点击 Next 完成安装即可关闭窗口。
"""
    ),
    (
        "步骤 5 · 运行同步助手，魔法开始",
        f"""
1. 找到刚下载并解压的同步包文件夹。
2. 双击运行 **`一键同步.bat`**。
3. 按照黑框提示，依次粘贴或输入：
   - 网站地址（本机默认直接回车即可，或输入 `http://127.0.0.1:8000`）
   - 同步口令（步骤 2 复制的代码）
   - 小红书用户 ID（步骤 3 找到的 ID）
   - 同步条数（建议第一次先填 20 试试水）
4. 等待提示「上传成功」。回到本站刷新页面，即可开始体验智能对话！
"""
    ),
]

for title, body in steps:
    with st.expander(f"✨ {title}", expanded=True):
        st.markdown(body)

st.divider()

st.subheader("③ 你可以这样向助手提问")
st.info(
    """
- 「给我推荐几篇关于秋季穿搭的帖子」
- 「帮我找找点赞超过 100 的高赞笔记」
- 「我收藏过有清冷感氛围的帖子吗？」
- 「总结一下我最近收藏偏好是什么？」
- 「把带有“旅行”标签的帖子都列出来」
    """
)

st.divider()

st.subheader("④ 遇到问题看这里")
with st.expander("❓ 百度网盘打不开 / 找不到文件"):
    st.markdown("请使用电脑浏览器打开网盘；如果提示需要登录，请用百度账号登录后再点击下载。")
with st.expander("❓ 双击一键同步后提示找不到 Python"):
    st.markdown("这是因为安装 Python 时忘记勾选 **Add to PATH**。请重新运行 Python 安装包，选择 Modify 或卸载重装并勾选该选项，安装后**重新打开**同步窗口。")
with st.expander("❓ 数据存在哪里？安不安全？"):
    st.markdown(
        """
- 你的收藏内容仅按照你的账号隔离存储，非常安全。
- 你的小红书密码**绝对不会**被上传，登录过程全在你自己的 Chrome 浏览器中完成。
- 对话使用的模型也是你自己的 Key，数据流转透明。
        """
    )

st.caption("需要进一步帮助时，请回到主页登录后直接与助手对话，或联系站点管理员。")