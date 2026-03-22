"""
Backend Tests – Education Tutor
================================
Run with:
    pytest tests/ -v
    # or inside Docker:
    docker-compose exec backend python -m pytest tests/ -v
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_db():
    """Mock MongoDB database"""
    db = MagicMock()
    db.users.find_one = AsyncMock(return_value=None)
    db.users.insert_one = AsyncMock(return_value=MagicMock(inserted_id="test_id"))
    db.users.update_one = AsyncMock()
    db.textbooks.find_one = AsyncMock(return_value=None)
    db.textbooks.insert_one = AsyncMock(return_value=MagicMock(inserted_id="tb_id"))
    db.chunks.insert_many = AsyncMock()
    db.chat_history.insert_one = AsyncMock()
    db.chat_history.find = MagicMock(return_value=MagicMock(
        sort=MagicMock(return_value=MagicMock(
            skip=MagicMock(return_value=MagicMock(
                limit=MagicMock(return_value=MagicMock(
                    to_list=AsyncMock(return_value=[])
                ))
            ))
        ))
    ))
    db.faq_cache.find_one = AsyncMock(return_value=None)
    db.faq_cache.update_one = AsyncMock()
    return db


# ── Unit Tests: PDF Service ───────────────────────────────────────────────────

class TestPDFService:
    def test_estimate_tokens(self):
        from services.pdf_service import estimate_tokens
        assert estimate_tokens("Hello world") == 2
        assert estimate_tokens("a" * 400) == 100

    def test_detect_chapter(self):
        from services.pdf_service import detect_chapter
        is_ch, title = detect_chapter("Chapter 1: The Solar System")
        assert is_ch is True
        assert "Chapter 1" in title

        is_ch2, _ = detect_chapter("This is a normal paragraph.")
        assert is_ch2 is False

    def test_detect_chapter_hindi(self):
        from services.pdf_service import detect_chapter
        is_ch, title = detect_chapter("अध्याय 3: भारत का इतिहास")
        assert is_ch is True

    def test_chunk_text_basic(self):
        from services.pdf_service import chunk_text
        text = " ".join([f"word{i}" for i in range(1000)])
        chunks = chunk_text(text, max_tokens=200)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) > 0

    def test_chunk_text_overlap(self):
        from services.pdf_service import chunk_text
        text = " ".join([f"w{i}" for i in range(500)])
        chunks = chunk_text(text, max_tokens=100, overlap=20)
        # With overlap, chunks should share some words
        assert len(chunks) >= 2

    def test_split_into_chapters(self):
        from services.pdf_service import split_into_chapters
        text = """
Chapter 1: Introduction
This is chapter one content with some text here.

