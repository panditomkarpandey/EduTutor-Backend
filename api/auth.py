from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from datetime import datetime

from models.schemas import UserCreate, UserLogin, Token
from utils.auth import hash_password, verify_password, create_access_token
from utils.db import get_db

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/register", response_model=dict)
@limiter.limit("5/minute")
async def register(request: Request, user_data: UserCreate):
    db = get_db()

    # Check if email exists
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_doc = {
        "name": user_data.name,
        "email": user_data.email,
        "hashed_password": hash_password(user_data.password),
        "role": user_data.role.value,
        "language": user_data.language,
        "created_at": datetime.utcnow(),
        "last_login": None
    }

    result = await db.users.insert_one(user_doc)
    return {
        "success": True,
        "message": "Registration successful",
        "user_id": str(result.inserted_id)
    }


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
async def login(request: Request, credentials: UserLogin):
    db = get_db()
    user = await db.users.find_one({"email": credentials.email})

    if not user or not verify_password(credentials.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"last_login": datetime.utcnow()}}
    )

    token = create_access_token({"sub": user["email"], "role": user["role"]})
    return Token(
        access_token=token,
        token_type="bearer",
        role=user["role"],
        name=user["name"]
    )


@router.get("/me")
async def get_me(request: Request):
    from fastapi.security import HTTPBearer
    from utils.auth import get_current_user
    # This route is handled with dependency in practice
    return {"message": "Use Authorization header"}
