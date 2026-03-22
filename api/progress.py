"""
Learning Progress API
─────────────────────
GET  /api/progress/summary      → Student's overall learning stats
GET  /api/progress/subjects     → Per-subject breakdown
GET  /api/progress/streak       → Daily question streak
POST /api/progress/bookmark     → Bookmark a chat answer
GET  /api/progress/bookmarks    → List bookmarks
"""

from fastapi import APIRouter, Depends, Request
from utils.auth import get_current_user
from utils.db import get_db
from datetime import datetime, timedelta

router = APIRouter()


@router.get("/summary")
async def learning_summary(request: Request, current_user=Depends(get_current_user)):
    db = get_db()
    student_id = str(current_user["_id"])

    total_questions  = await db.chat_history.count_documents({"student_id": student_id})
    total_quizzes    = await db.quizzes.count_documents({"student_id": student_id, "completed": True})
    cached_served    = await db.chat_history.count_documents({"student_id": student_id, "cached": True})

    # Avg quiz score
    pipeline = [
        {"$match": {"student_id": student_id, "completed": True}},
        {"$group": {"_id": None, "avg": {"$avg": "$score"}, "best": {"$max": "$score"}}}
    ]
    score_data = await db.quizzes.aggregate(pipeline).to_list(1)
    avg_score  = round(score_data[0]["avg"], 1)  if score_data else 0
    best_score = score_data[0]["best"] if score_data else 0

    # Most active subject
    subj_pipeline = [
        {"$match": {"student_id": student_id, "subject": {"$exists": True, "$ne": None}}},
        {"$group": {"_id": "$subject", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 1}
    ]
    subj_result = await db.chat_history.aggregate(subj_pipeline).to_list(1)
    top_subject = subj_result[0]["_id"] if subj_result else None

    # Questions this week
    week_ago = datetime.utcnow() - timedelta(days=7)
    questions_week = await db.chat_history.count_documents({
        "student_id": student_id,
        "created_at": {"$gte": week_ago}
    })

    return {
        "total_questions": total_questions,
        "total_quizzes":   total_quizzes,
        "avg_quiz_score":  avg_score,
        "best_quiz_score": best_score,
        "top_subject":     top_subject,
        "questions_this_week": questions_week,
        "cache_served":    cached_served,
    }


@router.get("/subjects")
async def subject_breakdown(request: Request, current_user=Depends(get_current_user)):
    db = get_db()
    student_id = str(current_user["_id"])

    pipeline = [
        {"$match": {"student_id": student_id}},
        {"$group": {
            "_id": {"$ifNull": ["$subject", "General"]},
            "questions": {"$sum": 1},
            "last_asked": {"$max": "$created_at"}
        }},
        {"$sort": {"questions": -1}}
    ]
    subjects = await db.chat_history.aggregate(pipeline).to_list(20)
    return {
        "subjects": [
            {
                "subject": s["_id"],
                "questions": s["questions"],
                "last_asked": s["last_asked"].isoformat() if s.get("last_asked") else None
            }
            for s in subjects
        ]
    }


@router.get("/streak")
async def question_streak(request: Request, current_user=Depends(get_current_user)):
    db = get_db()
    student_id = str(current_user["_id"])

    # Get last 30 days of activity
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    pipeline = [
        {"$match": {"student_id": student_id, "created_at": {"$gte": thirty_days_ago}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": -1}}
    ]
    daily = await db.chat_history.aggregate(pipeline).to_list(30)

    # Calculate current streak
    active_days = {d["_id"] for d in daily}
    streak = 0
    today = datetime.utcnow().date()
    for i in range(30):
        day_str = (today - timedelta(days=i)).isoformat()
        if day_str in active_days:
            streak += 1
        else:
            break

    return {
        "current_streak": streak,
        "active_days": [{"date": d["_id"], "questions": d["count"]} for d in daily]
    }


@router.post("/bookmark")
async def bookmark_answer(request: Request, current_user=Depends(get_current_user)):
    body = await request.json()
    chat_id = body.get("chat_id")
    if not chat_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="chat_id required")

    db = get_db()
    from bson import ObjectId
    chat = await db.chat_history.find_one({
        "_id": ObjectId(chat_id),
        "student_id": str(current_user["_id"])
    })
    if not chat:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Chat not found")

    await db.bookmarks.update_one(
        {"student_id": str(current_user["_id"]), "chat_id": chat_id},
        {"$set": {
            "student_id": str(current_user["_id"]),
            "chat_id": chat_id,
            "question": chat["question"],
            "answer": chat["answer"],
            "subject": chat.get("subject"),
            "bookmarked_at": datetime.utcnow()
        }},
        upsert=True
    )
    return {"success": True, "message": "Bookmarked successfully"}


@router.get("/bookmarks")
async def list_bookmarks(request: Request, current_user=Depends(get_current_user)):
    db = get_db()
    cursor = db.bookmarks.find(
        {"student_id": str(current_user["_id"])},
        {"_id": 1, "chat_id": 1, "question": 1, "answer": 1, "subject": 1, "bookmarked_at": 1}
    ).sort("bookmarked_at", -1).limit(50)
    bookmarks = await cursor.to_list(50)
    for b in bookmarks:
        b["_id"] = str(b["_id"])
        b["bookmarked_at"] = b["bookmarked_at"].isoformat()
    return {"bookmarks": bookmarks}


@router.delete("/bookmark/{chat_id}")
async def remove_bookmark(chat_id: str, request: Request, current_user=Depends(get_current_user)):
    db = get_db()
    await db.bookmarks.delete_one({
        "student_id": str(current_user["_id"]),
        "chat_id": chat_id
    })
    return {"success": True}