Chapter 2: Main Content
This is chapter two with different content here.
        """
        chapters = split_into_chapters(text)
        assert len(chapters) >= 2
        titles = [c["title"] for c in chapters]
        assert any("Chapter 1" in t or "Introduction" in t for t in titles)

    def test_split_no_chapters(self):
        from services.pdf_service import split_into_chapters
        text = "Just some text without any chapter headings at all."
        chapters = split_into_chapters(text)
        assert len(chapters) >= 1


# ── Unit Tests: Embeddings ───────────────────────────────────────────────────

class TestEmbeddings:
    def test_cosine_similarity_identical(self):
        from utils.embeddings import cosine_similarity
        v = [0.1, 0.2, 0.3, 0.4, 0.5]
        sim = cosine_similarity(v, v)
        assert abs(sim - 1.0) < 0.001

    def test_cosine_similarity_opposite(self):
        from utils.embeddings import cosine_similarity
        v1 = [1.0, 0.0]
        v2 = [-1.0, 0.0]
        sim = cosine_similarity(v1, v2)
        assert sim < -0.9

    def test_cosine_similarity_orthogonal(self):
        from utils.embeddings import cosine_similarity
        v1 = [1.0, 0.0]
        v2 = [0.0, 1.0]
        sim = cosine_similarity(v1, v2)
        assert abs(sim) < 0.001

    def test_cosine_similarity_zero_vector(self):
        from utils.embeddings import cosine_similarity
        v1 = [0.0, 0.0]
        v2 = [1.0, 0.0]
        # Should not raise, returns ~0
        sim = cosine_similarity(v1, v2)
        assert sim == 0.0 or abs(sim) < 0.01


# ── Unit Tests: Auth Utils ────────────────────────────────────────────────────

class TestAuthUtils:
    def test_hash_and_verify_password(self):
        from utils.auth import hash_password, verify_password
        plain = "SecurePass123"
        hashed = hash_password(plain)
        assert hashed != plain
        assert verify_password(plain, hashed) is True
        assert verify_password("WrongPass", hashed) is False

    def test_create_and_decode_token(self):
        from utils.auth import create_access_token, decode_token
        data = {"sub": "test@test.com", "role": "student"}
        token = create_access_token(data)
        assert isinstance(token, str)
        decoded = decode_token(token)
        assert decoded["sub"] == "test@test.com"
        assert decoded["role"] == "student"

    def test_invalid_token_raises(self):
        from utils.auth import decode_token
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            decode_token("invalid.token.here")
        assert exc_info.value.status_code == 401

    def test_expired_token_raises(self):
        from utils.auth import create_access_token, decode_token
        from fastapi import HTTPException
        from datetime import timedelta
        token = create_access_token({"sub": "x@x.com"}, expires_delta=timedelta(seconds=-1))
        with pytest.raises(HTTPException):
            decode_token(token)


# ── Unit Tests: RAG Service ───────────────────────────────────────────────────

class TestRAGService:
    def test_prune_context_empty(self):
        from services.rag_service import prune_context
        result = prune_context([])
        assert result == []

    def test_prune_context_filters_low_score(self):
        from services.rag_service import prune_context
        chunks = [
            {"score": 0.8, "chapter": "Ch1", "chapter_number": 1, "text": "good chunk", "token_count": 50},
            {"score": 0.2, "chapter": "Ch2", "chapter_number": 2, "text": "bad chunk",  "token_count": 50},
            {"score": 0.9, "chapter": "Ch3", "chapter_number": 3, "text": "best chunk", "token_count": 50},
        ]
        pruned = prune_context(chunks, max_tokens=1500)
        scores = [c["score"] for c in pruned]
        assert all(s >= 0.45 for s in scores)
        assert 0.9 in scores  # best chunk kept

    def test_prune_context_deduplicates_chapters(self):
        from services.rag_service import prune_context
        chunks = [
            {"score": 0.9, "chapter": "Ch1", "chapter_number": 1, "text": "first",  "token_count": 100},
            {"score": 0.8, "chapter": "Ch1", "chapter_number": 1, "text": "second", "token_count": 100},
            {"score": 0.7, "chapter": "Ch2", "chapter_number": 2, "text": "other",  "token_count": 100},
        ]
        pruned = prune_context(chunks, max_tokens=1500)
        chapter_nums = [c["chapter_number"] for c in pruned]
        assert chapter_nums.count(1) == 1  # only one chunk per chapter

    def test_prune_context_respects_token_limit(self):
        from services.rag_service import prune_context
        chunks = [
            {"score": 0.9, "chapter": f"Ch{i}", "chapter_number": i, "text": f"text{i}", "token_count": 400}
            for i in range(10)
        ]
        pruned = prune_context(chunks, max_tokens=1000)
        total_tokens = sum(c["token_count"] for c in pruned)
        assert total_tokens <= 1000

    def test_build_context_string(self):
        from services.rag_service import build_context_string
        chunks = [
            {"chapter": "Chapter 1", "text": "Some content here.", "score": 0.9},
            {"chapter": "Chapter 2", "text": "More content here.", "score": 0.8},
        ]
        ctx = build_context_string(chunks)
        assert "Chapter 1" in ctx
        assert "Chapter 2" in ctx
        assert "Some content here." in ctx
        assert "[Source 1" in ctx

    def test_question_hash_consistency(self):
        from services.rag_service import question_hash
        h1 = question_hash("What is photosynthesis?", "en")
        h2 = question_hash("What is photosynthesis?", "en")
        h3 = question_hash("What is photosynthesis?", "hi")
        assert h1 == h2          # same question, same hash
        assert h1 != h3          # different language, different hash

    def test_question_hash_case_insensitive(self):
        from services.rag_service import question_hash
        h1 = question_hash("What is photosynthesis?", "en")
        h2 = question_hash("WHAT IS PHOTOSYNTHESIS?", "en")
        assert h1 == h2


# ── Integration-style Tests: LLM Service (mocked) ────────────────────────────

class TestLLMService:
    def test_system_prompts_differ_by_language(self):
        from services.llm_service import SYSTEM_PROMPT_EN, SYSTEM_PROMPT_HI
        assert "JSON" in SYSTEM_PROMPT_EN
        assert "JSON" in SYSTEM_PROMPT_HI
        assert SYSTEM_PROMPT_EN != SYSTEM_PROMPT_HI

    @pytest.mark.asyncio
    async def test_generate_answer_parses_json(self):
        from services.llm_service import generate_answer
        mock_response = '{"simple_explanation":"Plants make food.","example":"Like cooking.","summary":"Food from sun.","practice_question":"What is needed?"}'
        with patch("services.llm_service.call_groq", new=AsyncMock(return_value=mock_response)):
            result = await generate_answer("What is photosynthesis?", "context here", "en")
        assert isinstance(result, dict)
        assert "simple_explanation" in result
        assert result["simple_explanation"] == "Plants make food."

    @pytest.mark.asyncio
    async def test_generate_answer_fallback_on_bad_json(self):
        from services.llm_service import generate_answer
        mock_response = "This is just plain text without JSON structure"
        with patch("services.llm_service.call_groq", new=AsyncMock(return_value=mock_response)):
            result = await generate_answer("question", "context", "en")
        assert isinstance(result, dict)
        assert "simple_explanation" in result  # fallback dict

    @pytest.mark.asyncio
    async def test_generate_quiz_parses_json(self):
        from services.llm_service import generate_quiz
        mock_response = '[{"question":"Q1?","options":["A. opt1","B. opt2","C. opt3","D. opt4"],"correct":"A","explanation":"Because A"}]'
        with patch("services.llm_service.call_groq", new=AsyncMock(return_value=mock_response)):
            result = await generate_quiz("context", 1, "en")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["correct"] == "A"


# ── API Route Tests (TestClient) ──────────────────────────────────────────────

@pytest.fixture
def app_client():
    """Create a test client with mocked DB and embedding model"""
    with patch("utils.db.connect_db", new=AsyncMock()), \
         patch("utils.db.close_db",   new=AsyncMock()), \
         patch("utils.embeddings.load_embedding_model", return_value=None):
        from main import app
        return TestClient(app)


class TestAuthRoutes:
    def test_health_endpoint(self, app_client):
        resp = app_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_register_validates_email(self, app_client):
        with patch("utils.db.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.users.find_one = AsyncMock(return_value=None)
            mock_db.users.insert_one = AsyncMock(return_value=MagicMock(inserted_id="id1"))
            mock_get_db.return_value = mock_db

            resp = app_client.post("/api/auth/register", json={
                "name": "Test User",
                "email": "notanemail",
                "password": "pass123"
            })
            assert resp.status_code == 422  # Pydantic validation error

    def test_register_validates_password_length(self, app_client):
        with patch("utils.db.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.users.find_one = AsyncMock(return_value=None)
            mock_get_db.return_value = mock_db

            resp = app_client.post("/api/auth/register", json={
                "name": "Test",
                "email": "test@test.com",
                "password": "123"  # too short
            })
            assert resp.status_code == 422

    def test_login_wrong_credentials(self, app_client):
        with patch("utils.db.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.users.find_one = AsyncMock(return_value=None)
            mock_get_db.return_value = mock_db

            resp = app_client.post("/api/auth/login", json={
                "email": "wrong@test.com",
                "password": "wrongpass"
            })
            assert resp.status_code == 401

    def test_protected_route_without_token(self, app_client):
        resp = app_client.get("/api/chat/history")
        assert resp.status_code == 403  # No Authorization header


# ── Run summary ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import subprocess
    subprocess.run(["python", "-m", "pytest", __file__, "-v", "--tb=short"])
