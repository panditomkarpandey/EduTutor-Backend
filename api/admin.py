import os
import asyncio
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from bson import ObjectId
from datetime import datetime
from slowapi import Limiter
from slowapi.util import get_remote_address

from utils.auth import require_admin
from utils.db import get_db
from utils.embeddings import generate_embeddings_batch
from services.pdf_service import process_pdf

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

MAX_FILE_SIZE = int(os.getenv("MAX_PDF_SIZE_MB", "50")) * 1024 * 1024  # 50MB default
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "8"))
DB_INSERT_BATCH_SIZE = int(os.getenv("DB_INSERT_BATCH_SIZE", "50"))


@router.post("/upload-textbook")
@limiter.limit("5/minute")
async def upload_textbook(
    request: Request,
    file: UploadFile = File(...),
    board: str = Form(...),
    class_name: str = Form(...),
    subject: str = Form(...),
    title: str = Form(...),
    admin=Depends(require_admin)
):
    # Read file first so we can inspect bytes
    file_bytes = await file.read()

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Max {MAX_FILE_SIZE // (1024*1024)}MB")

    # Deep validation: extension + MIME + magic bytes
    from utils.validators import validate_pdf_file, sanitize_filename
    safe_filename = sanitize_filename(file.filename or "upload.pdf")
    validate_pdf_file(safe_filename, file.content_type or "", file_bytes)

    db = get_db()

    # Check for duplicate
    existing = await db.textbooks.find_one({
        "board": board, "class_name": class_name,
        "subject": subject, "title": title
    })
    if existing:
        raise HTTPException(status_code=409, detail="Textbook already uploaded")

    # Insert textbook record
    tb_doc = {
        "board": board,
        "class_name": class_name,
        "subject": subject,
        "title": title,
        "filename": file.filename,
        "chunk_count": 0,
        "status": "processing",
        "uploaded_by": str(admin["_id"]),
        "created_at": datetime.utcnow()
    }
    result = await db.textbooks.insert_one(tb_doc)
    textbook_id = str(result.inserted_id)

    # Process in background
    asyncio.create_task(_ingest_pdf(textbook_id, file_bytes, board, class_name, subject))

    return {
        "success": True,
        "textbook_id": textbook_id,
        "message": "PDF uploaded. Processing started in background."
    }


async def _ingest_pdf(textbook_id: str, file_bytes: bytes, board: str, class_name: str, subject: str):
    """Background task: extract, chunk, embed, store"""
    db = get_db()
    try:
        # Extract and chunk
        chunks = process_pdf(file_bytes)
        if not chunks:
            raise ValueError("No text could be extracted from PDF")

        inserted_count = 0
        for i in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            chunk_batch = chunks[i:i + EMBEDDING_BATCH_SIZE]
            texts = [c["text"] for c in chunk_batch]
            embeddings = generate_embeddings_batch(texts, batch_size=EMBEDDING_BATCH_SIZE)

            chunk_docs = []
            for chunk, embedding in zip(chunk_batch, embeddings):
                chunk_docs.append({
                    "textbook_id": textbook_id,
                    "chapter": chunk["chapter"],
                    "chapter_number": chunk["chapter_number"],
                    "chunk_index": chunk["chunk_index"],
                    "text": chunk["text"],
                    "token_count": chunk["token_count"],
                    "embedding": embedding,
                    "board": board,
                    "class_name": class_name,
                    "subject": subject,
                    "created_at": datetime.utcnow()
                })

            for j in range(0, len(chunk_docs), DB_INSERT_BATCH_SIZE):
                batch = chunk_docs[j:j + DB_INSERT_BATCH_SIZE]
                await db.chunks.insert_many(batch)
                inserted_count += len(batch)

        # Update textbook status
        await db.textbooks.update_one(
            {"_id": ObjectId(textbook_id)},
            {"$set": {"status": "ready", "chunk_count": inserted_count}}
        )
        print(f"[Ingest] Textbook {textbook_id}: {inserted_count} chunks ingested")

    except Exception as e:
        print(f"[Ingest] Error for {textbook_id}: {e}")
        await db.textbooks.update_one(
            {"_id": ObjectId(textbook_id)},
            {"$set": {"status": "error", "error": str(e)}}
        )


@router.get("/textbooks")
async def list_textbooks(
    request: Request,
    board: str = None,
    class_name: str = None,
    subject: str = None,
    admin=Depends(require_admin)
):
    db = get_db()
    query = {}
    if board:
        query["board"] = board
    if class_name:
        query["class_name"] = class_name
    if subject:
        query["subject"] = subject

    cursor = db.textbooks.find(query, {"_id": 1, "board": 1, "class_name": 1,
                                        "subject": 1, "title": 1, "filename": 1,
                                        "chunk_count": 1, "status": 1, "created_at": 1})
    books = await cursor.to_list(length=100)
    for b in books:
        b["_id"] = str(b["_id"])
        b["created_at"] = b["created_at"].isoformat()
    return {"textbooks": books, "total": len(books)}


@router.delete("/textbooks/{textbook_id}")
async def delete_textbook(textbook_id: str, request: Request, admin=Depends(require_admin)):
    db = get_db()
    await db.chunks.delete_many({"textbook_id": textbook_id})
    result = await db.textbooks.delete_one({"_id": ObjectId(textbook_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Textbook not found")
    return {"success": True, "message": "Textbook and embeddings deleted"}


@router.get("/textbook-status/{textbook_id}")
async def get_status(textbook_id: str, request: Request, admin=Depends(require_admin)):
    db = get_db()
    tb = await db.textbooks.find_one({"_id": ObjectId(textbook_id)})
    if not tb:
        raise HTTPException(status_code=404, detail="Not found")
    return {"status": tb["status"], "chunk_count": tb.get("chunk_count", 0)}
