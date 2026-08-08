import json
import re
import time
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

import chromadb

from shared_models import (
    LocalEmbeddingFunction,
    RERANK_CANDIDATE_LIMIT,
    get_embedding_model,
    get_reranker,
)

SYNONYM_MAP = {
    "穿搭": ["穿搭", "OOTD", "cleanfit", "搭配", "时尚", "街拍", "ootd", "Cleanfit", "穿衣", "服装"],
    "妆容": ["妆容", "化妆", "美妆", "妆教", "彩妆"],
    "美食": ["美食", "探店", "吃", "餐厅", "下午茶", "甜品", "日料", "咖啡"],
    "旅行": ["旅行", "旅游", "游记", "打卡", "风景", "出行"],
    "家居": ["家居", "家装", "软装", "家具", "收纳", "卧室"],
    "健身": ["健身", "撸铁", "增肌", "减脂", "瑜伽", "帕梅拉"],
    "电影": ["电影", "影评", "导演", "经典影片", "院线"],
    "职场": ["职场", "求职", "面试", "实习", "晋升", "加班"],
}


def parse_likes(likes_str):
    if not likes_str:
        return 0
    if isinstance(likes_str, int):
        return likes_str
    likes_str = str(likes_str).strip()
    if likes_str.endswith("+"):
        likes_str = likes_str[:-1].strip()
    if "万" in likes_str:
        num = float(likes_str.replace("万", "").strip())
        return int(num * 10000)
    if "亿" in likes_str:
        num = float(likes_str.replace("亿", "").strip())
        return int(num * 100000000)
    try:
        return int(float(likes_str))
    except ValueError:
        return 0


