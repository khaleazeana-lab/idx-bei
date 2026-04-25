"""
push_to_dashboard.py
Scrape foreign flow hari ini dari IDX, lalu push ke runtrade.ilova.app.

Usage:
    uv run push_to_dashboard.py                   # hari ini
    uv run push_to_dashboard.py 2026-04-24        # tanggal tertentu
    uv run push_to_dashboard.py 2026-04-24 5      # + tren 5 hari
"""
import os, sys, json
from datetime import datetime
from dotenv import load_dotenv
from curl_cffi import requests as cf_requests

load_dotenv()

RUNTRADE_URL = os.getenv("RUNTRADE_URL", "https://runtrade.ilova.app").rstrip("/")

# ── Lookup tables ─────────────────────────────────────────────────────────────
def _load_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default

_DATA_DIR   = os.path.join(os.path.dirname(__file__), '../data')
_SECTOR     = _load_json(os.path.join(_DATA_DIR, 'sector_map.json'), {})
_FR_RAW     = _load_json(os.path.join(_DATA_DIR, 'financial_ratio.json'), {})
_FUNDAMENTAL = {r['code']: r for r in _FR_RAW.get('data', []) if r.get('code')}
API_KEY      = os.getenv("RUNTRADE_API_KEY") or os.getenv("VPS_API_KEY")

if not API_KEY:
    raise RuntimeError("RUNTRADE_API_KEY tidak ada di .env")

# ── HTTP helper ──────────────────────────────────────────────────────────────

def _post(path: str, payload: dict) -> dict:
    try:
        r = cf_requests.post(
            f"{RUNTRADE_URL}{path}",
            json=payload,
            headers={"X-API-Key": API_KEY},
            impersonate="chrome",
            timeout=20,
        )
        if r.status_code == 200:
            return r.json()
        print(f"  HTTP {r.status_code} dari {path}: {r.text[:200]}")
        return {}
    except Exception as e:
        print(f"  Error POST {path}: {e}")
        return {}

# ── Scraper (reuse dari scrape_foreign_flow.py) ──────────────────────────────

