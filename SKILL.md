---
name: pddikti-lookup
description: Batch lookup and verification of Indonesian university student records on PDDikti (pddikti.kemdiktisaintek.go.id) using Playwright (headed Chrome). Use when verifying student enrollment year, NIM, university, study program, S1/S2/S3 status, or updating scholarship/applicant Excel lists with PDDikti results.
---

# PDDikti Batch Lookup & Verification Skill

Otomasi pencarian dan verifikasi data mahasiswa di [PDDikti](https://pddikti.kemdiktisaintek.go.id/) menggunakan **Playwright (headed Chrome)** tanpa membakar token AI untuk setiap klik.

## Mengapa Strategi Ini?
- Endpoint API PDDikti (`api-pddikti.kemdiktisaintek.go.id`) mengembalikan `HTTP 403` jika diakses langsung lewat `curl`/`requests`.
- Mode `headless=True` di Playwright juga memicu `Terjadi Kesalahan` pada halaman pencarian PDDikti.
- **Solusi teruji:** Gunakan `channel="chrome"` dengan **`headless=False`** (browser terlihat), tunggu hidrasi *skeleton* (`...`) selesai pada halaman `/detail-mahasiswa/`, dan beri jeda sopan antar permintaan.

## Prasyarat Environment
```bash
python3 -m venv .venv
.venv/bin/pip install -r scripts/requirements.txt
```
*(Menggunakan Google Chrome yang sudah terpasang di sistem via `channel="chrome"`, sehingga tidak perlu mengunduh binary Chromium tambahan.)*

## Alur Kerja

### 1. Siapkan Input CSV
Buat file CSV dengan header:
```csv
nama,target_jenjang,filter_pt,filter_prodi
Abghiya Fadhilah Rahmi,S1,Sunan Gunung Djati,Alquran|Hadis
Ahmad Muthian Qowamma,S2,Padjadjaran,Hukum
```
**Tips Filter PDDikti:**
- Di PDDikti, nama perguruan tinggi ditulis lengkap (mis. `Universitas Islam Negeri Sunan Gunung Djati`, `Institut Teknologi Bandung`, `Universitas Pendidikan Indonesia`, `Universitas Padjadjaran`) — jangan gunakan singkatan seperti `UIN` atau `ITB` di `filter_pt`.
- Gunakan `|` untuk variasi kata kunci (mis. `Alquran|Hadis|Tafsir`).
- Jika pencarian dengan singkatan nama (mis. `M. Rizki`) tidak ditemukan, coba ubah menjadi `Muhammad Rizki` atau naikkan `--max-pages 5`.
- PDDikti hanya mencatat PT **dalam negeri**; untuk target S3 luar negeri, kosongkan `filter_pt` untuk mengecek riwayat S1/S2 dalam negeri jika ada.

### 2. Jalankan Pencarian Batch
```bash
.venv/bin/python scripts/pddikti_lookup.py \
  --input input.csv \
  --output output.csv \
  --max-pages 3 \
  --max-details 5 \
  --delay 1.0
```
- Mendukung **`--resume`** untuk melanjutkan jika terhenti (melewati `query_nama` yang sudah ada di `output.csv`).
- Jika muncul CAPTCHA / verifikasi Cloudflare di jendela Chrome, selesaikan secara manual di jendela browser (jangan mencoba mem-bypass proteksi anti-bot).

### 3. Perbarui File Excel (Opsional, Format 3 Sheet)
Untuk memperbarui daftar Excel tanpa mengubah susunan baris asli:
```bash
.venv/bin/python scripts/update_excel.py \
  --excel "/path/to/daftar.xlsx" \
  --csv output.csv
```
Skrip akan mempertahankan `Sheet1` secara utuh, lalu membuat:
- `Hasil_PDDikti`: Seluruh baris kandidat mentah dari PDDikti.
- `Verifikasi_Beasiswa`: Salinan `Sheet1` dengan header di baris 1, urutan data tetap, kolom hasil PDDikti (`C–K`), serta highlight **Hijau** (yakin cocok) dan **Kuning** (mirip/perlu cek ulang) pada kolom Nama.
