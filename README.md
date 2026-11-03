# IT Helpdesk Assistant

Asisten helpdesk internal yang bisa menjawab dua jenis pertanyaan karyawan:
pertanyaan kebijakan/prosedur (menggunakan RAG) dan cek status tiket (menggunakan tool call).
Backend-nya FastAPI, dan semuanya dijalankan di dalam container Docker.

## Problem Statement

Tim People & IT Operations tiap hari kebanjiran pertanyaan yang berulang, misalnya
"berapa jatah cuti saya?" atau "gimana cara reset password VPN?". Ada juga yang
nanya status tiket tertentu, misalnya "status TICKET-0005 gimana?".

Dua jenis pertanyaan ini butuh cara jawab yang beda. Pertanyaan kebijakan dijawab
dari knowledge base lewat semantic search, sedangkan status tiket harus dicek
langsung ke data tiket. Aplikasi ini mengenali mana yang mana, lalu memakai jalur
yang sesuai.

## Desain Workflow

```
User kirim query ke POST /ask
        |
      Router (deteksi intent)
      /          |           \
   faq     ticket_status    unknown
    |            |              |
   RAG       Tool call      Pesan "tidak
 (FAISS +   (cari ticket_id  paham" yang
  Gemini)    di CSV tiket)   sopan
    \            |
     Response JSON: status, intent, data
```

Cara router menentukan intent:
1. Kalau di kalimat ada pola `TICKET-xxxx`, langsung dianggap `ticket_status`.
2. Kalau tidak ada, pertanyaan dikirim ke Gemini untuk diklasifikasi ke
   `faq`, `ticket_status`, atau `unknown`.
3. Kalau Gemini gagal atau jawabannya tidak valid, router pakai keyword
   sederhana sebagai cadangan.

Alur RAG: tiap entri FAQ digabung jadi teks `Q: ... A: ...`, di-embed pakai
`gemini-embedding-001`, lalu disimpan di index FAISS. Saat ada pertanyaan,
diambil 3 FAQ terdekat sebagai context, lalu dimasukkan ke prompt
(Persona, Task, Context, Format) untuk dijawab `gemini-3-flash-preview`.
Index dibangun sekali saat aplikasi start, bukan di tiap request.

## Struktur Project

```
app/
├── main.py       # Entry point FastAPI, berisi endpoint /ask dan /health
├── router.py     # Intent detection + routing ke RAG atau tool call
├── rag.py        # Modul RAG: embedding, FAISS, semantic search, LLM answer
└── tools.py      # Modul tool call: pengecekan status tiket

data/
├── it_helpdesk_knowledge_base.csv   # Knowledge base untuk RAG
└── mock_tickets.csv                 # Data mock untuk tool call

Dockerfile
.dockerignore
.env.example                         # Contoh isi .env (tanpa key asli)
requirements.txt
```

## Menjalankan Secara Lokal (tanpa Docker)

Siapkan file `.env` di root project:
add folder .env di root project
Lalu isi `GEMINI_API_KEY` di dalam `.env`. Setelah itu:

```bash
python -m venv venv
venv\Scripts\activate        # Windows (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Menjalankan dengan Docker

```bash
docker build -t helpdesk-agent .
docker run -p 8000:8000 --env-file .env helpdesk-agent
```

API key dipasang lewat environment variable saat container dijalankan, jadi
tidak ada key yang masuk ke dalam image. Tunggu sampai muncul log
`Index FAISS siap dipakai` sebelum mencoba endpoint.

## Menguji Endpoint

Cara paling gampang lewat Swagger UI: buka `http://127.0.0.1:8000/docs`, klik
**POST /ask**, **Try it out**, isi query, lalu **Execute**.

Atau pakai curl:

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "berapa jatah cuti tahunan saya?"}'
```

Format response:

```json
{
  "status": "success",
  "intent": "faq",
  "data": "Karyawan tetap mendapatkan jatah 12 hari cuti tahunan. ..."
}
```

## Hasil Pengujian

| # | Jenis | Query | Intent | Hasil |
|---|-------|-------|--------|-------|
| 1 | FAQ | Berapa jatah cuti tahunan karyawan tetap? | faq | Jawaban benar: 12 hari cuti, bisa diambil setelah masa kerja minimal 3 bulan |
| 2 | FAQ | Gimana cara reset password VPN? | faq | Dijawab dari FAQ: reset lewat portal self-service, kalau akun terkunci hubungi IT Support |
| 3 | Tiket ada | Apa status TICKET-0005? | ticket_status | Tiket ketemu: reset password VPN gagal terus, status Diproses, update terakhir 2026-08-27 |
| 4 | Tiket tidak ada | Cek status TICKET-0042 | ticket_status | Muncul pesan tiket tidak ditemukan, aplikasi tidak error |
| 5 | Di luar cakupan | Cuaca hari ini gimana? | unknown | Ditolak dengan sopan dan diarahkan ke topik yang bisa dibantu |
| 6 | Tiket tanpa ID | mau cek status tiket atas nama Bayu Aji dong | ticket_status | Diminta menyertakan ID tiket (format TICKET-XXXX) |

Observasi:
- Router tidak cuma melihat kata kunci. Query nomor 2 menyebut VPN, padahal ada
  tiket soal VPN juga (TICKET-0005), tapi karena yang ditanya cara reset, query
  itu tetap diarahkan ke FAQ.
- Query tiket yang ID-nya tidak ada ditangani dengan pesan biasa, tidak sampai
  bikin aplikasi crash.
- Query di luar cakupan tidak dipaksa masuk ke RAG, jadi tidak ada jawaban
  ngarang soal cuaca.
- Query nomor 6 dikenali sebagai cek tiket, tapi tool hanya bisa mencari lewat
  ID, jadi user diminta menyebutkan ID tiketnya.
- Semua pengujian di atas dijalankan lagi dari dalam container Docker dan
  hasilnya sama.

## Keterbatasan

- Cek tiket cuma bisa lewat ID. Mencari berdasarkan nama atau subjek belum
  didukung, dan kalau ada lebih dari satu ID di satu kalimat, hanya yang
  pertama yang dicek.
- Data tiket masih mock dari file CSV dan belum ada autentikasi, jadi di
  sistem sungguhan siapa saja bisa mengecek tiket siapa saja.
- Semantic search selalu mengambil 3 hasil teratas, walaupun tidak ada yang
  benar-benar cocok. Belum ada batas jarak (threshold), jadi LLM yang
  menentukan informasinya ada atau tidak.
- Satu pertanyaan FAQ bisa memakai beberapa panggilan ke Gemini (klasifikasi,
  embedding, jawaban), jadi respons bisa lambat dan terkena batas kuota.
- Index FAISS dibangun ulang tiap aplikasi start dan tidak disimpan ke disk.
- Tidak ada memori percakapan, tiap pertanyaan diproses terpisah.
- Jawaban LLM bisa sedikit berbeda tiap kali ditanya, walaupun isinya sama.
- ID tiket hanya dikenali kalau ditulis dengan kata "TICKET" di depannya
  (misal `TICKET-0005`). Penulisan lain seperti "tiket nomor 5" belum dikenali.