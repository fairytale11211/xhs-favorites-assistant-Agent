# 小红书收藏智能助手

## 1. 项目概述

本项目是一个小红书收藏整理与智能对话Agent：

- **网站账号登录**：每人独立账号，收藏与对话记忆互不串扰
- **BYOK（自备模型 Key）**：在侧边栏填写自己的大模型 API Key，费用由对应服务商结算（如ModelScope）
- **本机同步收藏**：用「同步助手」在你自己的电脑上拉取小红书收藏（含正文/封面OCR/ 热门评论），再上传到网站
- **智能检索对话**：基于混合检索+重排序，用自然语言查找、整理自己的收藏

**同步助手（百度网盘，推荐）**

| 项 | 内容 |
|----|------|
| 文件 | `xhs-favorites-sync-windows.zip` |
| 链接 | https://pan.baidu.com/s/1tUe7t47GCCYXmC9lIV-CJA?pwd=xhs1 |
| 提取码 | `xhs1` |

---

## 2. 目录说明

### 2.1 源码与配置（仓库内）

| 路径 | 说明 |
|------|------|
| `app.py` | Streamlit 主页面（登录、设置、对话） |
| `pages/1_使用教程.py` | 前端「使用教程」页 |
| `backend/` | FastAPI：鉴权、BYOK、同步、对话 API |
| `collection_service.py` / `agent_service.py` / `llm_client.py` / `shared_models.py` | 收藏检索、Agent、模型加载 |
| `branding.py` / `auth_persist.py` / `assets/` | 品牌资源、登录态 Cookie 持久化 |
| `socai_sync.py` / `sort.py` / `sync_client/` | 本机同步相关辅助脚本 |
| `scripts/build_socai_pack.ps1` | 打包同步助手 zip（开发用） |
| `start_api.ps1` / `start_web.ps1` | 一键启动后端 / 前端 |
| `requirements.txt` | Python 依赖 |
| `.env.example` | 环境变量模板（复制为 `.env` 后修改） |


### 2.2 需要自行准备的本地模型

放到**项目根目录**下，名称保持一致（或在 `.env` 里改路径）：

| 路径 | 用途 |
|------|------|
| `all-MiniLM-L6-v2/` | 句向量嵌入模型（检索召回） |
| `bge-reranker-base/` | 重排序模型（提升检索相关性） |

### 2.3 个人数据存储

默认根目录由环境变量 `DATA_DIR` 控制（默认 `./data`）。运行后会自动创建：

```
data/
├── app.db                          # SQLite：用户账号、加密后的 BYOK、同步令牌等
└── users/
    └── <user_id>/                  # 每个注册用户一个目录
        ├── items.json              # 该用户的收藏笔记（同步上传后写入）
        ├── memory.json             # 对话「长期记忆」（助手记住的偏好等）
        ├── synonym_cache.json      # 同义词扩展缓存（检索时自动积累）
        └── chroma_storage/         # Chroma 向量库（该用户收藏的索引）
```

| 文件 / 目录 | 何时产生 | 能否删除 |
|-------------|----------|----------|
| `data/app.db` | 首次启动 API、注册用户时 | 删除等于清空所有账号（慎用） |
| `items.json` | 同步助手上传成功后 | 删除后该用户收藏需重新同步 |
| `memory.json` | 开始对话、写入记忆后 | 可在网站侧边栏「清除记忆」；删文件效果类似 |
| `synonym_cache.json` | 检索触发同义词扩展后 | 可删，下次会重新生成缓存 |
| `chroma_storage/` | 同步或重建索引后 | 可删，下次会按 `items.json` 重建（较慢） |

### 2.4 其它可能出现的本地文件

| 路径 | 说明 |
|------|------|
| `.env` | 本地密钥与配置 |
| `venv/` / `agent/` | Python 虚拟环境 |
| `ocr_judge_cache.json` | 若走本机 socai OCR 评判流程，可能落在对应缓存目录 |
| `~/.socai/runs/` | 同步助手拉取时，socai 在用户主目录写下的运行产物（与网站 `data/` 无关） |

---

