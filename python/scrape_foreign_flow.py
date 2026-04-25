import os
import json
from curl_cffi import requests

BASE_URL = "https://www.idx.co.id/primary/TradingSummary/GetStockSummary"
DATA_DIR = os.path.join(os.path.dirname(__file__), '../data/foreign_flow')

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "Referer": "https://www.idx.co.id/id/data-pasar/ringkasan-perdagangan/ringkasan-saham/"
}

def fetch_all_pages(date: str) -> list:
    url = f"{BASE_URL}?start=0&length=9999&date={date}"
    print(f"Fetching {url}...")
    r = requests.get(url, headers=HEADERS, impersonate="chrome", timeout=30)

    if r.status_code != 200:
        print(f"Error {r.status_code}: {r.text[:200]}")
        return []

    payload = r.json()
    data = payload.get("data", [])
    print(f"Total records fetched: {len(data)}")
    return data

def scrape_foreign_flow(date: str):
    """
    Scrape foreign buy/sell data for all stocks on a given date.
    date format: YYYY-MM-DD
    """
    os.makedirs(DATA_DIR, exist_ok=True)

    print(f"\n=== Scraping foreign flow: {date} ===")
    raw = fetch_all_pages(date)

    # Hitung net foreign buy per saham
    results = []
    for item in raw:
        foreign_buy = item.get("ForeignBuy") or 0
        foreign_sell = item.get("ForeignSell") or 0
        net = foreign_buy - foreign_sell
        results.append({
            "date": date,
            "code": item["StockCode"],
            "name": item["StockName"],
            "close": item.get("Close"),
            "change": item.get("Change"),
            "volume": item.get("Volume"),
            "value": item.get("Value"),
            "foreign_buy": foreign_buy,
            "foreign_sell": foreign_sell,
            "net_foreign": net,
        })

    # Urutkan: net foreign buy tertinggi
    results.sort(key=lambda x: x["net_foreign"], reverse=True)

    # Simpan ke file
    out_file = os.path.join(DATA_DIR, f"foreign_flow_{date}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Saved to {out_file}")

    # Tampilkan top 15 net foreign buy
    print(f"\n{'='*60}")
    print(f"TOP 15 NET FOREIGN BUY  —  {date}")
    print(f"{'='*60}")
    print(f"{'Kode':<6}  {'Nama':<35}  {'Close':>7}  {'Net Foreign (lot)':>18}")
    print("-" * 70)
    for r in results[:15]:
        print(f"{r['code']:<6}  {r['name'][:35]:<35}  {r['close']:>7,.0f}  {r['net_foreign']:>18,.0f}")

    # Tampilkan top 15 net foreign sell
    print(f"\n{'='*60}")
    print(f"TOP 15 NET FOREIGN SELL  —  {date}")
    print(f"{'='*60}")
    print(f"{'Kode':<6}  {'Nama':<35}  {'Close':>7}  {'Net Foreign (lot)':>18}")
    print("-" * 70)
    for r in results[-15:][::-1]:
        print(f"{r['code']:<6}  {r['name'][:35]:<35}  {r['close']:>7,.0f}  {r['net_foreign']:>18,.0f}")

    return results


if __name__ == "__main__":
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-04-24"
    scrape_foreign_flow(date)
