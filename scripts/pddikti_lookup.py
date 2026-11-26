"""Batch lookup mahasiswa di PDDikti menggunakan Playwright (headed Chrome).

Mendukung:
- Filter opsional: filter_jenjang (S1/S2/S3), filter_pt, filter_prodi
- Fallback cerdas: jika filter_pt + filter_prodi tidak ada yang cocok, fallback ke filter_pt saja
- Incremental save & --resume agar progres aman untuk ratusan nama
"""

import argparse
import csv
import json
import time
import urllib.parse
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://pddikti.kemdiktisaintek.go.id"

BIODATA_LABELS = [
    "Nama",
    "Perguruan Tinggi",
    "Jenis Kelamin",
    "Tanggal Masuk",
    "NIM",
    "Jenjang - Program Studi",
    "Status Awal Mahasiswa",
    "Status Terakhir Mahasiswa",
]

JENJANG_MAP = {
    "S1": "sarjana",
    "S2": "magister",
    "S3": "doktor",
    "D3": "d3",
    "D4": "d4",
}

FIELDNAMES = [
    "query_nama",
    "target_jenjang",
    "filter_pt",
    "filter_prodi",
    "nama",
    "nim",
    "perguruan_tinggi",
    "jenjang_prodi",
    "cocok_jenjang",
    "jenis_kelamin",
    "tanggal_masuk",
    "status_awal",
    "status_terakhir",
    "detail_url",
]


def wait_for_search_results(page, timeout_ms: int = 12000) -> None:
    """Tunggu hingga hasil pencarian Mahasiswa atau pesan kosong muncul."""
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        if page.locator('a[href*="/detail-mahasiswa/"]').count() > 0:
            return
        body = page.inner_text("body")
        if "Tidak ada hasil pencarian" in body and "Mahasiswa" in body:
            page.wait_for_timeout(1000)
            return
        if "Terjadi Kesalahan" in body:
            page.wait_for_timeout(1000)
        page.wait_for_timeout(350)


def extract_search_rows(page) -> list[dict]:
    """Ekstrak baris tabel Mahasiswa dari halaman pencarian saat ini."""
    rows_data = []
    links = page.locator('a[href*="/detail-mahasiswa/"]').all()
    for link in links:
        href = link.get_attribute("href") or ""
        tr = link.locator("xpath=ancestor::tr[1]")
        if tr.count() == 0:
            continue
        cells = [c.inner_text().strip() for c in tr.locator("td").all()]
        if len(cells) >= 4:
            rows_data.append(
                {
                    "nama": cells[0],
                    "nim": cells[1],
                    "perguruan_tinggi": cells[2],
                    "program_studi": cells[3],
                    "detail_url": urllib.parse.urljoin(BASE_URL, href),
                }
            )
    return rows_data


def _match_tokens(value: str, pattern: str) -> bool:
    if not pattern:
        return True
    tokens = [t.strip().lower() for t in pattern.split("|") if t.strip()]
    val_low = value.lower()
    return any(tok in val_low for tok in tokens)


def extract_student_detail(page, detail_url: str) -> dict:
    """Buka halaman detail mahasiswa dan ekstrak seluruh field Biodata Mahasiswa."""
    page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
    try:
        page.wait_for_selector("text=Biodata Mahasiswa", timeout=10000)
    except PlaywrightTimeoutError:
        pass

    detail = {label: "" for label in BIODATA_LABELS}
    deadline = time.time() + 6.0
    while time.time() < deadline:
        lines = [line.strip() for line in page.inner_text("body").splitlines() if line.strip()]
        detail = {label: "" for label in BIODATA_LABELS}
        for i, line in enumerate(lines):
            if line in detail and i + 1 < len(lines):
                next_val = lines[i + 1]
                if next_val not in detail:
                    detail[line] = next_val
        if detail["Nama"] and detail["Nama"] != "...":
            break
        page.wait_for_timeout(400)

    detail["Detail URL"] = detail_url
    return detail


def check_jenjang_match(jenjang_prodi: str, target_jenjang: str) -> str:
    """Periksa kecocokan jenjang (S1/S2/S3) terhadap string 'Jenjang - Program Studi'."""
    if not target_jenjang:
        return ""
    expected = JENJANG_MAP.get(target_jenjang.upper(), target_jenjang.lower())
    return "Ya" if expected in jenjang_prodi.lower() else "Tidak"


