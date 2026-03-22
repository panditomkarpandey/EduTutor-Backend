from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    STUDENT = "student"
    ADMIN = "admin"


class UserCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)
    role: UserRole = UserRole.STUDENT
    language: str = "en"  # "en" or "hi"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserInDB(BaseModel):
    id: Optional[str] = None
    name: str
    email: str
    hashed_password: str
    role: UserRole
    language: str = "en"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None


class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    name: str


class TextbookCreate(BaseModel):
    board: str = Field(..., min_length=1, max_length=100)
    class_name: str = Field(..., min_length=1, max_length=50)
    subject: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=200)


class TextbookInDB(BaseModel):
    id: Optional[str] = None
    board: str
    class_name: str
    subject: str
    title: str
    filename: str
    chunk_count: int = 0
    status: str = "processing"  # processing, ready, error
    uploaded_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChunkInDB(BaseModel):
    textbook_id: str
    chapter: str
    chapter_number: int
    chunk_index: int
    text: str
    token_count: int
    embedding: List[float]
    board: str
    class_name: str
    subject: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)
    textbook_id: Optional[str] = None
    subject: Optional[str] = None
    language: str = "en"


class ChatHistory(BaseModel):
    id: Optional[str] = None
    student_id: str
    question: str
    answer: str
    sources: List[Dict[str, Any]] = []
    textbook_id: Optional[str] = None
    subject: Optional[str] = None
    language: str = "en"
    cached: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class QuizGenerateRequest(BaseModel):
    textbook_id: str
    topic: Optional[str] = None
    num_questions: int = Field(default=5, ge=1, le=10)
    language: str = "en"


class FAQCache(BaseModel):
    question_hash: str
    question: str
    answer: str
    language: str
    hit_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed: datetime = Field(default_factory=datetime.utcnow)
