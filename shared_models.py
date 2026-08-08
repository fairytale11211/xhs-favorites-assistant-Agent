import os
import threading
from typing import Optional

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from sentence_transformers import CrossEncoder, SentenceTransformer

from backend.config import EMBEDDING_MODEL_PATH, RERANKER_MODEL_PATH

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

_lock = threading.Lock()
_embedding_model: Optional[SentenceTransformer] = None
_reranker: Optional[CrossEncoder] = None


class LocalEmbeddingFunction(EmbeddingFunction):
    def __call__(self, input: Documents) -> Embeddings:
        model = get_embedding_model()
        if isinstance(input, str):
            input = [input]
        embeddings = model.encode(input, show_progress_bar=False)
        return embeddings.tolist()


def get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        with _lock:
            if _embedding_model is None:
                if not os.path.exists(EMBEDDING_MODEL_PATH):
                    raise FileNotFoundError(
                        f"Embedding model not found: {EMBEDDING_MODEL_PATH}. "
                        "Download all-MiniLM-L6-v2 and set EMBEDDING_MODEL_PATH."
                    )
                _embedding_model = SentenceTransformer(EMBEDDING_MODEL_PATH)
    return _embedding_model


def get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        with _lock:
            if _reranker is None:
                if not os.path.exists(RERANKER_MODEL_PATH):
                    raise FileNotFoundError(
                        f"Reranker model not found: {RERANKER_MODEL_PATH}. "
                        "Download bge-reranker-base and set RERANKER_MODEL_PATH."
                    )
                _reranker = CrossEncoder(RERANKER_MODEL_PATH, max_length=512)
    return _reranker


RERANK_CANDIDATE_LIMIT = 60
