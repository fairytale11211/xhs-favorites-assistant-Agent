import json
import os
import re
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Optional

from backend.config import SOCAI_EXE_PATH
from collection_service import CollectionService, ensure_urls_with_token, parse_likes
from llm_client import build_llm_client

SOCAI_RUNS_DIR = os.path.join(os.path.expanduser("~"), ".socai", "runs")
OCR_JUDGE_CACHE_FILE = "ocr_judge_cache.json"


def _get_latest_output_json(exclude_dirs=None):
    if not os.path.exists(SOCAI_RUNS_DIR):
        return None
    exclude_dirs = exclude_dirs or set()
    subdirs = [
        os.path.join(SOCAI_RUNS_DIR, d)
        for d in os.listdir(SOCAI_RUNS_DIR)
        if os.path.isdir(os.path.join(SOCAI_RUNS_DIR, d)) and d not in exclude_dirs
    ]
    if not subdirs:
        return None
    latest_dir = max(subdirs, key=os.path.getmtime)
    output_path = os.path.join(latest_dir, "output.json")
    return output_path if os.path.exists(output_path) else None


def _looks_meaningful_ocr(text: str) -> bool:
    if not text or len(text) < 4:
        return False
    valid_chars = re.findall(r"[\u4e00-\u9fff a-zA-Z0-9]", text)
    if len(valid_chars) / len(text) < 0.5:
        return False
    tokens = text.split()
    if tokens:
        avg_token_len = sum(len(t) for t in tokens) / len(tokens)
        if len(tokens) >= 6 and avg_token_len < 1.6:
            return False
    return True


def _clean_ocr_text(ocr_list):
    if not ocr_list:
        return ""
    raw_text = " ".join([t for t in ocr_list if t and t.strip()])
    raw_text = raw_text.replace("\n", " ").replace("\r", " ")
    raw_text = re.sub(r"\s+", " ", raw_text).strip()
    if not raw_text or not _looks_meaningful_ocr(raw_text):
        return ""
    return raw_text


def _load_ocr_judge_cache(cache_dir: Path):
    path = cache_dir / OCR_JUDGE_CACHE_FILE
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_ocr_judge_cache(cache_dir: Path, cache):
    try:
        with open(cache_dir / OCR_JUDGE_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _text_hash(text: str) -> str:
    import hashlib

    return hashlib.md5(text.encode("utf-8")).hexdigest()


def filter_ocr_texts_with_llm(texts: dict, llm_client, cache_dir: Path, batch_size: int = 20) -> dict:
    cache = _load_ocr_judge_cache(cache_dir)
    results = {}
    to_judge = {}
    for note_id, text in texts.items():
        h = _text_hash(text)
        if h in cache:
            results[note_id] = cache[h]
        else:
            to_judge[note_id] = text
    ids = list(to_judge.keys())
    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i : i + batch_size]
        batch_items = [{"id": nid, "text": to_judge[nid][:200]} for nid in batch_ids]
        prompt = f"""以下是若干条从图片OCR识别出来的文本，请逐条判断每条文本是否"包含有意义、可读的信息"，
输出一个JSON数组，每个元素是 {{"id": "...", "keep": true/false}}，不要输出任何解释。

输入：
{json.dumps(batch_items, ensure_ascii=False)}
"""
        try:
            raw = llm_client._call(
                [
                    {"role": "system", "content": "你只输出一个JSON数组，不输出任何其他内容。"},
                    {"role": "user", "content": prompt},
                ]
            )
            raw = re.sub(r"^```json\s*|\s*```$", "", raw.strip()).strip()
            parsed = json.loads(raw)
            judged = {item["id"]: bool(item.get("keep", False)) for item in parsed if "id" in item}
        except Exception:
            judged = {nid: True for nid in batch_ids}
        for nid in batch_ids:
            keep = judged.get(nid, True)
            results[nid] = keep
            cache[_text_hash(to_judge[nid])] = keep
    _save_ocr_judge_cache(cache_dir, cache)
    return results


def _extract_notes_list(data):
    if isinstance(data, dict):
        raw_notes = data.get("notes", [])
    elif isinstance(data, list):
        raw_notes = data
    else:
        raw_notes = []
    notes = []
    for item in raw_notes:
        entity = item.get("entity", {}) if isinstance(item, dict) else {}
        if not entity:
            entity = item if isinstance(item, dict) else {}
        if entity.get("note_id"):
            notes.append(entity)
    return notes


