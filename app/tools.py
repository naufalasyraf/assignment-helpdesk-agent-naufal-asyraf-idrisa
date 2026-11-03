"""
Modul Tools — fungsi-fungsi "aksi" yang dipanggil router ketika intent
BUKAN pertanyaan informasi/kebijakan, melainkan permintaan spesifik
yang butuh pengecekan data langsung (bukan retrieval semantik).

Pola ini mengikuti konsep Tool Integration di Sesi 12.3.
"""

import pandas as pd

MOCK_TICKETS_PATH = "data/mock_tickets.csv"


def get_ticket_status(ticket_id: str) -> str:
    """Cari status tiket berdasarkan ticket_id di mock_tickets.csv."""
    if not ticket_id:
        return "ID tiket tidak ditemukan di pertanyaan. Sertakan ID dengan format TICKET-XXXX."

    try:
        df = pd.read_csv(MOCK_TICKETS_PATH)
    except FileNotFoundError:
        return "Data tiket sedang tidak bisa diakses. Coba lagi nanti."

    match = df[df["ticket_id"].astype(str).str.strip().str.upper() == ticket_id.strip().upper()]

    if match.empty:
        return f"Tiket {ticket_id} tidak ditemukan di sistem. Coba cek lagi ID tiketnya."

    row = match.iloc[0]
    return (
        f"Tiket {row['ticket_id']}: {row['subject']}. "
        f"Status: {row['status']}. "
        f"Update terakhir: {row['last_update']}."
    )
