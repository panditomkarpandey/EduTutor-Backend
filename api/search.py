from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from utils.auth import get_current_user
from utils.db import get_db
from utils.embeddings import generate_embedding
from services.rag_service import vector_search

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get("/textbooks")
async def search_textbooks(
    request: Request,
    q: str = "",
    board: str = None,
    class_name: str = None,
    subject: str = None,
    current_user=Depends(get_current_user)
):
    db = get_db()
    query = {"status": "ready"}
    if board:
        query["board"] = board
    if class_name:
        query["class_name"] = class_name
    if subject:
        query["subject"] = {"$regex": subject, "$options": "i"}
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"subject": {"$regex": q, "$options": "i"}},
            {"board": {"$regex": q, "$options": "i"}}
        ]

    cursor = db.textbooks.find(query, {"embedding": 0}).limit(50)
    books = await cursor.to_list(length=50)
    for b in books:
        b["_id"] = str(b["_id"])
        b["created_at"] = b["created_at"].isoformat()
    return {"results": books, "total": len(books)}


@router.get("/semantic")
@limiter.limit("30/minute")
async def semantic_search(
    request: Request,
    q: str,
    subject: str = None,
    limit: int = 5,
    current_user=Depends(get_current_user)
):
    if not q or len(q.strip()) < 3:
        raise HTTPException(status_code=400, detail="Query too short")

    embedding = generate_embedding(q)
    chunks = await vector_search(embedding, subject=subject, top_k=limit)

    results = [
        {
            "chapter": c.get("chapter", ""),
            "text": c.get("text", "")[:300] + "..." if len(c.get("text", "")) > 300 else c.get("text", ""),
            "subject": c.get("subject", ""),
            "score": round(c.get("score", 0), 3)
        }
        for c in chunks
    ]
    return {"results": results, "query": q}


@router.get("/boards")
async def get_boards(request: Request, current_user=Depends(get_current_user)):
    db = get_db()
    boards = await db.textbooks.distinct("board", {"status": "ready"})
    classes = await db.textbooks.distinct("class_name", {"status": "ready"})
    subjects = await db.textbooks.distinct("subject", {"status": "ready"})
    return {"boards": boards, "classes": sorted(classes), "subjects": subjects}
