import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

_client = None
_db = None


async def connect_db():
    global _client, _db
    mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGODB_DB", "education_tutor")
    _client = AsyncIOMotorClient(
    mongo_uri,
    serverSelectionTimeoutMS=10000,
    connectTimeoutMS=10000,
    socketTimeoutMS=10000,
)
    _db = _client[db_name]

    # Wait for connection to be established
    for attempt in range(5):
        try:
            await _db.command("ping")
            break
        except Exception as e:
            if attempt == 4:
                raise
            print(f"[DB] Waiting for MongoDB... attempt {attempt + 1}/5")
            await asyncio.sleep(3)

    await _ensure_indexes()
    print(f"[DB] Connected to MongoDB: {db_name}")


async def close_db():
    global _client
    if _client:
        _client.close()
        print("[DB] MongoDB connection closed")


def get_db():
    return _db


async def _ensure_indexes():
    db = _db
    try:
        await db.users.create_index([("email", 1)], unique=True)
        await db.textbooks.create_index([("board", 1), ("class_name", 1), ("subject", 1)])
        await db.chunks.create_index([("textbook_id", 1)])
        await db.chunks.create_index([("subject", 1)])
        await db.chat_history.create_index([("student_id", 1)])
        await db.chat_history.create_index([("created_at", 1)])
        await db.faq_cache.create_index([("question_hash", 1)], unique=True)
        await db.quizzes.create_index([("student_id", 1)])
        print("[DB] Indexes ensured")
    except Exception as e:
        print(f"[DB] Index warning: {e}")
