import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# 自动加载项目根目录 .env（若已安装 python-dotenv）
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env", override=False)
except ImportError:
    pass

DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
USERS_DIR = DATA_DIR / "users"

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-use-long-random-string")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))  # 7 days

DATABASE_URL = os.getenv("DATABASE_URL", str(BASE_DIR / "data" / "app.db"))
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", SECRET_KEY[:32].ljust(32, "0"))

# 优先使用面向用户的精简包 socai/bin/socai.exe，否则回退到开发编译产物
_SOCAI_PACK = BASE_DIR / "socai" / "bin" / "socai.exe"
_SOCAI_DEV = BASE_DIR / "socai-main" / "target" / "release" / "socai.exe"
SOCAI_EXE_PATH = os.getenv(
    "SOCAI_EXE_PATH",
    str(_SOCAI_PACK if _SOCAI_PACK.exists() else _SOCAI_DEV),
)
DOWNLOADS_DIR = Path(os.getenv("DOWNLOADS_DIR", str(BASE_DIR / "downloads")))

DEFAULT_LLM_BASE_URL = os.getenv("DEFAULT_LLM_BASE_URL", "https://api-inference.modelscope.cn/v1")
DEFAULT_LLM_MODEL_ID = os.getenv("DEFAULT_LLM_MODEL_ID", "deepseek-ai/DeepSeek-V4-Flash-0731")

EMBEDDING_MODEL_PATH = os.getenv("EMBEDDING_MODEL_PATH", str(BASE_DIR / "all-MiniLM-L6-v2"))
RERANKER_MODEL_PATH = os.getenv("RERANKER_MODEL_PATH", str(BASE_DIR / "bge-reranker-base"))

API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
