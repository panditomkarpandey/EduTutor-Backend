import os
import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from api.auth      import router as auth_router
from api.admin     import router as admin_router
from api.chat      import router as chat_router
from api.quiz      import router as quiz_router
from api.search    import router as search_router
from api.analytics import router as analytics_router
from api.progress  import router as progress_router
from utils.db         import connect_db, close_db
from utils.logger     import setup_logging
from utils.config     import settings, validate_config
from dotenv import load_dotenv

load_dotenv()

setup_logging()
log = logging.getLogger("main")

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=" * 55)
    log.info("  Education Tutor for Remote India  v1.0.0")
    log.info("=" * 55)
    validate_config()
    t0 = time.monotonic()
    await connect_db()
    log.info("MongoDB connected")
    log.info("Embedding model will be loaded lazily on first use")
    elapsed = time.monotonic() - t0
    log.info(f"Ready in {elapsed:.2f}s -> http://localhost:8000/docs")
    yield
    log.info("Shutting down...")
    await close_db()
    log.info("Goodbye")


app = FastAPI(
    title="Education Tutor for Remote India",
    description="AI-powered RAG tutoring platform for rural students.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.monotonic()
    response = await call_next(request)
    ms = (time.monotonic() - t0) * 1000
    log.info(f"{request.method} {request.url.path} -> {response.status_code} ({ms:.0f}ms)")
    return response


from fastapi import HTTPException

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    origin = request.headers.get("origin", "")
    headers = {}
    if origin in settings.allowed_origins_list:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers,
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    origin = request.headers.get("origin", "")
    headers = {}
    if origin in settings.allowed_origins_list:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again."},
        headers=headers,
    )


app.include_router(auth_router,      prefix="/api/auth",      tags=["Authentication"])
app.include_router(admin_router,     prefix="/api/admin",     tags=["Admin"])
app.include_router(chat_router,      prefix="/api/chat",      tags=["Chat / RAG"])
app.include_router(quiz_router,      prefix="/api/quiz",      tags=["Quiz"])
app.include_router(search_router,    prefix="/api/search",    tags=["Search"])
app.include_router(analytics_router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(progress_router,  prefix="/api/progress",  tags=["Progress"])


@app.get("/health", tags=["System"])
async def health():
    from utils.db import get_db
    db_ok = False
    try:
        db = get_db()
        await db.command("ping")
        db_ok = True
    except Exception:
        pass
    return {
        "status":  "ok" if db_ok else "degraded",
        "db":      "connected" if db_ok else "unavailable",
        "service": "Education Tutor API",
        "version": "1.0.0",
    }


@app.get("/api/info", tags=["System"])
async def api_info():
    return {
        "name":      "Education Tutor for Remote India",
        "version":   "1.0.0",
        "embedding": "all-MiniLM-L6-v2 (384-dim)",
        "llm":       "groq/llama3-8b-8192",
        "languages": ["en", "hi"],
        "boards":    ["CBSE", "ICSE", "State", "NIOS"],
    }
