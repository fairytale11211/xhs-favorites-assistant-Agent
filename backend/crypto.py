import base64
import hashlib
import json
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken

from backend.config import ENCRYPTION_KEY


def _derive_fernet_key(raw_key: str) -> bytes:
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_derive_fernet_key(ENCRYPTION_KEY))


def encrypt_value(value: str) -> str:
    return _fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_value(token: str) -> str:
    try:
        return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt value") from exc


def encrypt_llm_config(api_key: str, base_url: str, model_id: str) -> str:
    payload = {"api_key": api_key, "base_url": base_url, "model_id": model_id}
    return encrypt_value(json.dumps(payload, ensure_ascii=False))


def decrypt_llm_config(token: Optional[str]) -> Optional[dict[str, str]]:
    if not token:
        return None
    try:
        data = json.loads(decrypt_value(token))
        if not data.get("api_key"):
            return None
        return {
            "api_key": data["api_key"],
            "base_url": data.get("base_url") or "",
            "model_id": data.get("model_id") or "",
        }
    except (ValueError, json.JSONDecodeError):
        return None
