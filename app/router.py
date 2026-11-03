"""
Router — menentukan apakah query user butuh RAG (informasi/kebijakan)
atau tool call (aksi spesifik, misal cek status tiket).

Pola ini mengikuti workflow router yang sudah dipelajari di Sesi 12.4:
  user input -> intent detection -> jika butuh data -> retrieval (RAG)
                                  -> jika butuh aksi -> tool call
"""
import os
import re

from dotenv import load_dotenv
from google import genai

from app.rag import answer_from_knowledge_base
from app.tools import get_ticket_status

load_dotenv()

_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
LLM_MODEL = "gemini-3-flash-preview"

TICKET_PATTERN = re.compile(r"TICKET[-\s]?(\d{1,4})", re.IGNORECASE)
TICKET_KEYWORDS = ["status tiket", "cek tiket", "tiket saya", "ticket saya", "status ticket"]
VALID_INTENTS = ("faq", "ticket_status", "unknown")

async def detect_intent(query: str) -> str:
    """Kembalikan 'faq', 'ticket_status', atau 'unknown'."""
    if TICKET_PATTERN.search(query):
        return "ticket_status"

    prompt = f"""Klasifikasikan pertanyaan berikut ke dalam salah satu kategori:
- 'faq': pertanyaan informasi/kebijakan perusahaan (cuti, akses, password, perangkat, dll)
- 'ticket_status': permintaan mengecek status tiket tertentu
- 'unknown': di luar cakupan helpdesk atau tidak jelas maksudnya
Jawab hanya dengan satu kata.
Pertanyaan: {query}"""

    try:
        response = await _client.aio.models.generate_content(
            model=LLM_MODEL,
            contents=prompt,
        )
        label = response.text.strip().strip("'\".").lower()
        if label in VALID_INTENTS:
            return label
    except Exception:
        pass 

    if any(k in query.lower() for k in TICKET_KEYWORDS):
        return "ticket_status"
    return "faq"


def extract_ticket_id(query: str) -> str:
    """Ambil ticket_id dari kalimat dan rapikan jadi format TICKET-XXXX."""
    match = TICKET_PATTERN.search(query)
    if not match:
        return ""
    return f"TICKET-{int(match.group(1)):04d}"


async def handle_query(query: str) -> dict:
    """Dipanggil endpoint /ask: deteksi intent lalu rutekan ke RAG atau tool."""
    intent = await detect_intent(query)

    if intent == "ticket_status":
        ticket_id = extract_ticket_id(query)
        data = get_ticket_status(ticket_id)
        return {"status": "success", "intent": "ticket_status", "data": data}

    elif intent == "faq":
        data = await answer_from_knowledge_base(query)
        return {"status": "success", "intent": "faq", "data": data}

    else:
        return {
            "status": "error",
            "intent": "unknown",
            "data": "Maaf, saya tidak memahami permintaan Anda. Coba tanyakan seputar kebijakan IT/HR atau cek status tiket (format TICKET-XXXX).",
        }