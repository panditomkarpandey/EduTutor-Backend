from fastapi import APIRouter, Depends, Request
from utils.auth import require_admin
from utils.db import get_db
from datetime import datetime, timedelta

router = APIRouter()


@router.get("/dashboard")
async def dashboard(request: Request, admin=Depends(require_admin)):
    db = get_db()

    # Aggregate stats
    total_students = await db.users.count_documents({"role": "student"})
    total_textbooks = await db.textbooks.count_documents({"status": "ready"})
    total_questions = await db.chat_history.count_documents({})
    total_quizzes = await db.quizzes.count_documents({"completed": True})
    cached_questions = await db.chat_history.count_documents({"cached": True})
    total_chunks = await db.chunks.count_documents({})

    # FAQ cache stats
    faq_count = await db.faq_cache.count_documents({})
    faq_hits_pipeline = [{"$group": {"_id": None, "total": {"$sum": "$hit_count"}}}]
    faq_hits_result = await db.faq_cache.aggregate(faq_hits_pipeline).to_list(1)
    total_cache_hits = faq_hits_result[0]["total"] if faq_hits_result else 0

    # Questions in last 7 days
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_questions = await db.chat_history.count_documents({"created_at": {"$gte": week_ago}})

    # Questions per day (last 7 days)
    daily_pipeline = [
        {"$match": {"created_at": {"$gte": week_ago}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    daily_data = await db.chat_history.aggregate(daily_pipeline).to_list(7)

    # Top subjects asked
    subject_pipeline = [
        {"$match": {"subject": {"$exists": True, "$ne": None}}},
        {"$group": {"_id": "$subject", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5}
    ]
    top_subjects = await db.chat_history.aggregate(subject_pipeline).to_list(5)

    # Average quiz scores
    avg_score_pipeline = [
        {"$match": {"completed": True}},
        {"$group": {"_id": None, "avg": {"$avg": "$score"}}}
    ]
    avg_result = await db.quizzes.aggregate(avg_score_pipeline).to_list(1)
    avg_score = round(avg_result[0]["avg"], 1) if avg_result else 0

    return {
        "overview": {
            "total_students": total_students,
            "total_textbooks": total_textbooks,
            "total_questions": total_questions,
            "total_quizzes": total_quizzes,
            "total_chunks": total_chunks,
            "cached_questions": cached_questions,
            "cache_ratio": round(cached_questions / max(total_questions, 1) * 100, 1),
            "avg_quiz_score": avg_score
        },
        "faq_cache": {
            "total_cached": faq_count,
            "total_hits": total_cache_hits
        },
        "recent": {
            "questions_7d": recent_questions,
            "daily": daily_data
        },
        "top_subjects": [{"subject": s["_id"], "count": s["count"]} for s in top_subjects]
    }


@router.get("/students")
async def student_stats(request: Request, admin=Depends(require_admin)):
    db = get_db()
    pipeline = [
        {"$lookup": {
            "from": "chat_history",
            "localField": "_id",
            "foreignField": "student_id",
            "as": "questions",
            "pipeline": [{"$count": "total"}]
        }},
        {"$match": {"role": "student"}},
        {"$project": {
            "_id": {"$toString": "$_id"},
            "name": 1,
            "email": 1,
            "language": 1,
            "created_at": 1,
            "last_login": 1,
        }},
        {"$limit": 50}
    ]
    students = await db.users.aggregate(pipeline).to_list(50)
    for s in students:
        if "created_at" in s:
            s["created_at"] = s["created_at"].isoformat()
        if s.get("last_login"):
            s["last_login"] = s["last_login"].isoformat()
    return {"students": students}
