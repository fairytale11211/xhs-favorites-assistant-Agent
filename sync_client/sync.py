"""
本机同步助手：调用 socai 拉取收藏（含正文/OCR/评论）→ 清洗 → POST 到网站 /api/v1/sync

用法示例：
  set SYNC_TOKEN=你的同步令牌
  set API_URL=http://127.0.0.1:8000
  set SOCAI_EXE_PATH=...\\socai.exe
  python sync_client/sync.py --xhs-user-id 5f16af11... --num-notes 20
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOCAI = ROOT / "socai" / "bin" / "socai.exe"
if not DEFAULT_SOCAI.exists():
    DEFAULT_SOCAI = ROOT / "socai-main" / "target" / "release" / "socai.exe"
SOCAI_RUNS_DIR = Path.home() / ".socai" / "runs"


def get_latest_output_json(exclude_dirs: set[str] | None = None) -> Path | None:
    if not SOCAI_RUNS_DIR.exists():
        return None
    exclude_dirs = exclude_dirs or set()
    subdirs = [
        p for p in SOCAI_RUNS_DIR.iterdir() if p.is_dir() and p.name not in exclude_dirs
    ]
    if not subdirs:
        return None
    latest = max(subdirs, key=lambda p: p.stat().st_mtime)
    out = latest / "output.json"
    return out if out.exists() else None


def extract_notes(data) -> list[dict]:
    if isinstance(data, dict):
        raw = data.get("notes", [])
    elif isinstance(data, list):
        raw = data
    else:
        raw = []
    notes = []
    for item in raw:
        entity = item.get("entity", {}) if isinstance(item, dict) else {}
        if not entity and isinstance(item, dict):
            entity = item
        if entity.get("note_id"):
            notes.append(entity)
    return notes


def looks_meaningful_ocr(text: str) -> bool:
    if not text or len(text) < 4:
        return False
    valid = re.findall(r"[\u4e00-\u9fff a-zA-Z0-9]", text)
    if len(valid) / len(text) < 0.5:
        return False
    tokens = text.split()
    if tokens:
        avg = sum(len(t) for t in tokens) / len(tokens)
        if len(tokens) >= 6 and avg < 1.6:
            return False
    return True


def clean_ocr(ocr_list) -> str:
    if not ocr_list:
        return ""
    if isinstance(ocr_list, list):
        raw = " ".join([t for t in ocr_list if t and str(t).strip()])
    else:
        raw = str(ocr_list)
    raw = re.sub(r"\s+", " ", raw.replace("\n", " ").replace("\r", " ")).strip()
    return raw if looks_meaningful_ocr(raw) else ""


def flatten_comments(top_comments, max_comments: int = 5) -> str:
    if not top_comments:
        return ""
    texts = []
    for c in top_comments[:max_comments]:
        if isinstance(c, dict):
            t = (c.get("text") or "").strip()
        elif isinstance(c, str):
            t = c.strip()
        else:
            t = ""
        if t:
            texts.append(t)
    return " / ".join(texts)


def run_socai(socai_exe: Path, xhs_user_id: str, num_notes: int, timeout: int = 180) -> list[dict]:
    if not socai_exe.exists():
        raise FileNotFoundError(f"socai 不存在: {socai_exe}")
    cmd = [str(socai_exe), "xhs", "favorites", xhs_user_id, "--num-notes", str(num_notes), "--pretty"]
    print("⏳", " ".join(cmd))
    existing = {p.name for p in SOCAI_RUNS_DIR.iterdir() if p.is_dir()} if SOCAI_RUNS_DIR.exists() else set()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
    output_path = None
    start = time.time()
    while time.time() - start < timeout:
        output_path = get_latest_output_json(existing)
        if output_path:
            break
        if proc.poll() is not None:
            time.sleep(1)
            output_path = get_latest_output_json(existing)
            if not output_path:
                _, err = proc.communicate(timeout=5)
                raise RuntimeError(f"socai 失败: {err or proc.returncode}")
            break
        time.sleep(2)
    if not output_path:
        proc.kill()
        raise TimeoutError("socai 超时")
    with open(output_path, "r", encoding="utf-8", errors="ignore") as f:
        data = json.load(f)
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    return extract_notes(data)


def notes_to_items(notes: list[dict]) -> list[dict]:
    items = []
    for entity in notes:
        note_id = entity.get("note_id")
        if not note_id:
            continue
        title = entity.get("title", "")
        content = entity.get("content", "") or title
        tags = re.findall(r"#([^\s#]+)", content)
        if not tags and "tags" in entity:
            tags = entity.get("tags", [])
        ocr = clean_ocr(entity.get("ocr_text", ""))
        if ocr:
            content += "\n[封面文字] " + ocr
        comments = flatten_comments(entity.get("top_comments"))
        if comments:
            content += "\n[热门评论] " + comments
        url = entity.get("url", "")
        token = entity.get("xsec_token", "")
        if not token and url and "xsec_token=" in url:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            token = q.get("xsec_token", [""])[0]
        items.append(
            {
                "note_id": note_id,
                "title": title,
                "desc": content,
                "tags": tags,
                "liked_count": entity.get("likes", "0"),
                "url": url,
                "xsec_token": token,
                "sources": ["socai"],
                "first_seen_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                "last_seen_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            }
        )
    return items


def upload(api_url: str, sync_token: str, items: list[dict]) -> dict:
    url = api_url.rstrip("/") + "/api/v1/sync"
    headers = {"Authorization": f"Bearer {sync_token}"}
    # trust_env=False：忽略系统/VPN 代理，避免访问本机 API 时出现 502
    with httpx.Client(timeout=120.0, trust_env=False) as client:
        resp = client.post(url, headers=headers, json={"items": items})
        if resp.status_code >= 400:
            detail = (resp.text or "").strip()
            if len(detail) > 300:
                detail = detail[:300] + "…"
            raise RuntimeError(f"上传失败 {resp.status_code}: {detail}")
        return resp.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="小红书收藏本机同步助手（socai → 网站）")
    parser.add_argument("--xhs-user-id", required=True, help="小红书个人主页用户 ID")
    parser.add_argument("--num-notes", type=int, default=20)
    parser.add_argument("--api-url", default=os.getenv("API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--sync-token", default=os.getenv("SYNC_TOKEN", ""))
    parser.add_argument(
        "--socai-exe",
        default=os.getenv("SOCAI_EXE_PATH", str(DEFAULT_SOCAI)),
    )
    parser.add_argument("--dry-run", action="store_true", help="只导出本地 JSON，不上传")
    parser.add_argument("--out", default="", help="dry-run 时写出的文件路径")
    args = parser.parse_args()

    if not args.sync_token and not args.dry_run:
        print("❌ 请设置 SYNC_TOKEN 或传 --sync-token（在网站侧边栏复制）", file=sys.stderr)
        return 1

    notes = run_socai(Path(args.socai_exe), args.xhs_user_id, args.num_notes)
    items = notes_to_items(notes)
    print(f"✅ 解析得到 {len(items)} 条")

    if args.dry_run:
        out = Path(args.out or f"sync_export_{int(time.time())}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"items": items, "total_items": len(items)}, f, ensure_ascii=False, indent=2)
        print(f"💾 已写出 {out}")
        return 0

    result = upload(args.api_url, args.sync_token, items)
    print(f"☁️ 上传成功：新增 {result.get('new_items')}，合计 {result.get('total_items')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
