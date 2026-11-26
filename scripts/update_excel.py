"""Memperbarui file Excel dengan 3 sheet dari hasil pencarian PDDikti:
1. Sheet1 (asli, tidak diubah)
2. Hasil_PDDikti (seluruh baris kandidat mentah dari PDDikti)
3. Verifikasi_Beasiswa (salinan Sheet1 dengan header di baris 1, urutan baris tetap + kolom hasil PDDikti,
   highlight Hijau pada nama yang yakin, Kuning pada nama yang mirip/perlu dicek).
"""

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path
import openpyxl
from openpyxl.styles import PatternFill, Font

GREEN_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
YELLOW_FILL = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
HEADER_FILL = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
BOLD_FONT = Font(bold=True)


def norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def name_similarity(q: str, cand: str) -> float:
    nq, nc = norm_name(q), norm_name(cand)
    if nq == nc:
        return 1.0
    if nq in nc or nc in nq:
        return 0.85
    q_words = set(nq.split())
    c_words = set(nc.split())
    if not q_words or not c_words:
        return 0.0
    return len(q_words & c_words) / max(len(q_words), len(c_words))


def classify_and_pick(query_nama: str, items: list[dict]) -> tuple[dict | None, str, str]:
    """Pilih kandidat terbaik dan tentukan status keyakinan: GREEN, YELLOW, atau NONE."""
    valid = [x for x in items if not x["nama"].startswith("TIDAK DITEMUKAN")]
    if not valid:
        return None, "NONE", "Tidak ditemukan di PDDikti"

    scored = sorted(
        valid,
        key=lambda x: (
            1 if x["cocok_jenjang"] == "Ya" else 0,
            name_similarity(query_nama, x["nama"]),
        ),
        reverse=True,
    )
    best = scored[0]
    sim = name_similarity(query_nama, best["nama"])
    has_filter = bool(best["filter_pt"] or best["filter_prodi"])
    jenjang_ok = best["cocok_jenjang"] == "Ya"
    exact_or_near = [x for x in valid if name_similarity(query_nama, x["nama"]) >= 0.8]

    if not jenjang_ok:
        return (
            best,
            "YELLOW",
            f"Jenjang berbeda (target {best['target_jenjang']}, di PDDikti {best['jenjang_prodi']})",
        )

    if len(valid) > 1 and not has_filter:
        return (
            best,
            "YELLOW",
            f"Ada {len(valid)} kandidat di PDDikti tanpa filter PT/Prodi — perlu verifikasi manual",
        )

    if sim < 0.75 and not has_filter:
        return (
            best,
            "YELLOW",
            f"Nama di PDDikti berbeda/parsial ('{best['nama']}')",
        )

    if has_filter or (len(exact_or_near) == 1 and jenjang_ok and sim >= 0.8):
        return best, "GREEN", "Cocok nama, jenjang, dan konteks"

    return best, "YELLOW", "Perlu verifikasi manual"


