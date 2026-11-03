"""
Entry point aplikasi FastAPI — IT Helpdesk Assistant.

Alur endpoint utama:
  1. Menerima pertanyaan/permintaan dari user
  2. Meneruskan ke router (router.py) untuk menentukan intent
  3. Router memanggil RAG (rag.py) atau tool (tools.py) sesuai intent
  4. Mengembalikan response terstruktur ke client
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.rag import build_index
from app.router import handle_query

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await asyncio.to_thread(build_index)
        logger.info("Index FAISS siap dipakai.")
    except Exception:
        logger.exception("Gagal membangun index saat startup.")
    yield


app = FastAPI(title="IT Helpdesk Assistant API", lifespan=lifespan)


class AskRequest(BaseModel):
    query: str


class AskResponse(BaseModel):
    status: str
    intent: str
    data: str


def _error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "intent": "unknown", "data": message},
    )


@app.get("/health")
async def health():
    """Endpoint sederhana untuk memastikan service berjalan."""
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """
    Endpoint utama. Menerima pertanyaan bebas dari user (informasi/kebijakan
    ATAU cek status tiket), lalu meneruskannya ke router untuk diproses.
    """
    if not request.query.strip():
        return _error_response(400, "Pertanyaan tidak boleh kosong.")

    try:
        result = await handle_query(request.query)
        return AskResponse(**result)
    except Exception:
        logger.exception("Gagal memproses query: %s", request.query)
        return _error_response(
            503,
            "Maaf, layanan sedang bermasalah. Silakan coba lagi beberapa saat lagi.",
        )
