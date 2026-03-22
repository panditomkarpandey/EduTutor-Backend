import os
import hashlib
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from utils.db import get_db
from utils.embeddings import generate_embedding, cosine_similarity

SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.35"))
TOP_K = int(os.getenv("TOP_K_CHUNKS", "10"))
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", "1500"))
PRUNE_SIMILARITY = float(os.getenv("PRUNE_SIMILARITY", "0.45"))


async def vector_search(
    question_embedding: List[float],
    textbook_id: Optional[str] = None,
    subject: Optional[str] = None,
    top_k: int = TOP_K
) -> List[Dict]:
    """
    MongoDB Atlas Vector Search query.
    Falls back to cosine similarity scan if Atlas Vector Search index not yet created.
    """
    db = get_db()

    # Build filter
    pre_filter = {}
    if textbook_id:
        pre_filter["textbook_id"] = textbook_id
    if subject and not textbook_id:
        pre_filter["subject"] = subject

    try:
        # Atlas Vector Search aggregation pipeline
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "embedding_index",
                    "path": "embedding",
                    "queryVector": question_embedding,
                    "numCandidates": top_k * 10,
                    "limit": top_k,
                    "filter": pre_filter if pre_filter else None
                }
            },
            {
                "$project": {
                    "_id": {"$toString": "$_id"},
                    "textbook_id": 1,
                    "chapter": 1,
                    "chapter_number": 1,
                    "chunk_index": 1,
                    "text": 1,
                    "token_count": 1,
                    "subject": 1,
                    "score": {"$meta": "vectorSearchScore"}
                }
            }
        ]

        # Remove None filter
        if pipeline[0]["$vectorSearch"]["filter"] is None:
            del pipeline[0]["$vectorSearch"]["filter"]

        results = await db.chunks.aggregate(pipeline).to_list(length=top_k)
        if results:
            return results
    except Exception as e:
        print(f"[RAG] Atlas Vector Search failed, falling back to scan: {e}")

    # Fallback: brute-force cosine similarity
    query = {}
    if pre_filter:
        query = pre_filter

    cursor = db.chunks.find(query, {
        "embedding": 1, "text": 1, "chapter": 1, "chapter_number": 1,
        "chunk_index": 1, "textbook_id": 1, "token_count": 1, "subject": 1
    })
    chunks = await cursor.to_list(length=5000)

    scored = []
    for chunk in chunks:
        emb = chunk.get("embedding", [])
        if emb:
            sim = cosine_similarity(question_embedding, emb)
            chunk["score"] = sim
            scored.append(chunk)

    scored.sort(key=lambda x: x["score"], reverse=True)
    results = scored[:top_k]

    for r in results:
        r["_id"] = str(r["_id"])
        r.pop("embedding", None)

    return results


def prune_context(chunks: List[Dict], max_tokens: int = MAX_CONTEXT_TOKENS) -> List[Dict]:
    """
    Context pruning:
    1. Filter by similarity threshold
    2. Sort by similarity score
    3. Remove duplicate chapters (keep best chunk per chapter)
    4. Limit total tokens
    """
    # Filter by similarity
    filtered = [c for c in chunks if c.get("score", 0) >= PRUNE_SIMILARITY]
    if not filtered:
        # Relax threshold if nothing passes
        filtered = chunks[:5]

    # Sort by score descending
    filtered.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Deduplicate chapters (keep highest scoring chunk per chapter)
    seen_chapters = {}
    deduped = []
    for chunk in filtered:
        ch = chunk.get("chapter_number", 0)
        if ch not in seen_chapters:
            seen_chapters[ch] = True
            deduped.append(chunk)

    # Limit total tokens
    pruned = []
    total_tokens = 0
    for chunk in deduped:
        ct = chunk.get("token_count", 100)
        if total_tokens + ct <= max_tokens:
            pruned.append(chunk)
            total_tokens += ct
        else:
            break

    return pruned


def build_context_string(chunks: List[Dict]) -> str:
    """Build context string from pruned chunks"""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        chapter = chunk.get("chapter", "Unknown")
        text = chunk.get("text", "")
        parts.append(f"[Source {i} - {chapter}]\n{text}")
    return "\n\n".join(parts)


def question_hash(question: str, language: str) -> str:
    normalized = question.lower().strip()
    return hashlib.md5(f"{normalized}:{language}".encode()).hexdigest()


async def get_faq_cache(q_hash: str) -> Optional[str]:
    db = get_db()
    cached = await db.faq_cache.find_one({"question_hash": q_hash})
    if cached:
        await db.faq_cache.update_one(
            {"question_hash": q_hash},
            {"$inc": {"hit_count": 1}, "$set": {"last_accessed": datetime.utcnow()}}
        )
        return cached["answer"]
    return None


async def set_faq_cache(q_hash: str, question: str, answer: str, language: str):
    db = get_db()
    await db.faq_cache.update_one(
        {"question_hash": q_hash},
        {"$set": {
            "question_hash": q_hash,
            "question": question,
            "answer": answer,
            "language": language,
            "last_accessed": datetime.utcnow()
        }, "$setOnInsert": {"created_at": datetime.utcnow(), "hit_count": 0}},
        upsert=True
    )
