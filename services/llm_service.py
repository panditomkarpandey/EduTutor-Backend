import os
import httpx
import json

# Groq settings
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-8b-8192")

LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))

SYSTEM_PROMPT_EN = """You are an expert educational tutor for Indian school students.
You help students understand textbook concepts clearly and simply.
Always respond in this exact JSON structure:
{
  "simple_explanation": "Clear explanation in simple language",
  "example": "A relatable real-world example",
  "summary": "1-2 sentence summary",
  "practice_question": "One practice question to test understanding"
}
Base your answer ONLY on the provided context."""

SYSTEM_PROMPT_HI = """आप भारतीय स्कूली छात्रों के लिए एक विशेषज्ञ शैक्षिक ट्यूटर हैं।
हमेशा इस JSON संरचना में उत्तर दें:
{
  "simple_explanation": "सरल भाषा में स्पष्ट व्याख्या",
  "example": "एक संबंधित वास्तविक उदाहरण",
  "summary": "1-2 वाक्य सारांश",
  "practice_question": "समझ परखने के लिए एक प्रश्न"
}
केवल दिए गए संदर्भ के आधार पर उत्तर दें।"""

QUIZ_PROMPT_EN = """Generate exactly {n} multiple choice questions from the following educational content.
Return ONLY a JSON array:
[
  {{
    "question": "Question text",
    "options": ["A. option1", "B. option2", "C. option3", "D. option4"],
    "correct": "A",
    "explanation": "Why this answer is correct"
  }}
]"""


async def call_groq(prompt: str, system: str, temperature: float = 0.3) -> str:
    """Call Groq API"""
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set in environment variables")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": 1024,
    }

    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        resp = await client.post(GROQ_BASE_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def call_llm(prompt: str, system: str, temperature: float = 0.3) -> str:
    """Call Groq."""
    return await call_groq(prompt, system, temperature)


async def generate_answer(question: str, context: str, language: str = "en") -> dict:
    """Generate structured answer using RAG context"""
    system = SYSTEM_PROMPT_HI if language == "hi" else SYSTEM_PROMPT_EN

    if language == "hi":
        prompt = f"संदर्भ:\n{context}\n\nछात्र का प्रश्न: {question}\n\nJSON में उत्तर दें:"
    else:
        prompt = f"Context:\n{context}\n\nStudent Question: {question}\n\nRespond in JSON:"

    try:
        raw = await call_llm(prompt, system, temperature=0.3)
        start = raw.find('{')
        end   = raw.rfind('}') + 1
        if start != -1 and end > start:
            return json.loads(raw[start:end])
    except (json.JSONDecodeError, ValueError, Exception):
        pass

    return {
        "simple_explanation": raw.strip() if 'raw' in dir() else "Unable to generate answer",
        "example": "Please refer to your textbook for examples.",
        "summary": "Answer provided above.",
        "practice_question": "Can you explain this concept in your own words?"
    }


async def generate_quiz(context: str, num_questions: int = 5, language: str = "en") -> list:
    """Generate quiz questions from context"""
    system = "You are an expert quiz generator. Return ONLY valid JSON array."
    prompt = f"{QUIZ_PROMPT_EN.format(n=num_questions)}\n\nContent:\n{context}"

    try:
        raw = await call_llm(prompt, system, temperature=0.4)
        start = raw.find('[')
        end   = raw.rfind(']') + 1
        if start != -1 and end > start:
            return json.loads(raw[start:end])
    except Exception:
        pass
    return []


async def check_llm_health() -> bool:
    """Check if Groq is reachable."""
    try:
        if not GROQ_API_KEY:
            return False
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"}
            )
            return resp.status_code == 200
    except Exception:
        return False