## 3. 使用教程

### 3.1 环境准备

**系统要求**

- Windows 10/11
- Python **3.10+**
- Google Chrome（同步时需已登录小红书）
- 建议 8GB+ 内存（本地嵌入 / 重排模型）

**① 获取代码**

```powershell
git clone <你的仓库地址>
cd <项目目录>
```

**② 创建虚拟环境并安装依赖**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**③ 配置环境变量**

```powershell
copy .env.example .env
```

用编辑器打开 `.env`，至少修改：

```env
SECRET_KEY=请换成一串足够长的随机字符
API_URL=http://127.0.0.1:8000
```

**④ 下载本地模型（必做）**

将下列两个模型放到项目**根目录**，文件夹名保持：

- `all-MiniLM-L6-v2/`
- `bge-reranker-base/`

**官方页面 / 下载地址：**

| 模型 | 用途 | 下载地址 |
|------|------|----------|
| all-MiniLM-L6-v2 | 向量检索 | https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2 |
| bge-reranker-base | 结果重排 | https://huggingface.co/BAAI/bge-reranker-base |

若 Hugging Face 访问不便，可用 git 镜像克隆到项目根目录（需已安装 Git，且网络可访问）：

```powershell
# 嵌入模型 → 得到文件夹 all-MiniLM-L6-v2
git clone https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2

# 重排模型 → 得到文件夹 bge-reranker-base
git clone https://huggingface.co/BAAI/bge-reranker-base
```

也可在浏览器打开模型页，用「Files and versions」逐个下载后放进对应文件夹。  
若改存放路径，在 `.env` 中设置：

```env
EMBEDDING_MODEL_PATH=./all-MiniLM-L6-v2
RERANKER_MODEL_PATH=./bge-reranker-base
```

**⑤ 同步助手**

用户无需编译，直接从百度网盘下载解压即可（见文首链接）。

### 3.2 启动服务

开两个终端（均先 `Activate` 虚拟环境）：

**终端 1 — 后端 API**

```powershell
.\start_api.ps1
```

**终端 2 — 前端**

```powershell
.\start_web.ps1
```

- 前端一般在浏览器打开 Streamlit 提示的本地地址（如 `http://localhost:8501`）
- API 健康检查：http://127.0.0.1:8000/api/v1/health  
- API 文档：http://127.0.0.1:8000/docs  

> 若登录报 `WinError 10061` / 连不上后端：说明 API 未启动，或开了 VPN 代理拦截了本地请求。请先运行 `start_api.ps1`；`start_web.ps1` 已尽量绕过本地代理。

### 3.3 最终用户操作流程

1. 打开网站，左侧进入 **「使用教程」**（可按页内说明操作）
2. 从百度网盘下载同步包并解压，确认有 `一键同步.bat`、`sync.py`、`bin\socai.exe`
3. 回到主页：**注册 / 登录** → 侧边栏填写 **API Key** 并保存 → 复制 **同步令牌**
4. 用 Chrome 登录小红书网页版
5. 双击 `一键同步.bat`，按提示填写：网站地址（默认 `http://127.0.0.1:8000`）、同步令牌、小红书用户 ID、条数
6. 等待显示上传成功 → 回到网站，侧边栏点 **「刷新收藏状态」**（或刷新页面；登录态会保持）
7. 在对话框里用自然语言查询自己的收藏

### 3.4 常见问题

| 现象 | 处理 |
|------|------|
| 同步「上传失败 502」 | 多为 VPN/系统代理拦截本机 API；请更新同步包内 `sync.py`（已对 localhost 禁用代理）或临时关闭代理后再传 |
| 找不到模型 / 嵌入报错 | 确认根目录存在 `all-MiniLM-L6-v2`、`bge-reranker-base`，且文件下载完整 |
| 收藏数量不更新 | 同步成功后点侧边栏「刷新收藏状态」 |

---

## 许可证说明

- 网站与同步脚本：本项目代码
- 同步引擎 `socai.exe`：基于 [socai](https://github.com/socai-io/socai)（Apache-2.0）新增了获取收藏夹内容的功能
