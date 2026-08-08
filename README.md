# 小红书收藏智能助手（多用户版）

用 **网站账号 + BYOK（自备模型 Key）** 整理每个人自己的小红书收藏。  
抓取在用户本机完成：下载 **socai 同步包** → 双击同步 → 上传到网站（含正文 / OCR / 评论）。

面向最终用户的图文说明见前端左侧菜单 **「使用教程」**。

**同步助手下载（百度网盘）**  
文件：`xhs-favorites-sync-windows.zip`  
链接：https://pan.baidu.com/s/1tUe7t47GCCYXmC9lIV-CJA?pwd=xhs1  
提取码：`xhs1`

---

## 架构一览

```
用户浏览器 (Streamlit：主页 + 使用教程)
        │  JWT
        ▼
FastAPI (backend/main.py)
  · 注册登录 / BYOK 加密 / 同步令牌
  · 对话 Agent / 向量索引
  · /downloads 提供同步包下载
        ▲
本机 socai/ 同步包（一键同步.bat）──POST /api/v1/sync──┘
（Chrome 已登录小红书）
```

---

## 目录说明

| 路径 | 作用 |
|------|------|
| `backend/` | FastAPI API |
| `app.py` / `pages/1_使用教程.py` | 前端主页与教程 |
| `socai/` | **面向用户的精简同步包**（exe + 一键同步脚本） |
| `socai-main/` | 上游完整源码（仅开发编译用，用户无需打开） |
| `downloads/` | 网站可下载的 zip（由打包脚本生成） |
| `scripts/build_socai_pack.ps1` | 把 `socai.exe` 打进 `socai/bin` 并生成 zip |
| `collection_service.py` / `agent_service.py` 等 | 检索与 Agent |

---

## 环境准备（运维 / 开发）

1. Python 3.10+，建议使用项目 `venv`
2. 本地模型：`all-MiniLM-L6-v2/`、`bge-reranker-base/`
3. 编译或准备 `socai-main/target/release/socai.exe`，再打包：

```powershell
.\scripts\build_socai_pack.ps1
```

会生成：

- `socai/bin/socai.exe`
- `downloads/xhs-favorites-sync-windows.zip`（教程页下载链接指向此处）

4. 配置环境：

```powershell
copy .env.example .env
# 至少修改 SECRET_KEY
pip install -r requirements.txt
```

---

## 启动

> 注册/登录依赖后端。若 `WinError 10061`，说明 API 未启动。

**终端 1 — API：**

```powershell
.\start_api.ps1
```

**终端 2 — 前端：**

```powershell
.\start_web.ps1
```

- 健康检查：`http://127.0.0.1:8000/api/v1/health`
- 同步包下载：`http://127.0.0.1:8000/downloads/xhs-favorites-sync-windows.zip`
- Swagger：`http://127.0.0.1:8000/docs`

---

## 最终用户怎么用

1. 打开网站 → 左侧 **「使用教程」**（含下载链接）
2. 下载 Windows 同步包并解压
3. 主页注册登录 → 配置 BYOK → 复制同步令牌
4. Chrome 登录小红书
5. 双击 `一键同步.bat`，按提示填写
6. 回到主页对话检索

开发机若 API 与 Chrome 同机，也可用侧边栏「本机拉取更新」。公网多用户部署请让用户各自跑同步包。

---

## 主要 API

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| POST | `/api/v1/auth/register` | 无 | 注册 |
| POST | `/api/v1/auth/login` | 无 | 登录 → JWT |
| GET | `/api/v1/me` | JWT | 当前用户（含 sync_token） |
| PUT | `/api/v1/settings/llm` | JWT | 保存 BYOK |
| POST | `/api/v1/chat` | JWT | 对话 |
| POST | `/api/v1/sync` | sync_token | 本机同步上传 |
| GET | `/downloads/*` | 无 | 同步包静态下载 |
| GET | `/api/v1/downloads` | 无 | 列出可下载文件 |

---

## 数据落盘

```
data/
  app.db
  users/<user_id>/
    items.json
    chroma_storage/
    memory.json
```

---

## 许可证说明

- 网站与同步脚本：本项目自有代码
- `socai/bin/socai.exe`：基于 [socai](https://github.com/socai-io/socai)（Apache-2.0），见 `socai/NOTICE.txt`
