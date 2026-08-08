"""
兼容入口：旧的单机 sort.py 已拆分为多用户模块。

- 多用户服务请使用：uvicorn backend.main:app + streamlit run app.py
- 本机 CLI 调试仍可：python sort.py（需配置环境变量 LLM）
"""

from __future__ import annotations

import os
from pathlib import Path

from agent_service import ask_agent as _ask_agent
from agent_service import get_service_for_user
from backend.config import DEFAULT_LLM_BASE_URL, DEFAULT_LLM_MODEL_ID
from backend.database import get_user_data_dir, init_db
from collection_service import CollectionService
from socai_sync import refresh_data_from_socai as _refresh_data_from_socai

# 本地开发默认用户目录（不经过注册时）
_LOCAL_USER_ID = 0
_LOCAL_DIR = Path(os.getenv("DATA_DIR", "data")) / "users" / "local"


def _local_llm_config() -> dict:
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "请设置环境变量 LLM_API_KEY（BYOK）。"
            "多用户场景请使用网站注册后在侧边栏填写 Key。"
        )
    return {
        "api_key": api_key,
        "base_url": os.getenv("LLM_BASE_URL", DEFAULT_LLM_BASE_URL),
        "model_id": os.getenv("LLM_MODEL_ID", DEFAULT_LLM_MODEL_ID),
    }


def _local_service() -> CollectionService:
    _LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    # 若本地还没有 items，尝试从旧的 final_with_details_updated.json 导入一次
    items_file = _LOCAL_DIR / "items.json"
    legacy = Path("final_with_details_updated.json")
    if not items_file.exists() and legacy.exists():
        import json
        import shutil

        with open(legacy, "r", encoding="utf-8") as f:
            data = json.load(f)
        with open(items_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"📦 已从 {legacy} 导入到 {_LOCAL_DIR}")
    return CollectionService("local", _LOCAL_DIR, _local_llm_config())


def ask_agent(user_input: str, history: list = None):
    service = _local_service()
    return _ask_agent(user_input, service, _local_llm_config(), history=history)


def clear_memory():
    return _local_service().clear_memory()


def refresh_data_from_socai(user_id: str, num_notes: int = 10, llm_ocr_filter: bool = False) -> int:
    """兼容旧签名：user_id 这里是小红书 profile id。"""
    return _refresh_data_from_socai(
        user_id="local",
        xhs_user_id=user_id,
        num_notes=num_notes,
        llm_config=_local_llm_config() if llm_ocr_filter else None,
        data_dir=_LOCAL_DIR,
        llm_ocr_filter=llm_ocr_filter,
    )


def run_cli():
    print("\n🤖 小红书收藏助手（本地 CLI / 兼容模式）")
    print("  - 多用户网站请用：uvicorn backend.main:app 与 streamlit run app.py")
    print("  - 本模式需要环境变量 LLM_API_KEY")
    print("输入 '退出' 结束。\n")
    while True:
        user_input = input("👤 你: ").strip()
        if user_input.lower() in ["退出", "exit", "quit"]:
            print("👋 再见！")
            break
        if user_input.lower().startswith("fetch"):
            parts = user_input.split()
            if len(parts) < 2:
                print("⚠️ 用法: fetch <小红书用户ID> [帖子数量]")
                continue
            xhs_id = parts[1]
            num = int(parts[2]) if len(parts) > 2 else 10
            try:
                count = refresh_data_from_socai(xhs_id, num)
                print(f"✅ 已更新 {count} 条")
            except Exception as e:
                print(f"❌ {e}")
            continue
        result = ask_agent(user_input)
        print(f"\n✅ {result['final']}\n💭 {result['trace']}\n" + "-" * 40)


if __name__ == "__main__":
    run_cli()
