"""
Input Validation & Sanitization Utilities
==========================================
Central place for all input-level security checks.
"""

import re
import os
from typing import Optional
from fastapi import HTTPException


# ── Text sanitization ─────────────────────────────────────────────────────────

def sanitize_text(text: str, max_length: int = 2000) -> str:
    """
    Strip control characters, excessive whitespace, and truncate.
    """
    # Remove null bytes and control chars (except newline/tab)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # Normalise whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Truncate
    return text[:max_length]


def sanitize_question(question: str) -> str:
    """Sanitize a student question for LLM submission."""
    text = sanitize_text(question, max_length=1000)
    if len(text) < 3:
        raise HTTPException(status_code=400, detail="Question is too short")
    if len(text) > 1000:
        raise HTTPException(status_code=400, detail="Question is too long (max 1000 chars)")
    return text


def sanitize_filename(filename: str) -> str:
    """
    Clean a filename to prevent path traversal.
    """
    # Extract basename only
    filename = os.path.basename(filename)
    # Only allow safe characters
    filename = re.sub(r'[^\w\-_\. ]', '_', filename)
    # Max 200 chars
    return filename[:200]


# ── File validation ───────────────────────────────────────────────────────────

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "application/octet-stream",  # some browsers send this for PDFs
}

PDF_MAGIC_BYTES = b'%PDF'


def validate_pdf_file(filename: str, content_type: str, file_bytes: bytes) -> None:
    """
    Validates a PDF upload:
    1. Extension check
    2. MIME type check (with fallback)
    3. Magic bytes check (actual file header)
    4. Size check
    """
    # 1. Extension
    if not filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only PDF files are allowed."
        )

    # 2. MIME type (relaxed — browsers are inconsistent)
    if content_type and content_type not in ALLOWED_MIME_TYPES and 'pdf' not in content_type:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid MIME type: {content_type}. Expected PDF."
        )

    # 3. Magic bytes — actual content check
    if len(file_bytes) < 4 or file_bytes[:4] != PDF_MAGIC_BYTES:
        raise HTTPException(
            status_code=400,
            detail="File does not appear to be a valid PDF (bad magic bytes)."
        )

    # 4. Minimum size — reject trivially small files
    if len(file_bytes) < 1024:
        raise HTTPException(
            status_code=400,
            detail="PDF file is too small or corrupt."
        )


# ── Query parameter validation ────────────────────────────────────────────────

def validate_object_id(id_str: str, field_name: str = "id") -> str:
    """Validate a MongoDB ObjectId string (24 hex chars)."""
    if not re.match(r'^[a-f0-9]{24}$', id_str, re.IGNORECASE):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}: must be a 24-character hex string"
        )
    return id_str


def validate_language(lang: str) -> str:
    """Validate supported language code."""
    supported = {"en", "hi"}
    if lang not in supported:
        return "en"  # default gracefully
    return lang


def validate_pagination(limit: int, skip: int) -> tuple:
    """Clamp pagination values to safe ranges."""
    limit = max(1, min(limit, 100))
    skip  = max(0, min(skip, 10000))
    return limit, skip


# ── Prompt injection guard ────────────────────────────────────────────────────

INJECTION_PATTERNS = [
    r'ignore (previous|all|above) instructions',
    r'system prompt',
    r'you are now',
    r'pretend (you are|to be)',
    r'roleplay as',
    r'forget your',
    r'jailbreak',
    r'DAN mode',
    r'act as (an? )?(unrestricted|evil|hacker)',
]

_INJECTION_RE = re.compile(
    '|'.join(INJECTION_PATTERNS),
    re.IGNORECASE
)


def check_prompt_injection(text: str) -> None:
    """
    Detect obvious prompt injection attempts.
    Raises HTTP 400 if suspicious patterns found.
    """
    if _INJECTION_RE.search(text):
        raise HTTPException(
            status_code=400,
            detail="Question contains disallowed content. Please ask an educational question."
        )