def _fetch_foreign_flow(date: str) -> list:
    """Return list of dicts dengan field net_foreign, atau load dari cache."""
    from scrape_foreign_flow import fetch_all_pages
    import os

    DATA_DIR  = os.path.join(os.path.dirname(__file__), '../data/foreign_flow')
    cache     = os.path.join(DATA_DIR, f"foreign_flow_{date}.json")

    if os.path.exists(cache):
        with open(cache, encoding='utf-8') as f:
            print(f"  [{date}] loaded from cache")
            return json.load(f)

    print(f"  [{date}] fetching from IDX...")
    raw = fetch_all_pages(date)
    if not raw:
        return []

    results = []
    for item in raw:
        fb = item.get("ForeignBuy") or 0
        fs = item.get("ForeignSell") or 0
        results.append({
            "date":         date,
            "code":         item["StockCode"],
            "name":         item["StockName"],
            "close":        item.get("Close"),
            "change":       item.get("Change"),
            "volume":       item.get("Volume"),
            "value":        item.get("Value"),
            "foreign_buy":  fb,
            "foreign_sell": fs,
            "net_foreign":  fb - fs,
        })

    results.sort(key=lambda x: x["net_foreign"], reverse=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(cache, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"  [{date}] {len(results)} saham")
    return results


def _build_trend(end_date: str, n_days: int) -> dict:
    """Hitung akumulasi net foreign n hari terakhir."""
    from analyze_foreign_trend import get_trading_dates
    from collections import defaultdict

    dates = get_trading_dates(end_date, n_days)
    totals = defaultdict(lambda: {"name": "", "net_total": 0, "days_buy": 0, "days_sell": 0})

    for d in dates:
        rows = _fetch_foreign_flow(d)
        for r in rows:
            code = r["code"]
            totals[code]["name"] = r["name"]
            totals[code]["net_total"] += r["net_foreign"]
            if r["net_foreign"] > 0:
                totals[code]["days_buy"]  += 1
            elif r["net_foreign"] < 0:
                totals[code]["days_sell"] += 1

    ranked = sorted(totals.items(), key=lambda x: x[1]["net_total"], reverse=True)
    return {
        "dates":     dates,
        "top_buy":   [{"code": c, **v} for c, v in ranked[:20]],
        "top_sell":  [{"code": c, **v} for c, v in ranked[-20:][::-1]],
        "consistent_buy":  [{"code": c, **v} for c, v in ranked if v["days_buy"]  == len(dates)],
        "consistent_sell": [{"code": c, **v} for c, v in ranked if v["days_sell"] == len(dates)],
    }

# ── Push functions ────────────────────────────────────────────────────────────

def push_all(date: str, rows: list, trend: dict | None = None):
    """Push semua data (aggregate + detail) dalam satu request ke /foreign-flow/push."""
    print(f"\n[1/1] Push foreign flow ({date}) -> /foreign-flow/push ...")

    net_vals    = [r["net_foreign"] for r in rows]
    total_buy   = sum(v for v in net_vals if v > 0)
    total_sell  = sum(v for v in net_vals if v < 0)
    consistent_buy  = (trend or {}).get("consistent_buy", [])
    consistent_sell = (trend or {}).get("consistent_sell", [])

    payload = {
        "date":               date,
        "source":             "idx-bei/foreign_flow",
        # aggregate untuk chart
        "total_stocks":       len(rows),
        "net_buy_stocks":     sum(1 for v in net_vals if v > 0),
        "net_sell_stocks":    sum(1 for v in net_vals if v < 0),
        "total_foreign_buy":  total_buy,
        "total_foreign_sell": total_sell,
        "net_market":         total_buy + total_sell,
        # detail untuk tabel
        "top_buy":            rows[:30],
        "top_sell":           rows[-30:][::-1],
        "consistent_buy":     consistent_buy[:30],
        "consistent_sell":    consistent_sell[:30],
        "trend":              trend,
        # semua saham — compact untuk chart per-saham + sektor
        "all_stocks":         [{"code": r["code"], "name": r["name"],
                                "net": r["net_foreign"], "close": r.get("close"),
                                "value": r.get("value"),
                                "sektor": _SECTOR.get(r["code"], {}).get("sektor", ""),
                                "subSektor": _SECTOR.get(r["code"], {}).get("subSektor", "")} for r in rows],
        "generated":          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    res = _post("/foreign-flow/push", payload)
    print(f"  -> {res}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    date   = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    n_days = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    print(f"\n{'='*55}")
    print(f"  PUSH TO DASHBOARD: {RUNTRADE_URL}")
    print(f"  Tanggal: {date} | Tren: {n_days} hari")
    print(f"{'='*55}")

    print(f"\n[Fetch] Ambil data foreign flow...")
    rows = _fetch_foreign_flow(date)
    if not rows:
        print(f"Tidak ada data untuk {date} (hari libur?). Berhenti.")
        return

    print(f"\n[Trend] Hitung tren {n_days} hari...")
    trend = _build_trend(date, n_days)

    push_all(date, rows, trend)

    # Push fundamental data (once per run, skip if already pushed recently)
    if _FUNDAMENTAL and sys.argv[1:] == [] or date == datetime.now().strftime("%Y-%m-%d"):
        push_fundamental()

    # Push IHSG for this date
    push_ihsg(date)

    print(f"\nSelesai. Cek dashboard: {RUNTRADE_URL}")


def push_fundamental():
    """Push financial ratio data ke /fundamental/push."""
    data = []
    for code, r in _FUNDAMENTAL.items():
        data.append({
            "code": code, "name": r.get("stockName",""),
            "sector": r.get("sector",""), "subSector": r.get("subSector",""),
            "per": r.get("per"), "pbv": r.get("priceBV"),
            "roe": r.get("roe"), "roa": r.get("roa"),
            "der": r.get("deRatio"), "npm": r.get("npm"),
            "eps": r.get("eps"), "equity": r.get("equity"),
        })
    res = _post("/fundamental/push", {"data": data, "source": "financial_ratio.json"})
    print(f"  [Fundamental] {len(data)} saham -> {res}")


def push_ihsg(date: str):
    """Push IHSG closing price untuk satu tanggal."""
    try:
        from curl_cffi import requests as cf
        url = f"https://www.idx.co.id/primary/TradingSummary/GetIndexSummary?length=9999&start=0"
        r = cf.get(url, impersonate="chrome", timeout=15)
        if r.status_code != 200:
            return
        items = r.json().get("data", [])
        for item in items:
            if str(item.get("IndexCode","")).upper() in ("COMPOSITE", "IHSG", "IDX COMPOSITE"):
                close = item.get("Close") or item.get("IndexValue")
                if close:
                    _post("/ihsg/push", {"date": date, "close": close,
                                         "change": item.get("Change"), "volume": item.get("Volume")})
                    print(f"  [IHSG] {date}: {close}")
                    return
    except Exception as e:
        print(f"  [IHSG] skip: {e}")

if __name__ == "__main__":
    main()
