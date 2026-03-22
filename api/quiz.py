from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from datetime import datetime

from models.schemas import QuizGenerateRequest
from utils.auth import get_current_user
from utils.db import get_db
from utils.embeddings import generate_embedding
from services.rag_service import vector_search, prune_context, build_context_string
from services.llm_service import generate_quiz

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/generate")
@limiter.limit("10/minute")
async def generate_quiz_endpoint(
    request: Request,
    body: QuizGenerateRequest,
    current_user=Depends(get_current_user)
):
    language = body.language or current_user.get("language", "en")
    student_id = str(current_user["_id"])

    # Get context for quiz
    topic = body.topic or "general concepts"
    q_embedding = generate_embedding(topic)
    raw_chunks = await vector_search(q_embedding, body.textbook_id)

    if not raw_chunks:
        raise HTTPException(status_code=404, detail="No content found for this textbook")

    pruned = prune_context(raw_chunks, max_tokens=2000)
    context = build_context_string(pruned)

    try:
        questions = await generate_quiz(context, body.num_questions, language)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not questions:
        raise HTTPException(status_code=500, detail="Quiz generation failed. Try again.")

    # Save quiz to DB
    quiz_doc = {
        "student_id": student_id,
        "textbook_id": body.textbook_id,
        "topic": topic,
        "language": language,
        "questions": questions,
        "score": None,
        "completed": False,
        "created_at": datetime.utcnow()
    }
    db = get_db()
    result = await db.quizzes.insert_one(quiz_doc)

    return {
        "quiz_id": str(result.inserted_id),
        "questions": questions,
        "total": len(questions)
    }


@router.post("/submit/{quiz_id}")
async def submit_quiz(
    quiz_id: str,
    request: Request,
    current_user=Depends(get_current_user)
):
    from bson import ObjectId
    body = await request.json()
    answers = body.get("answers", {})  # {question_index: selected_option}

    db = get_db()
    quiz = await db.quizzes.find_one({"_id": ObjectId(quiz_id), "student_id": str(current_user["_id"])})
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    questions = quiz["questions"]
    score = 0
    results = []

    for i, q in enumerate(questions):
        user_ans = answers.get(str(i), "")
        correct = q.get("correct", "")
        is_correct = user_ans.strip().upper().startswith(correct.strip().upper())
        if is_correct:
            score += 1
        results.append({
            "question": q["question"],
            "your_answer": user_ans,
            "correct_answer": correct,
            "is_correct": is_correct,
            "explanation": q.get("explanation", "")
        })

    percentage = round((score / len(questions)) * 100) if questions else 0

    await db.quizzes.update_one(
        {"_id": ObjectId(quiz_id)},
        {"$set": {"score": percentage, "completed": True, "answers": answers}}
    )

    # Save to learning history
    await db.learning_history.insert_one({
        "student_id": str(current_user["_id"]),
        "quiz_id": quiz_id,
        "textbook_id": quiz["textbook_id"],
        "topic": quiz["topic"],
        "score": percentage,
        "total_questions": len(questions),
        "correct": score,
        "created_at": datetime.utcnow()
    })

    return {"score": percentage, "correct": score, "total": len(questions), "results": results}


@router.get("/history")
async def quiz_history(request: Request, current_user=Depends(get_current_user)):
    db = get_db()
    cursor = db.quizzes.find(
        {"student_id": str(current_user["_id"])},
        {"_id": 1, "topic": 1, "score": 1, "completed": 1, "created_at": 1, "total": 1}
    ).sort("created_at", -1).limit(20)
    quizzes = await cursor.to_list(length=20)
    for q in quizzes:
        q["_id"] = str(q["_id"])
        q["created_at"] = q["created_at"].isoformat()
    return {"quizzes": quizzes}