def _run_socai(xhs_user_id: str, num_notes: int, extra_flags: list, poll_timeout: int = 180, poll_interval: float = 2.0) -> list:
    socai_path = os.getenv("SOCAI_EXE_PATH", SOCAI_EXE_PATH)
    cmd = [socai_path, "xhs", "favorites", xhs_user_id, "--num-notes", str(num_notes), "--pretty"] + extra_flags
    existing_dirs = set()
    if os.path.exists(SOCAI_RUNS_DIR):
        existing_dirs = {d for d in os.listdir(SOCAI_RUNS_DIR) if os.path.isdir(os.path.join(SOCAI_RUNS_DIR, d))}
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
    output_path = None
    start = time.time()
    while time.time() - start < poll_timeout:
        output_path = _get_latest_output_json(exclude_dirs=existing_dirs)
        if output_path:
            break
        if proc.poll() is not None:
            time.sleep(1)
            output_path = _get_latest_output_json(exclude_dirs=existing_dirs)
            if not output_path:
                _, stderr = proc.communicate(timeout=5)
                error_msg = (stderr or "").strip() or "未知错误"
                raise RuntimeError(f"socai 执行失败 (返回码 {proc.returncode}): {error_msg}")
            break
        time.sleep(poll_interval)
    if not output_path:
        proc.kill()
        raise TimeoutError(f"socai 执行超时（{poll_timeout}秒）仍未生成结果文件")
    with open(output_path, "r", encoding="utf-8", errors="ignore") as f:
        data = json.load(f)
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    return _extract_notes_list(data)


def _flatten_top_comments(top_comments, max_comments: int = 5) -> str:
    if not top_comments:
        return ""
    texts = []
    for c in top_comments[:max_comments]:
        if isinstance(c, dict):
            text = c.get("text", "")
        elif isinstance(c, str):
            text = c
        else:
            text = ""
        text = text.strip()
        if text:
            texts.append(text)
    return " / ".join(texts)


def refresh_data_from_socai(
    user_id: int | str,
    xhs_user_id: str,
    num_notes: int = 10,
    llm_config: Optional[dict] = None,
    data_dir: Optional[Path] = None,
    llm_ocr_filter: bool = False,
) -> int:
    socai_path = os.getenv("SOCAI_EXE_PATH", SOCAI_EXE_PATH)
    if not os.path.exists(socai_path):
        raise FileNotFoundError(f"socai 可执行文件不存在: {socai_path}")

    if data_dir is None:
        from backend.database import get_user_data_dir

        data_dir = get_user_data_dir(int(user_id))

    service = CollectionService(user_id, data_dir, llm_config)
    llm_client = build_llm_client(llm_config) if llm_ocr_filter and llm_config else None

    body_notes = _run_socai(xhs_user_id, num_notes, [])
    if not body_notes:
        return 0

    ocr_candidates_for_llm = {}
    cleaned_ocr_by_id = {}
    for entity in body_notes:
        note_id = entity.get("note_id")
        if not note_id:
            continue
        ocr_list = entity.get("ocr_text", "")
        if isinstance(ocr_list, list):
            cleaned = _clean_ocr_text(ocr_list)
        elif isinstance(ocr_list, str):
            raw = re.sub(r"\s+", " ", ocr_list.replace("\n", " ")).strip()
            cleaned = raw if _looks_meaningful_ocr(raw) else ""
        else:
            cleaned = ""
        if cleaned:
            cleaned_ocr_by_id[note_id] = cleaned
            if llm_ocr_filter and llm_client:
                ocr_candidates_for_llm[note_id] = cleaned

    if llm_ocr_filter and llm_client and ocr_candidates_for_llm:
        keep_map = filter_ocr_texts_with_llm(ocr_candidates_for_llm, llm_client, data_dir)
        for note_id, keep in keep_map.items():
            if not keep:
                cleaned_ocr_by_id.pop(note_id, None)

    new_posts = []
    for entity in body_notes:
        note_id = entity.get("note_id")
        if not note_id:
            continue
        title = entity.get("title", "")
        content = entity.get("content", "") or title
        tags = re.findall(r"#([^\s#]+)", content)
        if not tags and "tags" in entity:
            tags = entity.get("tags", [])
        ocr_cleaned = cleaned_ocr_by_id.get(note_id, "")
        if ocr_cleaned:
            content += "\n[封面文字] " + ocr_cleaned
        comments_text = _flatten_top_comments(entity.get("top_comments"))
        if comments_text:
            content += "\n[热门评论] " + comments_text
        likes_str = entity.get("likes", "0")
        url = entity.get("url", "")
        token = entity.get("xsec_token", "")
        if not token and url and "xsec_token=" in url:
            parsed = urllib.parse.urlparse(url)
            query = urllib.parse.parse_qs(parsed.query)
            token = query.get("xsec_token", [""])[0]
        new_posts.append(
            {
                "note_id": note_id,
                "title": title,
                "desc": content,
                "tags": tags,
                "liked_count": likes_str,
                "url": url,
                "xsec_token": token,
                "sources": ["socai"],
                "first_seen_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                "last_seen_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            }
        )

    result = service.merge_items(new_posts)
    return result["new_items"]
