import os
import json
from curl_cffi import requests
from datetime import datetime, timedelta
from collections import defaultdict

BASE_URL = "https://www.idx.co.id/primary/TradingSummary/GetStockSummary"
DATA_DIR = os.path.join(os.path.dirname(__file__), '../data/foreign_flow')

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "Referer": "https://www.idx.co.id/id/data-pasar/ringkasan-perdagangan/ringkasan-saham/"
}

def fetch_date(date: str) -> list:
    cache_file = os.path.join(DATA_DIR, f"foreign_flow_{date}.json")
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            print(f"  [{date}] loaded from cache")
            return json.load(f)

    print(f"  [{date}] fetching from IDX...")
    r = requests.get(
        f"{BASE_URL}?start=0&length=9999&date={date}",
        headers=HEADERS, impersonate="chrome", timeout=30
    )
    if r.status_code != 200:
        print(f"  [{date}] Error {r.status_code} — skip (hari libur/tidak ada data)")
        return []

    raw = r.json().get("data", [])
    if not raw:
        print(f"  [{date}] kosong — skip")
        return []

    results = []
    for item in raw:
        fb = item.get("ForeignBuy") or 0
        fs = item.get("ForeignSell") or 0
        results.append({
            "value":        item.get("Value"),
            "date": date,
            "code": item["StockCode"],
            "name": item["StockName"],
            "close": item.get("Close"),
            "foreign_buy": fb,
            "foreign_sell": fs,
            "net_foreign": fb - fs,
        })

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"  [{date}] {len(results)} saham, disimpan ke cache")
    return results

def get_trading_dates(end_date: str, n_days: int) -> list:
    """Ambil n hari kerja ke belakang dari end_date (skip weekend)."""
    dt = datetime.strptime(end_date, "%Y-%m-%d")
    dates = []
    while len(dates) < n_days:
        if dt.weekday() < 5:  # Senin-Jumat
            dates.append(dt.strftime("%Y-%m-%d"))
        dt -= timedelta(days=1)
    return list(reversed(dates))

def analyze_trend(end_date: str = "2026-04-24", n_days: int = 5, top_n: int = 15):
    print(f"\n{'='*65}")
    print(f"  ANALISIS TREN FOREIGN FLOW — {n_days} hari kerja s/d {end_date}")
    print(f"{'='*65}")

    dates = get_trading_dates(end_date, n_days)
    print(f"\nMengambil data untuk: {', '.join(dates)}\n")

    # Kumpulkan semua data per hari
    daily_data = {}
    for d in dates:
        rows = fetch_date(d)
        if rows:
            daily_data[d] = {r["code"]: r for r in rows}

    valid_dates = [d for d in dates if d in daily_data]
    if not valid_dates:
        print("Tidak ada data yang berhasil diambil.")
        return

    # Hitung akumulasi net foreign per saham
    totals = defaultdict(lambda: {"name": "", "net_total": 0, "days": 0, "daily": {}})
    for d in valid_dates:
        for code, row in daily_data[d].items():
            totals[code]["name"] = row["name"]
            totals[code]["net_total"] += row["net_foreign"]
            totals[code]["days"] += 1
            totals[code]["daily"][d] = row["net_foreign"]

    # Hanya saham yang ada di semua hari valid
    all_days = len(valid_dates)
    ranked = [
        {"code": code, **v}
        for code, v in totals.items()
        if v["days"] == all_days
    ]

    ranked_buy  = sorted(ranked, key=lambda x: x["net_total"], reverse=True)
    ranked_sell = sorted(ranked, key=lambda x: x["net_total"])

    # Header tabel
    def date_short(d): return d[5:]  # MM-DD
    col_dates = "  ".join(f"{date_short(d):>12}" for d in valid_dates)

    def print_table(title, rows):
        print(f"\n{'='*65}")
        print(f"  {title}")
        print(f"{'='*65}")
        header = f"{'Kode':<6}  {'Nama':<28}  {col_dates}  {'TOTAL':>14}"
        print(header)
        print("-" * len(header))
        for r in rows[:top_n]:
            daily_cols = "  ".join(
                f"{r['daily'].get(d, 0):>12,.0f}" for d in valid_dates
            )
            print(f"{r['code']:<6}  {r['name'][:28]:<28}  {daily_cols}  {r['net_total']:>14,.0f}")

    print_table(f"TOP {top_n} AKUMULASI NET FOREIGN BUY  (lot)", ranked_buy)
    print_table(f"TOP {top_n} AKUMULASI NET FOREIGN SELL  (lot)", ranked_sell)

    # Konsisten beli/jual setiap hari
    konsisten_beli = [r for r in ranked if all(r["daily"].get(d, 0) > 0 for d in valid_dates)]
    konsisten_jual = [r for r in ranked if all(r["daily"].get(d, 0) < 0 for d in valid_dates)]

    konsisten_beli.sort(key=lambda x: x["net_total"], reverse=True)
    konsisten_jual.sort(key=lambda x: x["net_total"])

    if konsisten_beli:
        print(f"\n{'='*65}")
        print(f"  DIBELI ASING SETIAP HARI ({all_days} hari berturut-turut)")
        print(f"{'='*65}")
        for r in konsisten_beli[:top_n]:
            print(f"  {r['code']:<6}  {r['name'][:40]}  total: {r['net_total']:>14,.0f} lot")

    if konsisten_jual:
        print(f"\n{'='*65}")
        print(f"  DIJUAL ASING SETIAP HARI ({all_days} hari berturut-turut)")
        print(f"{'='*65}")
        for r in konsisten_jual[:top_n]:
            print(f"  {r['code']:<6}  {r['name'][:40]}  total: {r['net_total']:>14,.0f} lot")

    print()

if __name__ == "__main__":
    import sys
    end_date = sys.argv[1] if len(sys.argv) > 1 else "2026-04-24"
    n_days   = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    analyze_trend(end_date, n_days)
