"""
Modul RAG — mengubah knowledge base menjadi embedding, menyimpannya ke FAISS,
melakukan semantic search, lalu menghasilkan jawaban menggunakan LLM.

Alur ini serupa dengan yang sudah dibangun di Assignment 3 (Semantic Search &
LLM Application) dan Sesi 11 (Building a Simple RAG System) — di assignment ini,
alur tersebut dibungkus menjadi fungsi yang dipanggil oleh router.py.

Modul RAG — knowledge base -> embedding -> FAISS -> semantic search -> jawaban LLM.

"""
import asyncio
import os

import faiss
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

KNOWLEDGE_BASE_PATH = "data/it_helpdesk_knowledge_base.csv"
EMBEDDING_MODEL = "gemini-embedding-001"
LLM_MODEL = "gemini-3-flash-preview"

_index = None
_df = None


def _get_embedding(text: str):
    result = _client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
    )
    return result.embeddings[0].values


def build_index():
    """Baca CSV -> gabung question+answer -> embedding -> simpan ke FAISS."""
    global _index, _df

    df = pd.read_csv(KNOWLEDGE_BASE_PATH)
    df["content"] = "Q: " + df["question"] + " A: " + df["answer"]

    embeddings = [_get_embedding(doc) for doc in df["content"].tolist()]
    embeddings = np.array(embeddings).astype("float32")

    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)

    _df = df
    _index = index


def _ensure_index():
    if _index is None:
        build_index()


def semantic_search(query: str, top_k: int = 3):
    """Ambil top_k entri FAQ paling relevan untuk query."""
    _ensure_index()

    query_embedding = np.array([_get_embedding(query)]).astype("float32")
    distances, indices = _index.search(query_embedding, top_k)

    results = []
    for rank, idx in enumerate(indices[0]):
        if idx < 0:
            continue
        row = _df.iloc[idx]
        results.append({
            "rank": rank + 1,
            "question": row["question"],
            "answer": row["answer"],
            "category": row["category"],
            "distance": float(distances[0][rank]),
        })
    return results


def _build_prompt(query: str, search_results: list) -> str:
    context = "\n\n".join(
        f"FAQ: {r['question']}\nJawaban: {r['answer']}" for r in search_results
    )
    return f"""Persona: Kamu adalah asisten IT Helpdesk internal perusahaan yang ramah dan membantu karyawan.

Task: Jawab pertanyaan karyawan HANYA berdasarkan informasi FAQ pada bagian Context. Jika informasinya tidak ada di FAQ, katakan bahwa kamu belum punya informasi tersebut dan sarankan menghubungi tim IT Support. Jangan mengarang.

Context:
{context}

Pertanyaan karyawan: {query}

Format: Jawab dalam bahasa Indonesia, singkat dan jelas (maksimal 3-4 kalimat), langsung ke inti tanpa pembukaan yang panjang.

Jawaban:"""


async def answer_from_knowledge_base(query: str) -> str:
    """Dipanggil router saat intent = 'faq'."""
    results = await asyncio.to_thread(semantic_search, query, 3)
    prompt = _build_prompt(query, results)

    response = await _client.aio.models.generate_content(
        model=LLM_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.3),
    )

    if not response.text:
        raise RuntimeError("LLM tidak mengembalikan jawaban")
    return response.text