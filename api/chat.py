from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from datetime import datetime

from models.schemas import QuestionRequest
from utils.auth import get_current_user
from utils.db import get_db
from utils.embeddings import generate_embedding
from services.rag_service import (
    vector_search, prune_context, build_context_string,
    question_hash, get_faq_cache, set_faq_cache
)
from services.llm_service import generate_answer
from utils.validators import sanitize_question, validate_language, check_prompt_injection

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/ask")
@limiter.limit("20/minute")
async def ask_question(
    request: Request,
    body: QuestionRequest,
    current_user=Depends(get_current_user)
):
    question = sanitize_question(body.question.strip())
    language = validate_language(body.language or current_user.get("language", "en"))
    check_prompt_injection(question)
    student_id = str(current_user["_id"])

    # 1. Check FAQ cache
    q_hash = question_hash(question, language)
    cached_answer = await get_faq_cache(q_hash)

    if cached_answer:
        # Save to history
        await _save_history(student_id, question, cached_answer, [], body.textbook_id, body.subject, language, cached=True)
        return {
            "answer": cached_answer,
            "sources": [],
            "cached": True,
            "chunks_used": 0
        }

    # 2. Generate question embedding
    q_embedding = generate_embedding(question)

    # 3. Vector similarity search
    raw_chunks = await vector_search(q_embedding, body.textbook_id, body.subject)

    if not raw_chunks:
        raise HTTPException(
            status_code=404,
            detail="No relevant content found. Please ensure a textbook is uploaded for this subject."
        )

    # 4. Context pruning
    pruned = prune_context(raw_chunks)

    # 5. Build context string
    context = build_context_string(pruned)

    # 6. Generate answer via LLM
    try:
        answer = await generate_answer(question, context, language)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Prepare sources (minimal data for frontend)
    sources = [
        {
            "chapter": c.get("chapter", ""),
            "subject": c.get("subject", ""),
            "score": round(c.get("score", 0), 3)
        }
        for c in pruned
    ]

    # 7. Cache the answer
    answer_str = str(answer)
    await set_faq_cache(q_hash, question, answer_str, language)

    # 8. Save to history
    await _save_history(student_id, question, answer_str, sources, body.textbook_id, body.subject, language)

    return {
        "answer": answer,
        "sources": sources,
        "cached": False,
        "chunks_used": len(pruned)
    }


async def _save_history(student_id, question, answer, sources, textbook_id, subject, language, cached=False):
    db = get_db()
    await db.chat_history.insert_one({
        "student_id": student_id,
        "question": question,
        "answer": str(answer),
        "sources": sources,
        "textbook_id": textbook_id,
        "subject": subject,
        "language": language,
        "cached": cached,
        "created_at": datetime.utcnow()
    })


@router.get("/history")
async def get_history(
    request: Request,
    limit: int = 20,
    skip: int = 0,
    current_user=Depends(get_current_user)
):
    db = get_db()
    student_id = str(current_user["_id"])

    cursor = db.chat_history.find(
        {"student_id": student_id},
        {"_id": 1, "question": 1, "answer": 1, "sources": 1, "cached": 1, "created_at": 1, "subject": 1}
    ).sort("created_at", -1).skip(skip).limit(limit)

    history = await cursor.to_list(length=limit)
    for h in history:
        h["_id"] = str(h["_id"])
        h["created_at"] = h["created_at"].isoformat()

    total = await db.chat_history.count_documents({"student_id": student_id})
    return {"history": history, "total": total, "skip": skip, "limit": limit}


@router.delete("/history")
async def clear_history(request: Request, current_user=Depends(get_current_user)):
    db = get_db()
    student_id = str(current_user["_id"])
    result = await db.chat_history.delete_many({"student_id": student_id})
    return {"deleted": result.deleted_count}