def main() -> None:
    parser = argparse.ArgumentParser(description="Update Excel dengan hasil verifikasi PDDikti.")
    parser.add_argument("--excel", required=True, help="Path file Excel target (.xlsx)")
    parser.add_argument("--csv", required=True, help="Path file CSV hasil pddikti_lookup.py")
    parser.add_argument("--sheet", default="Sheet1", help="Nama sheet sumber yang dipertahankan utuh")
    args = parser.parse_args()

    excel_path = Path(args.excel)
    csv_path = Path(args.csv)

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        csv_rows = list(csv.DictReader(f))

    by_query = defaultdict(list)
    for r in csv_rows:
        by_query[r["query_nama"].strip()].append(r)

    wb = openpyxl.load_workbook(excel_path)
    ws1 = wb[args.sheet]

    for sname in ("Hasil_PDDikti", "Verifikasi_Beasiswa"):
        if sname in wb.sheetnames:
            del wb[sname]

    ws2 = wb.create_sheet(title="Hasil_PDDikti")
    headers2 = [
        "Query Nama",
        "Target Jenjang",
        "Filter PT",
        "Filter Prodi",
        "Nama PDDikti",
        "NIM",
        "Perguruan Tinggi",
        "Jenjang - Prodi",
        "Cocok Jenjang",
        "Jenis Kelamin",
        "Tanggal Masuk",
        "Status Awal",
        "Status Terakhir",
        "Link PDDikti",
    ]
    ws2.append(headers2)
    for c in range(1, len(headers2) + 1):
        cell = ws2.cell(1, c)
        cell.fill = HEADER_FILL
        cell.font = BOLD_FONT

    for r in csv_rows:
        ws2.append(
            [
                r["query_nama"],
                r["target_jenjang"],
                r["filter_pt"],
                r["filter_prodi"],
                r["nama"],
                r["nim"],
                r["perguruan_tinggi"],
                r["jenjang_prodi"],
                r["cocok_jenjang"],
                r["jenis_kelamin"],
                r["tanggal_masuk"],
                r["status_awal"],
                r["status_terakhir"],
                r["detail_url"],
            ]
        )
    ws2.freeze_panes = "A2"

    ws3 = wb.create_sheet(title="Verifikasi_Beasiswa")
    headers3 = [
        "Nama",
        "Keterangan Beasiswa",
        "Nama PDDikti",
        "NIM",
        "Perguruan Tinggi",
        "Jenjang - Prodi",
        "Tanggal Masuk",
        "Status Terakhir",
        "Tingkat Keyakinan",
        "Catatan",
        "Link PDDikti",
    ]
    ws3.append(headers3)
    for c in range(1, len(headers3) + 1):
        cell = ws3.cell(1, c)
        cell.fill = HEADER_FILL
        cell.font = BOLD_FONT
    ws3.freeze_panes = "A2"

    counts = {"GREEN": 0, "YELLOW": 0, "NONE": 0}

    for row_idx in range(1, ws1.max_row + 1):
        target_row = row_idx + 1
        nama_orig = ws1.cell(row_idx, 1).value
        ket_orig = ws1.cell(row_idx, 2).value

        c_nama = ws3.cell(target_row, 1, value=nama_orig)
        ws3.cell(target_row, 2, value=ket_orig)

        q_key = (nama_orig or "").strip()
        items = by_query.get(q_key, [])
        best, status, note = classify_and_pick(q_key, items)
        counts[status] += 1

        if status == "GREEN":
            c_nama.fill = GREEN_FILL
            label = "Yakin (Hijau)"
        elif status == "YELLOW":
            c_nama.fill = YELLOW_FILL
            label = "Mirip / Cek Ulang (Kuning)"
        else:
            label = "Tidak Ditemukan"

        if best:
            ws3.cell(target_row, 3, value=best["nama"])
            ws3.cell(target_row, 4, value=best["nim"])
            ws3.cell(target_row, 5, value=best["perguruan_tinggi"])
            ws3.cell(target_row, 6, value=best["jenjang_prodi"])
            ws3.cell(target_row, 7, value=best["tanggal_masuk"])
            ws3.cell(target_row, 8, value=best["status_terakhir"])
            ws3.cell(target_row, 9, value=label)
            ws3.cell(target_row, 10, value=note)
            ws3.cell(target_row, 11, value=best["detail_url"])
        else:
            ws3.cell(target_row, 3, value="")
            ws3.cell(target_row, 9, value=label)
            ws3.cell(target_row, 10, value=note)

    for ws in (ws2, ws3):
        for col in ws.columns:
            max_len = max((len(str(cell.value or "")) for cell in col), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(max(max_len + 3, 12), 45)

    wb.save(excel_path)
    print(f"Berhasil memperbarui {excel_path}")
    print(f"Sheets: {wb.sheetnames}")
    print(f"Ringkasan: Hijau={counts['GREEN']}, Kuning={counts['YELLOW']}, Tidak Ditemukan={counts['NONE']}")


if __name__ == "__main__":
    main()
