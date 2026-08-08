import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.config import DATABASE_URL, USERS_DIR


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    db_path = Path(DATABASE_URL)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    USERS_DIR.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                sync_token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                llm_config_encrypted TEXT,
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )


@contextmanager
def get_connection():
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_user(email: str, password_hash: str) -> dict[str, Any]:
    sync_token = secrets.token_urlsafe(32)
    created_at = _utc_now()
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, sync_token, created_at) VALUES (?, ?, ?, ?)",
            (email.lower().strip(), password_hash, sync_token, created_at),
        )
        user_id = cur.lastrowid
        conn.execute(
            "INSERT INTO user_settings (user_id, llm_config_encrypted, updated_at) VALUES (?, NULL, ?)",
            (user_id, created_at),
        )
    return get_user_by_id(user_id)


def get_user_by_email(email: str) -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email.lower().strip(),),
        ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_by_sync_token(sync_token: str) -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE sync_token = ?",
            (sync_token,),
        ).fetchone()
    return dict(row) if row else None


def regenerate_sync_token(user_id: int) -> str:
    new_token = secrets.token_urlsafe(32)
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET sync_token = ? WHERE id = ?",
            (new_token, user_id),
        )
    return new_token


def get_user_settings(user_id: int) -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM user_settings WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def save_llm_config(user_id: int, encrypted_config: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_settings (user_id, llm_config_encrypted, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                llm_config_encrypted = excluded.llm_config_encrypted,
                updated_at = excluded.updated_at
            """,
            (user_id, encrypted_config, _utc_now()),
        )


def get_user_data_dir(user_id: int) -> Path:
    path = USERS_DIR / str(user_id)
    path.mkdir(parents=True, exist_ok=True)
    return path
