import re
import io
from typing import List, Dict, Tuple
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTChar

MAX_CHUNK_TOKENS = 700
MIN_CHUNK_TOKENS = 100
OVERLAP_TOKENS = 50

CHAPTER_PATTERNS = [
    r'^chapter\s+(\d+|[ivxlcdm]+)[:\.\s]',
    r'^unit\s+(\d+)[:\.\s]',
    r'^lesson\s+(\d+)[:\.\s]',
    r'^section\s+(\d+)[:\.\s]',
    r'^अध्याय\s+(\d+)',   # Hindi
    r'^पाठ\s+(\d+)',       # Hindi
]


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token"""
    return len(text) // 4


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract all text from PDF bytes"""
    from pdfminer.high_level import extract_text
    return extract_text(io.BytesIO(file_bytes))


def detect_chapter(line: str) -> Tuple[bool, str]:
    """Detect if a line is a chapter heading"""
    line_lower = line.strip().lower()
    for pattern in CHAPTER_PATTERNS:
        if re.match(pattern, line_lower, re.IGNORECASE):
            return True, line.strip()
    # Heuristic: short uppercase line likely a heading
    if len(line.strip()) < 80 and line.strip().isupper() and len(line.strip()) > 3:
        return True, line.strip()
    return False, ""


def split_into_chapters(text: str) -> List[Dict]:
    """Split text into chapters with metadata"""
    lines = text.split('\n')
    chapters = []
    current_chapter = {"title": "Introduction", "number": 0, "content": []}
    chapter_num = 0

    for line in lines:
        is_chapter, chapter_title = detect_chapter(line)
        if is_chapter:
            if current_chapter["content"]:
                chapters.append(current_chapter)
            chapter_num += 1
            current_chapter = {
                "title": chapter_title,
                "number": chapter_num,
                "content": []
            }
        else:
            stripped = line.strip()
            if stripped:
                current_chapter["content"].append(stripped)

    if current_chapter["content"]:
        chapters.append(current_chapter)

    return chapters if chapters else [{"title": "Full Text", "number": 1, "content": lines}]


def chunk_text(text: str, max_tokens: int = MAX_CHUNK_TOKENS, overlap: int = OVERLAP_TOKENS) -> List[str]:
    """Split text into overlapping chunks by token estimate"""
    words = text.split()
    chunks = []
    start = 0

    while start < len(words):
        # Estimate token limit by word count (~1.3 words per token)
        word_limit = int(max_tokens * 1.3)
        end = min(start + word_limit, len(words))
        chunk = ' '.join(words[start:end])

        if estimate_tokens(chunk) >= MIN_CHUNK_TOKENS:
            chunks.append(chunk)

        if end >= len(words):
            break

        overlap_words = int(overlap * 1.3)
        start = end - overlap_words

    return chunks


def process_pdf(file_bytes: bytes) -> List[Dict]:
    """
    Full pipeline: PDF bytes → list of chunk dicts with metadata
    Returns list of: {chapter, chapter_number, chunk_index, text, token_count}
    """
    raw_text = extract_text_from_pdf(file_bytes)
    chapters = split_into_chapters(raw_text)

    all_chunks = []
    global_chunk_idx = 0

    for chapter in chapters:
        chapter_text = ' '.join(chapter["content"])
        if not chapter_text.strip():
            continue

        chunks = chunk_text(chapter_text)
        for i, chunk in enumerate(chunks):
            all_chunks.append({
                "chapter": chapter["title"],
                "chapter_number": chapter["number"],
                "chunk_index": global_chunk_idx,
                "text": chunk,
                "token_count": estimate_tokens(chunk)
            })
            global_chunk_idx += 1

    return all_chunks
