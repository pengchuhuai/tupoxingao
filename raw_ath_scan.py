"""Incremental RAW (unadjusted) intraday all-time-high verifier.
No 52-week proxies. Each stock is verified against all available bars since listing.
Requires TUSHARE_TOKEN; deliberately does not emit unverified candidates.
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import tushare as ts

ROOT = Path("data")
ROOT.mkdir(exist_ok=True)
TOKEN = os.getenv("TUSHARE_TOKEN")
BATCH_SIZE = max(1, int(os.getenv("ATH_BATCH_SIZE", "50")))


def read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def request(call, **kwargs):
    for attempt in range(3):
        try:
            return call(**kwargs)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def verify_raw(pro, stock, through):
    code = stock["ts_code"]
    listing = str(stock["list_date"])
    chunks = []
    for year in range(int(listing[:4]), int(through[:4]) + 1):
        start, end = max(listing, f"{year}0101"), min(through, f"{year}1231")
        if start > end:
            continue
        bars = request(pro.daily, ts_code=code, start_date=start, end_date=end,
                       fields="ts_code,trade_date,open,high,low,close,vol")
        if bars is not None and not bars.empty:
            # Yearly queries avoid Tushare's per-request row cap.
            if len(bars) >= 5000:
                raise ValueError(f"Potentially truncated yearly data: {year}")
            chunks.append(bars)
    if not chunks:
        raise ValueError("No history returned")
    df = pd.concat(chunks, ignore_index=True)
    if df.trade_date.duplicated().any():
        df = df.drop_duplicates("trade_date")
    df = df.sort_values("trade_date").reset_index(drop=True)
    if df.high.isna().any() or (df.high.astype(float) <= 0).any():
        raise ValueError("Invalid high prices")
    if str(df.iloc[0].trade_date) < listing:
        raise ValueError("Data predates listing")
    # A missing initial history segment cannot be proven absent with this API.
    # Mark coverage explicitly; do not silently assert independently audited IPO history.
    previous = df.high.astype(float).cummax().shift(1)
    events = []
    for i in range(1, len(df)):
        day = str(df.at[i, "trade_date"])
        high, prev = float(df.at[i, "high"]), float(previous.iloc[i])
        if high > prev:
            events.append({
                "ts_code": code, "name": stock["name"], "date": day,
                "basis": "raw", "breakout_high": round(high, 6),
                "previous_high": round(prev, 6),
                "gain_pct": round((high / prev - 1) * 100, 4),
                "history_from": str(df.iloc[0].trade_date),
                "listing_date": listing, "data_through": through,
                "source": "Tushare Pro daily",
                "verification": "source_history_fetched_not_independently_audited"
            })
    return events, len(df)


def main():
    if not TOKEN:
        raise SystemExit("Missing TUSHARE_TOKEN GitHub Actions secret")
    pro = ts.pro_api(TOKEN)
    now = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d")
    stocks = []
    for status in ("L", "D", "P"):
        part = request(pro.stock_basic, exchange="", list_status=status,
                       fields="ts_code,name,list_date,list_status")
        stocks.append(part)
    universe = pd.concat(stocks, ignore_index=True).drop_duplicates("ts_code")
    universe = universe[universe.list_date.astype(str).str.fullmatch(r"\d{8}")]
    # Prefer current listings; retain D/P for later historical research.
    universe = universe.sort_values(["list_status", "ts_code"],
                                    key=lambda s: s.map({"L": 0, "P": 1, "D": 2}) if s.name == "list_status" else s)
    progress_path = ROOT / "raw_ath_progress.json"
    result_path = ROOT / "raw_ath_breakouts.json"
    progress = read_json(progress_path, {"completed": {}, "errors": {}})
    completed, errors = progress["completed"], progress["errors"]
    due = [s for s in universe.to_dict("records") if completed.get(s["ts_code"]) != now]
    # Unprocessed names first; then refresh previously covered names.
    due.sort(key=lambda s: (s["ts_code"] in completed, s["list_status"] != "L", s["ts_code"]))
    selected = due[:BATCH_SIZE]
    saved = read_json(result_path, [])
    index = {(e["ts_code"], e["date"], e["basis"]) for e in saved}
    for stock in selected:
        code = stock["ts_code"]
        try:
            events, bars = verify_raw(pro, stock, now)
            new = [e for e in events if (e["ts_code"], e["date"], e["basis"]) not in index]
            saved.extend(new)
            index.update((e["ts_code"], e["date"], e["basis"]) for e in new)
            completed[code] = now
            errors.pop(code, None)
            print(f"[ATH] {code}: bars={bars}, historical_breakouts={len(events)}, new={len(new)}", flush=True)
        except Exception as exc:
            errors[code] = str(exc)[:300]
            print(f"[ATH] ERROR {code}: {exc}", flush=True)
        finally:
            write_json(progress_path, progress)
            write_json(result_path, saved)
            time.sleep(0.25)
    latest = sorted((e for e in saved if e["date"] == now), key=lambda e: e["ts_code"])
    write_json(ROOT / "raw_ath_today.json", {
        "date": now, "complete_market_coverage": False,
        "verified_with_source_history": latest,
        "note": "Partial batch only. RAW high > prior all-time RAW high; not 250-day high. Full IPO history not independently audited.",
        "processed_today": sum(d == now for d in completed.values()),
        "universe": len(universe), "errors": len(errors)
    })
    print(f"[ATH] processed_today={sum(d == now for d in completed.values())}/{len(universe)}, new_today={len(latest)}", flush=True)


if __name__ == "__main__":
    main()