def ensure_urls_with_token(items: list[dict]) -> None:
    for item in items:
        token = item.get("xsec_token")
        url = item.get("url", "")
        if token and url and "xsec_token" not in url:
            parsed = urllib.parse.urlparse(url)
            query = urllib.parse.parse_qs(parsed.query)
            query["xsec_token"] = [token]
            new_query = urllib.parse.urlencode(query, doseq=True)
            item["url"] = urllib.parse.urlunparse(
                (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
            )


def normalize_items_payload(data: Any) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        if "items" in data and isinstance(data["items"], list):
            return [item for item in data["items"] if isinstance(item, dict)]
        notes = data.get("notes", [])
        items = []
        for item in notes:
            if isinstance(item, dict):
                entity = item.get("entity", item)
                if isinstance(entity, dict) and entity.get("note_id"):
                    items.append(entity)
        return items
    return []


class CollectionService:
    def __init__(self, user_id: int | str, data_dir: Path, llm_config: Optional[dict[str, str]] = None):
        self.user_id = str(user_id)
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.items_file = self.data_dir / "items.json"
        self.memory_file = self.data_dir / "memory.json"
        self.synonym_cache_file = self.data_dir / "synonym_cache.json"
        self.chroma_dir = self.data_dir / "chroma_storage"
        self.llm_config = llm_config or {}

        self.posts: list[dict] = []
        self._corpus_text_lower: list[str] = []
        self._synonym_cache: dict = {}
        self._collection = None
        self._chroma_client = None

        self.reload()

    def reload(self) -> None:
        self.posts = self.load_items()
        ensure_urls_with_token(self.posts)
        self._corpus_text_lower = [
            (p.get("title", "") + " " + p.get("desc", "") + " " + " ".join(p.get("tags", []))).lower()
            for p in self.posts
        ]
        self._synonym_cache = self._load_synonym_cache()
        self._init_chroma()
        self.build_vector_index()

    def load_items(self) -> list[dict]:
        if not self.items_file.exists():
            self._save_items([])
            return []
        with open(self.items_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("items", []) if isinstance(data, dict) else []

    def _save_items(self, items: list[dict]) -> None:
        payload = {
            "items": items,
            "total_items": len(items),
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        }
        with open(self.items_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def merge_items(self, incoming: list[dict]) -> dict[str, int]:
        merged_by_id = {p.get("note_id"): p for p in self.posts if p.get("note_id")}
        new_count = 0
        for item in incoming:
            note_id = item.get("note_id")
            if not note_id:
                continue
            if note_id in merged_by_id:
                merged_by_id[note_id].update(item)
            else:
                merged_by_id[note_id] = item
                new_count += 1
        self.posts = list(merged_by_id.values())
        ensure_urls_with_token(self.posts)
        self._save_items(self.posts)
        self._corpus_text_lower = [
            (p.get("title", "") + " " + p.get("desc", "") + " " + " ".join(p.get("tags", []))).lower()
            for p in self.posts
        ]
        self.build_vector_index(force=True)
        return {"new_items": new_count, "total_items": len(self.posts)}

    def merge_from_payload(self, payload: Any) -> dict[str, int]:
        return self.merge_items(normalize_items_payload(payload))

    def _init_chroma(self) -> None:
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        self._chroma_client = chromadb.PersistentClient(path=str(self.chroma_dir))
        embedding_fn = LocalEmbeddingFunction()
        collection_name = "favorites"
        try:
            self._collection = self._chroma_client.get_collection(
                name=collection_name, embedding_function=embedding_fn
            )
        except Exception:
            try:
                self._chroma_client.delete_collection(collection_name)
            except Exception:
                pass
            self._collection = self._chroma_client.create_collection(
                name=collection_name, embedding_function=embedding_fn
            )

    def build_vector_index(self, force: bool = False) -> None:
        if self._collection is None:
            self._init_chroma()
        if not force and self._collection.count() == len(self.posts) and len(self.posts) > 0:
            return

        try:
            self._chroma_client.delete_collection("favorites")
        except Exception:
            pass
        embedding_fn = LocalEmbeddingFunction()
        self._collection = self._chroma_client.create_collection(
            name="favorites", embedding_function=embedding_fn
        )

        ids, documents, metadatas = [], [], []
        for idx, post in enumerate(self.posts):
            text = (post.get("title", "") + " " + post.get("desc", "")).strip() or "无正文"
            ids.append(str(idx))
            documents.append(text)
            metadatas.append(
                {
                    "note_id": post.get("note_id", ""),
                    "likes": parse_likes(post.get("liked_count", 0)),
                    "title": post.get("title", ""),
                    "url": post.get("url", ""),
                    "tags": ",".join(post.get("tags", [])),
                    "desc": post.get("desc", "")[:200],
                }
            )
        batch_size = 50
        for i in range(0, len(ids), batch_size):
            self._collection.add(
                ids=ids[i : i + batch_size],
                documents=documents[i : i + batch_size],
                metadatas=metadatas[i : i + batch_size],
            )

    def _term_exists_in_corpus(self, term: str) -> bool:
        term = term.strip().lower()
        if not term:
            return False
        return any(term in text for text in self._corpus_text_lower)

    def _load_synonym_cache(self) -> dict:
        if self.synonym_cache_file.exists():
            try:
                with open(self.synonym_cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_synonym_cache(self) -> None:
        try:
            with open(self.synonym_cache_file, "w", encoding="utf-8") as f:
                json.dump(self._synonym_cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def llm_generate_synonyms(self, concept: str, llm_client, max_terms: int = 6) -> list:
        concept = (concept or "").strip()
        if not concept:
            return []
        cache_key = concept.lower()
        if cache_key in self._synonym_cache:
            return self._synonym_cache[cache_key]

        prompt = f"""你是中文社交媒体（小红书）搜索query改写助手。
给定一个用户搜索词，请生成最多 {max_terms} 个与它语义高度相关、且很可能出现在小红书笔记标题/正文/标签中的同义词、近义词、英文缩写或网络流行说法。

要求：
1. 只输出与"{concept}"强相关的词，不要输出泛泛而谈、容易跑题的宽泛词。
2. 严格只输出一个 JSON 数组，不要输出任何解释、前缀或代码块标记。
3. 数组里不要包含"{concept}"本身。

搜索词：{concept}
"""
        synonyms = []
        try:
            raw = llm_client._call(
                [
                    {"role": "system", "content": "你只输出一个JSON数组，不输出任何其他内容。"},
                    {"role": "user", "content": prompt},
                ]
            )
            raw = re.sub(r"^```json\s*|\s*```$", "", raw.strip()).strip()
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                synonyms = [str(s).strip() for s in parsed if str(s).strip()]
        except Exception:
            synonyms = []

        validated = [s for s in synonyms if self._term_exists_in_corpus(s)]
        if not validated:
            for base, fallback_syns in SYNONYM_MAP.items():
                if cache_key == base.lower() or cache_key in base.lower():
                    validated = [s.lower() for s in fallback_syns if self._term_exists_in_corpus(s)]
                    break

        self._synonym_cache[cache_key] = validated
        self._save_synonym_cache()
        return validated

    def expand_keywords_with_synonyms(self, keyword_str: str, llm_client) -> list:
        if not keyword_str:
            return []
        parts = [p.strip().lower() for p in keyword_str.split(",") if p.strip()]
        if not parts:
            return []
        if len(parts) >= 6:
            return list(dict.fromkeys(parts))
        expanded = list(parts)
        for p in parts:
            expanded.extend(self.llm_generate_synonyms(p, llm_client))
        return list(dict.fromkeys(expanded))

    def _passes_filters(self, post, min_likes=None, max_likes=None, tag=None):
        likes = post.get("likes", 0)
        if min_likes is not None and likes < min_likes:
            return False
        if max_likes is not None and likes > max_likes:
            return False
        if tag:
            post_tags = [t.lower() for t in post.get("tags", [])]
            if tag.lower() not in post_tags:
                return False
        return True

    def rerank_results(self, query: str, candidates: list, top_k: int = None) -> list:
        if not candidates or not query or not query.strip():
            return candidates
        reranker = get_reranker()
        pool = candidates
        if len(pool) > RERANK_CANDIDATE_LIMIT:
            pool = sorted(pool, key=lambda x: x.get("likes", 0), reverse=True)[:RERANK_CANDIDATE_LIMIT]
        pairs = []
        for p in pool:
            doc_text = (p.get("title", "") + " " + p.get("desc", "")).strip()
            pairs.append([query, doc_text if doc_text else p.get("title", "无标题")])
        try:
            scores = reranker.predict(pairs)
        except Exception:
            return sorted(candidates, key=lambda x: x.get("likes", 0), reverse=True)
        for p, score in zip(pool, scores):
            p["_rerank_score"] = float(score)
        ranked = sorted(pool, key=lambda x: x["_rerank_score"], reverse=True)
        if top_k is not None:
            ranked = ranked[:top_k]
        return ranked

    def get_posts_by_keyword(self, keyword=None, min_likes=None, max_likes=None, tag=None, llm_client=None):
        results = []
        keyword_list = []
        if keyword and llm_client:
            keyword_list = self.expand_keywords_with_synonyms(keyword, llm_client)
        elif keyword:
            keyword_list = [p.strip().lower() for p in keyword.split(",") if p.strip()]
        for post in self.posts:
            likes = parse_likes(post.get("liked_count", 0))
            if min_likes is not None and likes < min_likes:
                continue
            if max_likes is not None and likes > max_likes:
                continue
            if tag:
                post_tags = [t.lower() for t in post.get("tags", [])]
                if tag.lower() not in post_tags:
                    continue
            if keyword_list:
                text = (
                    post.get("title", "")
                    + " "
                    + post.get("desc", "")
                    + " "
                    + " ".join(post.get("tags", []))
                ).lower()
                if not any(k in text for k in keyword_list):
                    continue
            results.append(
                {
                    "note_id": post.get("note_id", ""),
                    "title": post.get("title", "无标题"),
                    "url": post.get("url", ""),
                    "likes": likes,
                    "tags": post.get("tags", []),
                    "desc": post.get("desc", "")[:150],
                }
            )
        return results

    def get_posts_by_semantic(self, concept, top_k=30):
        if not concept.strip() or self._collection is None:
            return []
        results = self._collection.query(
            query_texts=[concept],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        if not results["ids"] or len(results["ids"][0]) == 0:
            return []
        posts_list = []
        for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
            score = round(1 - dist, 3)
            posts_list.append(
                {
                    "note_id": meta.get("note_id", ""),
                    "title": meta.get("title", "无标题"),
                    "url": meta.get("url", ""),
                    "likes": int(meta.get("likes", 0)),
                    "tags": meta.get("tags", "").split(","),
                    "desc": meta.get("desc", "")[:150],
                    "_score": score,
                }
            )
        return posts_list

    @staticmethod
    def _format_results(results, source_label=""):
        total = len(results)
        display = results[:50]
        lines = [f"共找到 {total} 条帖子（来源：{source_label}）："]
        for i, p in enumerate(display, 1):
            lines.append(f"{i}. {p['title']}")
            lines.append(f"   👍 {p['likes']}  | 标签: {', '.join(p['tags'][:5]) if p['tags'] else '无'}")
            if p.get("desc"):
                desc_preview = p["desc"][:100] + ("..." if len(p["desc"]) > 100 else "")
                lines.append(f"   📝 {desc_preview}")
            lines.append(f"   🔗 {p['url']}")
            lines.append("")
        if total > len(display):
            lines.append(f"... 还有 {total - len(display)} 条未显示。")
        return "\n".join(lines)

    def hybrid_search(self, llm_client, keyword=None, min_likes=None, max_likes=None, tag=None):
        exact_results = self.get_posts_by_keyword(keyword, min_likes, max_likes, tag, llm_client)
        exact_ids = {p["note_id"] for p in exact_results}
        semantic_results = []
        main_concept = None
        if keyword:
            main_concept = keyword.split(",")[0].strip()
            if main_concept:
                raw = self.get_posts_by_semantic(main_concept, top_k=30)
                semantic_results = [p for p in raw if p.get("_score", 0) > 0.35]
                semantic_results = [p for p in semantic_results if self._passes_filters(p, min_likes, max_likes, tag)]
        candidate_pool = exact_results.copy()
        for p in semantic_results:
            if p["note_id"] not in exact_ids:
                candidate_pool.append(p)
        if not candidate_pool:
            return "未找到符合条件的帖子。"
        if main_concept:
            ranked = self.rerank_results(main_concept, candidate_pool)
            source_label = "混合检索（Cross-Encoder重排）"
        else:
            ranked = sorted(candidate_pool, key=lambda x: x.get("likes", 0), reverse=True)
            source_label = "混合检索"
        return self._format_results(ranked, source_label)

    def query_posts(self, llm_client, keyword=None, min_likes=None, max_likes=None, tag=None):
        results = self.get_posts_by_keyword(keyword, min_likes, max_likes, tag, llm_client)
        if not results:
            return "未找到符合条件的帖子。"
        return self._format_results(results, "关键词匹配")

    def semantic_search(self, concept: str, top_k: int = 20):
        results = self.get_posts_by_semantic(concept, top_k)
        if not results:
            return f"未找到与 '{concept}' 语义相关的帖子。"
        return self._format_results(results, f"语义检索 '{concept}'")

    def generate_insight(self, llm_client):
        tag_counter = Counter()
        for post in self.posts:
            for tag in post.get("tags", []):
                if tag:
                    tag_counter[tag] += 1
        top_tags = [tag for tag, _ in tag_counter.most_common(15)]
        titles = [post.get("title", "") for post in self.posts if post.get("title")]
        sample_titles = titles[:20]
        prompt = f"""
你是一位资深的生活观察家。以下是一位用户在小红书上收藏的所有帖子的**高频标签**和**部分标题样本**。

高频标签：{', '.join(top_tags)}
标题样本：{'; '.join(sample_titles)}

请根据这些信息，用一段自然、有温度的文字（约100~150字）概括该用户的兴趣偏好和风格画像。
只输出最终的文字描述，不要加任何前缀或解释。
"""
        try:
            return llm_client._call(
                [
                    {"role": "system", "content": "你是一个擅长总结用户兴趣的生活观察家。"},
                    {"role": "user", "content": prompt},
                ]
            ).strip()
        except Exception as e:
            return f"⚠️ 生成偏好画像失败：{e}，请稍后重试。"

    def clear_memory(self) -> bool:
        if self.memory_file.exists():
            try:
                self.memory_file.unlink()
                return True
            except Exception:
                return False
        return True

    def load_memory(self) -> dict:
        if self.memory_file.exists():
            with open(self.memory_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "conversations" not in data:
                    data["conversations"] = []
                if "category_freq" not in data:
                    data["category_freq"] = defaultdict(int)
                else:
                    data["category_freq"] = defaultdict(int, data["category_freq"])
                return data
        return {
            "conversations": [],
            "category_freq": defaultdict(int),
            "preferred_min_likes": None,
            "preferred_tag": None,
        }

    def save_memory(self, memory: dict) -> None:
        memory_copy = dict(memory)
        memory_copy["category_freq"] = dict(memory["category_freq"])
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(memory_copy, f, ensure_ascii=False, indent=2)

    def update_memory(self, memory: dict, user_input: str, assistant_response: str) -> None:
        memory["conversations"].append(
            {"user": user_input, "assistant": assistant_response[:300] if assistant_response else ""}
        )
        if len(memory["conversations"]) > 10:
            memory["conversations"] = memory["conversations"][-10:]
        categories = ["穿搭", "妆容", "美食", "旅行", "家居", "健身", "电影", "职场"]
        for cat in categories:
            if cat in user_input:
                memory["category_freq"][cat] += 1
                break
        likes_match = re.search(r"点赞\s*([\d.]+)\s*万?", user_input)
        if likes_match:
            try:
                val = float(likes_match.group(1))
                if "万" in user_input:
                    val *= 10000
                memory["preferred_min_likes"] = int(val)
            except Exception:
                pass
        tag_match = re.search(r"标签[：:]\s*([^\s,，]+)", user_input)
        if tag_match:
            memory["preferred_tag"] = tag_match.group(1)

    @staticmethod
    def format_memory_for_prompt(memory: dict) -> str:
        lines = []
        if memory["conversations"]:
            recent = memory["conversations"][-3:]
            lines.append("最近对话记录（用户 → 助手）：")
            for conv in recent:
                lines.append(f"用户：{conv['user'][:60]}... → 助手：{conv['assistant'][:120]}...")
            lines.append("")
        if memory["category_freq"]:
            top_cats = sorted(memory["category_freq"].items(), key=lambda x: x[1], reverse=True)[:3]
            if top_cats:
                lines.append("用户经常查询的分类：" + ", ".join([f"{cat}({cnt}次)" for cat, cnt in top_cats]))
        if memory.get("preferred_min_likes") is not None:
            lines.append(f"用户偏好的最小点赞数：{memory['preferred_min_likes']}")
        if memory.get("preferred_tag"):
            lines.append(f"用户常关注的标签：{memory['preferred_tag']}")
        if lines:
            return "\n" + "\n".join(lines)
        return ""

    def get_stats(self) -> dict:
        memory = self.load_memory()
        vector_count = self._collection.count() if self._collection else 0
        return {
            "total_items": len(self.posts),
            "memory_conversations": len(memory.get("conversations", [])),
            "vector_index_count": vector_count,
        }

    def get_tools(self, llm_client) -> dict:
        return {
            "hybrid_search": lambda **kwargs: self.hybrid_search(llm_client, **kwargs),
            "query_posts": lambda **kwargs: self.query_posts(llm_client, **kwargs),
            "semantic_search": self.semantic_search,
            "generate_insight": lambda **kwargs: self.generate_insight(llm_client),
        }
