# pddikti-lookup

Skill & skrip Playwright (Python) untuk pencarian batch dan verifikasi status mahasiswa di PDDikti (`pddikti.kemdiktisaintek.go.id`), lengkap dengan ekspor CSV/JSON dan pembaruan Excel 3-sheet (Hijau/Kuning).

## Instalasi

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Penggunaan

### 1. Pencarian Batch dari CSV
```bash
.venv/bin/python scripts/pddikti_lookup.py --input input.csv --output output.csv --resume
```

### 2. Update Excel 3-Sheet
```bash
.venv/bin/python scripts/update_excel.py --excel "daftar beasiswa.xlsx" --csv output.csv
```
