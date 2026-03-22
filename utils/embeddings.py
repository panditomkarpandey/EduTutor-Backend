from sentence_transformers import SentenceTransformer
from typing import List
import numpy as np

_model: SentenceTransformer = None
MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


def load_embedding_model():
    global _model
    if _model is None:
        print(f"[Embeddings] Loading model: {MODEL_NAME}")
        _model = SentenceTransformer(MODEL_NAME)
        print("[Embeddings] Model loaded successfully")
    return _model


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        load_embedding_model()
    return _model


def generate_embedding(text: str) -> List[float]:
    model = get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def generate_embeddings_batch(texts: List[str], batch_size: int = 32) -> List[List[float]]:
    model = get_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False
    )
    return embeddings.tolist()


def cosine_similarity(a: List[float], b: List[float]) -> float:
    a_np = np.array(a)
    b_np = np.array(b)
    return float(np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np) + 1e-9))
