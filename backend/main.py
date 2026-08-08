"""FastAPI 入口：注册登录、BYOK、同步上传、对话。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# 保证项目根目录可 import collection_service / agent_service
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_service import ask_agent, get_service_for_user
from backend.auth import (
    create_access_token,
    get_current_user,
    get_sync_user,
    hash_password,
    verify_password,
)
from backend.config import DEFAULT_LLM_BASE_URL, DEFAULT_LLM_MODEL_ID, DOWNLOADS_DIR
from backend.crypto import decrypt_llm_config, encrypt_llm_config
from backend.database import (
    create_user,
    get_user_by_email,
    get_user_settings,
    init_db,
    regenerate_sync_token,
    save_llm_config,
)
from backend.models import (
    ChatRequest,
    ChatResponse,
    LLMSettingsRequest,
    LLMSettingsResponse,
    LoginRequest,
    RegisterRequest,
    StatsResponse,
    SyncResponse,
    TokenResponse,
    UserResponse,
)
from llm_client import LLMCallError, verify_llm_config

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="小红书收藏智能助手 API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 面向用户的同步包下载（zip / 说明文件）
app.mount("/downloads", StaticFiles(directory=str(DOWNLOADS_DIR)), name="downloads")


@app.get("/api/v1/downloads")
def list_downloads() -> dict[str, Any]:
    """列出可供下载的同步包文件。"""
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for p in sorted(DOWNLOADS_DIR.iterdir()):
        if not p.is_file() or p.name.startswith("."):
            continue
        # 教程页主要展示同步包；说明类 md 不列入下载清单
        if p.suffix.lower() not in {".zip", ".exe", ".bat"}:
            continue
        files.append(
            {
                "name": p.name,
                "size_bytes": p.stat().st_size,
                "url": f"/downloads/{p.name}",
            }
        )
    return {"files": files}


@app.get("/api/v1/downloads/{filename}")
def download_file(filename: str):
    """带 Content-Disposition 的下载（适合浏览器另存为）。"""
    safe = Path(filename).name
    path = DOWNLOADS_DIR / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在，请先运行 scripts/build_socai_pack.ps1")
    return FileResponse(path, filename=safe, media_type="application/octet-stream")



def _has_llm(user_id: int) -> bool:
    settings = get_user_settings(user_id)
    if not settings:
        return False
    return decrypt_llm_config(settings.get("llm_config_encrypted")) is not None


def _require_llm_config(user_id: int) -> dict[str, str]:
    settings = get_user_settings(user_id)
    cfg = decrypt_llm_config(settings.get("llm_config_encrypted") if settings else None)
    if not cfg:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先在设置中配置 BYOK（API Key）",
        )
    if not cfg.get("base_url"):
        cfg["base_url"] = DEFAULT_LLM_BASE_URL
    if not cfg.get("model_id"):
        cfg["model_id"] = DEFAULT_LLM_MODEL_ID
    return cfg


def _user_response(user: dict[str, Any]) -> UserResponse:
    return UserResponse(
        id=user["id"],
        email=user["email"],
        has_llm_config=_has_llm(user["id"]),
        sync_token=user["sync_token"],
    )


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/auth/register", response_model=TokenResponse)
def register(body: RegisterRequest) -> TokenResponse:
    if get_user_by_email(body.email):
        raise HTTPException(status_code=400, detail="该邮箱已注册")
    user = create_user(body.email, hash_password(body.password))
    token = create_access_token(user["id"], user["email"])
    return TokenResponse(access_token=token)


@app.post("/api/v1/auth/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    user = get_user_by_email(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    token = create_access_token(user["id"], user["email"])
    return TokenResponse(access_token=token)


@app.get("/api/v1/me", response_model=UserResponse)
def me(user: dict = Depends(get_current_user)) -> UserResponse:
    return _user_response(user)


@app.post("/api/v1/me/sync-token/regenerate", response_model=UserResponse)
def regenerate_token(user: dict = Depends(get_current_user)) -> UserResponse:
    new_token = regenerate_sync_token(user["id"])
    user = {**user, "sync_token": new_token}
    return _user_response(user)


@app.get("/api/v1/settings/llm", response_model=LLMSettingsResponse)
def get_llm_settings(user: dict = Depends(get_current_user)) -> LLMSettingsResponse:
    settings = get_user_settings(user["id"])
    cfg = decrypt_llm_config(settings.get("llm_config_encrypted") if settings else None)
    if not cfg:
        return LLMSettingsResponse(configured=False)
    return LLMSettingsResponse(
        configured=True,
        base_url=cfg.get("base_url") or DEFAULT_LLM_BASE_URL,
        model_id=cfg.get("model_id") or DEFAULT_LLM_MODEL_ID,
    )


@app.put("/api/v1/settings/llm", response_model=LLMSettingsResponse)
def put_llm_settings(body: LLMSettingsRequest, user: dict = Depends(get_current_user)) -> LLMSettingsResponse:
    base_url = (body.base_url or DEFAULT_LLM_BASE_URL).strip()
    model_id = (body.model_id or DEFAULT_LLM_MODEL_ID).strip()
    encrypted = encrypt_llm_config(body.api_key.strip(), base_url, model_id)
    save_llm_config(user["id"], encrypted)
    # 尽量校验，失败不回滚（用户仍可稍后改 Key）
    try:
        verify_llm_config({"api_key": body.api_key.strip(), "base_url": base_url, "model_id": model_id})
    except LLMCallError:
        pass
    return LLMSettingsResponse(configured=True, base_url=base_url, model_id=model_id)


@app.get("/api/v1/stats", response_model=StatsResponse)
def stats(user: dict = Depends(get_current_user)) -> StatsResponse:
    llm_cfg = None
    try:
        llm_cfg = _require_llm_config(user["id"])
    except HTTPException:
        pass
    service = get_service_for_user(user["id"], llm_cfg)
    s = service.get_stats()
    return StatsResponse(
        total_items=s["total_items"],
        memory_conversations=s["memory_conversations"],
        vector_index_count=s["vector_index_count"],
        has_llm_config=_has_llm(user["id"]),
    )


@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(body: ChatRequest, user: dict = Depends(get_current_user)) -> ChatResponse:
    llm_cfg = _require_llm_config(user["id"])
    service = get_service_for_user(user["id"], llm_cfg)
    if not service.posts:
        return ChatResponse(
            final="你的收藏库还是空的。请先上传扩展导出的 JSON，或使用本机同步助手通过 socai 同步。",
            trace="",
            error=False,
        )
    result = ask_agent(body.message, service, llm_cfg, history=body.history)
    return ChatResponse(
        final=result["final"],
        trace=result.get("trace", ""),
        error=bool(result.get("error")),
        contexts=result.get("contexts", []),
    )


@app.post("/api/v1/memory/clear")
def clear_memory(user: dict = Depends(get_current_user)) -> dict[str, bool]:
    service = get_service_for_user(user["id"])
    ok = service.clear_memory()
    return {"ok": ok}


@app.post("/api/v1/upload", response_model=SyncResponse)
async def upload_json(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> SyncResponse:
    raw = await file.read()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无效的 JSON 文件：{e}") from e
    service = get_service_for_user(user["id"])
    before = len(service.posts)
    result = service.merge_from_payload(payload)
    return SyncResponse(
        merged_count=result["total_items"] - before + result["new_items"],
        total_items=result["total_items"],
        new_items=result["new_items"],
    )


@app.post("/api/v1/sync", response_model=SyncResponse)
async def sync_items(
    payload: dict[str, Any],
    user: dict = Depends(get_sync_user),
) -> SyncResponse:
    """本机同步助手用 sync_token 调用；body 为 {items:[...]} 或扩展/socai 导出结构。"""
    service = get_service_for_user(user["id"])
    before = len(service.posts)
    result = service.merge_from_payload(payload)
    return SyncResponse(
        merged_count=max(result["total_items"] - before, result["new_items"]),
        total_items=result["total_items"],
        new_items=result["new_items"],
    )


@app.post("/api/v1/sync/local-socai", response_model=SyncResponse)
def sync_local_socai(
    body: dict[str, Any],
    user: dict = Depends(get_current_user),
) -> SyncResponse:
    """服务端本机有 socai 时可选：从网站触发 socai（仅适合单机开发/自托管）。"""
    from socai_sync import refresh_data_from_socai

    xhs_user_id = (body.get("xhs_user_id") or "").strip()
    num_notes = int(body.get("num_notes") or 20)
    if not xhs_user_id:
        raise HTTPException(status_code=400, detail="缺少 xhs_user_id")
    llm_cfg = None
    try:
        llm_cfg = _require_llm_config(user["id"])
    except HTTPException:
        pass
    try:
        new_items = refresh_data_from_socai(
            user_id=user["id"],
            xhs_user_id=xhs_user_id,
            num_notes=num_notes,
            llm_config=llm_cfg,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    service = get_service_for_user(user["id"], llm_cfg)
    return SyncResponse(merged_count=new_items, total_items=len(service.posts), new_items=new_items)