def search_student(
    page,
    nama: str,
    target_jenjang: str = "",
    filter_pt: str = "",
    filter_prodi: str = "",
    max_pages: int = 3,
    max_details: int = 5,
) -> list[dict]:
    """Cari satu nama mahasiswa di PDDikti dan ambil detail kandidat yang cocok."""
    search_url = f"{BASE_URL}/search/{urllib.parse.quote(nama)}"
    page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    wait_for_search_results(page)

    all_rows = []
    seen_urls = set()

    for _ in range(max_pages):
        rows = extract_search_rows(page)
        for r in rows:
            if r["detail_url"] not in seen_urls:
                seen_urls.add(r["detail_url"])
                all_rows.append(r)

        # Jika ada filter PT dan sudah ada kandidat PT yang cocok di halaman ini, hentikan pagination
        if filter_pt and any(_match_tokens(r["perguruan_tinggi"], filter_pt) for r in all_rows):
            break
        if not filter_pt and not filter_prodi and len(all_rows) >= max_details:
            break

        next_btn = page.locator('button:has-text(">"), button[aria-label*="next" i]').first
        if next_btn.count() == 0 or not next_btn.is_enabled():
            break
        next_btn.click()
        page.wait_for_timeout(1600)

    # Prioritas filter: PT + Prodi -> PT saja -> Prodi saja -> Semua (terbatas max_details)
    pt_prodi_matches = [
        r
        for r in all_rows
        if _match_tokens(r["perguruan_tinggi"], filter_pt)
        and _match_tokens(r["program_studi"], filter_prodi)
    ]
    if pt_prodi_matches:
        candidates = pt_prodi_matches
    elif filter_pt:
        pt_matches = [r for r in all_rows if _match_tokens(r["perguruan_tinggi"], filter_pt)]
        candidates = pt_matches
    elif filter_prodi:
        prodi_matches = [r for r in all_rows if _match_tokens(r["program_studi"], filter_prodi)]
        candidates = prodi_matches
    else:
        candidates = all_rows

    results = []
    for row in candidates[:max_details]:
        detail = extract_student_detail(page, row["detail_url"])
        jenjang_prodi = detail.get("Jenjang - Program Studi") or row["program_studi"]
        results.append(
            {
                "query_nama": nama,
                "target_jenjang": target_jenjang,
                "filter_pt": filter_pt,
                "filter_prodi": filter_prodi,
                "nama": detail.get("Nama") or row["nama"],
                "nim": detail.get("NIM") or row["nim"],
                "perguruan_tinggi": detail.get("Perguruan Tinggi") or row["perguruan_tinggi"],
                "jenjang_prodi": jenjang_prodi,
                "cocok_jenjang": check_jenjang_match(jenjang_prodi, target_jenjang),
                "jenis_kelamin": detail.get("Jenis Kelamin", ""),
                "tanggal_masuk": detail.get("Tanggal Masuk", ""),
                "status_awal": detail.get("Status Awal Mahasiswa", ""),
                "status_terakhir": detail.get("Status Terakhir Mahasiswa", ""),
                "detail_url": row["detail_url"],
            }
        )
        time.sleep(0.6)

    if not results:
        note = "TIDAK DITEMUKAN (atau PT/Prodi tidak cocok)" if all_rows else "TIDAK DITEMUKAN"
        results.append(
            {
                "query_nama": nama,
                "target_jenjang": target_jenjang,
                "filter_pt": filter_pt,
                "filter_prodi": filter_prodi,
                "nama": note,
                "nim": "",
                "perguruan_tinggi": "",
                "jenjang_prodi": "",
                "cocok_jenjang": "",
                "jenis_kelamin": "",
                "tanggal_masuk": "",
                "status_awal": "",
                "status_terakhir": "",
                "detail_url": search_url,
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch lookup mahasiswa di PDDikti via Playwright.")
    parser.add_argument("--input", default="input_batch.csv", help="Path file CSV input")
    parser.add_argument("--output", default="output_batch.csv", help="Path file CSV output")
    parser.add_argument("--delay", type=float, default=1.0, help="Jeda antar pencarian (detik)")
    parser.add_argument("--max-pages", type=int, default=3, help="Maksimal halaman pagination per nama")
    parser.add_argument("--max-details", type=int, default=5, help="Maksimal kandidat detail yang dibuka per nama")
    parser.add_argument("--resume", action="store_true", help="Lewati nama yang sudah ada di file output")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        queries = list(csv.DictReader(f))

    done_queries = set()
    existing_rows = []
    if args.resume and output_path.exists():
        with output_path.open("r", encoding="utf-8-sig", newline="") as f:
            existing_rows = list(csv.DictReader(f))
            done_queries = {r["query_nama"].strip().lower() for r in existing_rows if r.get("query_nama")}

    all_results = list(existing_rows)
    write_header = not (args.resume and output_path.exists() and len(existing_rows) > 0)
    mode = "a" if not write_header else "w"

    with output_path.open(mode, encoding="utf-8-sig", newline="") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
            out_f.flush()

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=False)
            context = browser.new_context()
            page = context.new_page()

            for idx, q in enumerate(queries, start=1):
                nama = (q.get("nama") or "").strip()
                if not nama:
                    continue
                if nama.lower() in done_queries:
                    print(f"[{idx}/{len(queries)}] SKIP (sudah ada): {nama}")
                    continue

                target_jenjang = (q.get("target_jenjang") or "").strip()
                filter_pt = (q.get("filter_pt") or "").strip()
                filter_prodi = (q.get("filter_prodi") or "").strip()
                print(f"[{idx}/{len(queries)}] Mencari: {nama} ({target_jenjang}, PT='{filter_pt}', Prodi='{filter_prodi}')")

                rows = search_student(
                    page,
                    nama=nama,
                    target_jenjang=target_jenjang,
                    filter_pt=filter_pt,
                    filter_prodi=filter_prodi,
                    max_pages=args.max_pages,
                    max_details=args.max_details,
                )
                all_results.extend(rows)
                writer.writerows(rows)
                out_f.flush()

                for r in rows:
                    print(
                        f"   -> {r['nama']} | {r['nim']} | {r['perguruan_tinggi']} | "
                        f"{r['jenjang_prodi']} | Masuk: {r['tanggal_masuk']} | Status: {r['status_terakhir']}"
                    )
                time.sleep(args.delay)

            browser.close()

    json_path = output_path.with_suffix(".json")
    json_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSelesai. Total baris: {len(all_results)}. Hasil disimpan ke:\n- {output_path}\n- {json_path}")


if __name__ == "__main__":
    main()
