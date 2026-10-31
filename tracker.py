"""Conservative A-share all-time intraday-high backfill and MA10 watcher.

No orders. No signal unless the listing-to-present history has been fetched
successfully. Requires Tushare Pro access and API quota.
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import tushare as ts

ROOT = Path("data")
HISTORY = ROOT / "history"
ROOT.mkdir(exist_ok=True)
HISTORY.mkdir(exist_ok=True)
TOKEN = os.environ.get("TUSHARE_TOKEN", "")
BATCH = max(1, int(os.environ.get("BATCH_SIZE", "25")))


def save(name, obj):
    path = ROOT / name
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def load(name, default):
    p = ROOT / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def request(func, **kwargs):
    for attempt in range(3):
        try:
            return func(**kwargs)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))


def main():
    if not TOKEN:
        raise SystemExit("Set GitHub Actions secret TUSHARE_TOKEN")
    pro = ts.pro_api(TOKEN)
    now = datetime.now().strftime("%Y%m%d")  # runner UTC; scheduled after CN close
    cal = request(pro.trade_cal, exchange="SSE", start_date=now, end_date=now)
    if cal.empty or str(cal.iloc[0]["is_open"]) != "1":
        print("Not a trading day; skipping")
        return

    stocks = []
    for status in ("L", "D", "P"):
        df = request(pro.stock_basic, exchange="", list_status=status,
                     fields="ts_code,name,list_date,list_status")
        stocks.append(df)
    universe = pd.concat(stocks).drop_duplicates("ts_code").sort_values("ts_code")
    # Exclude codes without valid listing dates.
    universe = universe[universe.list_date.astype(str).str.fullmatch(r"\d{8}")]
    progress = load("progress.json", {"completed": {}, "errors": {}})
    completed = progress["completed"]
    errors = progress["errors"]
    # Existing stocks are refreshed each trading day, while new stocks are backfilled.
    due = sorted([r for r in universe.to_dict("records") if completed.get(r["ts_code"]) != now],\n                 key=lambda r: (r["ts_code"] in completed, r["ts_code"]))
    selected = due[:BATCH]
    breakouts = load("breakouts.json", [])
    index = {(x["ts_code"], x["date"], x["basis"]) for x in breakouts}
    watchlist = load("watchlist.json", [])
    watch_index = {(x["ts_code"], x["breakout_date"], x["basis"]): x for x in watchlist}

    for stock in selected:
        code, listing = stock["ts_code"], str(stock["list_date"])
        try:
            # Full listing history fetched, not a 250-day proxy.
            daily = request(pro.daily, ts_code=code, start_date=listing, end_date=now)
            factors = request(pro.adj_factor, ts_code=code, start_date=listing, end_date=now)
            if daily.empty:
                raise ValueError("No daily bars; cannot verify listing history")
            if factors.empty:
                raise ValueError("Missing adjustment factors")
            daily = daily.sort_values("trade_date").drop_duplicates("trade_date")
            factors = factors[["trade_date", "adj_factor"]].drop_duplicates("trade_date")
            df = daily.merge(factors, on="trade_date", how="left", validate="one_to_one")
            if df.adj_factor.isna().any():
                raise ValueError("Adjustment factors missing on some trading dates")
            # Tushare returns a capped number of rows per request. Reject truncated histories.
            # For a long-lived stock, pagination is mandatory; use yearly windows below.
            years = range(int(listing[:4]), int(now[:4]) + 1)
            chunks = []
            for year in years:
                start = max(listing, f"{year}0101")
                end = min(now, f"{year}1231")
                if start > end:
                    continue
                d = request(pro.daily, ts_code=code, start_date=start, end_date=end)
                a = request(pro.adj_factor, ts_code=code, start_date=start, end_date=end)
                if d.empty:
                    continue
                if a.empty:
                    raise ValueError(f"No adj_factor in {year}")
                chunks.append(d.merge(a[["trade_date", "adj_factor"]],
                                      on="trade_date", validate="one_to_one"))
            if not chunks:
                raise ValueError("No history")
            df = pd.concat(chunks).drop_duplicates("trade_date").sort_values("trade_date").reset_index(drop=True)
            if df.adj_factor.isna().any() or len(df) < len(daily):
                raise ValueError("Incomplete yearly history")
            if str(df.iloc[0]["trade_date"]) < listing:
                raise ValueError("History predates listing unexpectedly")
            # Detect gaps relative to exchange trading calendar, allowing suspension days.
            # Cannot independently certify every missing bar: mark data as source-verified only.
            df["high_hfq"] = df["high"].astype(float) * df["adj_factor"].astype(float)
            df["ma10"] = df["close"].astype(float).rolling(10).mean()
            df["prev_vol5"] = df["vol"].astype(float).shift(1).rolling(5).mean()
            for basis, col in (("raw", "high"), ("hfq", "high_hfq")):
                prev_max = df[col].astype(float).cummax().shift(1)
                for i in range(1, len(df)):
                    day = str(df.at[i, "trade_date"])
                    if float(df.at[i, col]) <= float(prev_max.iloc[i]):
                        continue
                    key = (code, day, basis)
                    if key not in index:
                        breakouts.append({
                            "ts_code": code, "name": stock["name"], "date": day,
                            "basis": basis, "breakout_high": round(float(df.at[i, col]), 6),
                            "previous_high": round(float(prev_max.iloc[i]), 6),
                            "gain_pct": round((float(df.at[i, col]) / float(prev_max.iloc[i]) - 1) * 100, 4),
                            "source": "Tushare Pro daily + adj_factor",
                            "history_from": listing, "data_through": now,
                            "verification": "source_history_fetched"
                        })
                        index.add(key)
                    # A watchlist record is created only for a new-high event,
                    # and only first touch after that event can qualify.
                    wkey = (code, day, basis)
                    if wkey not in watch_index:
                        watch_index[wkey] = {
                            "ts_code": code, "name": stock["name"],
                            "breakout_date": day, "basis": basis,
                            "first_touch_date": None, "touch_count": 0,
                            "first_touch_valid": False, "status": "watching"
                        }
            # Recompute touch tracking from full bars deterministically.
            for (wcode, bdate, basis), w in list(watch_index.items()):
                if wcode != code:
                    continue
                start_idx = df.index[df.trade_date.astype(str) == bdate]
                if len(start_idx) == 0:
                    continue
                touches = 0
                first_date = None
                first_valid = False
                for i in range(int(start_idx[0]) + 1, len(df)):
                    if pd.isna(df.at[i, "ma10"]) or pd.isna(df.at[i, "prev_vol5"]):
                        continue
                    low = float(df.at[i, "low"])
                    ma = float(df.at[i, "ma10"])
                    if low <= ma * 1.01 and float(df.at[i, "high"]) >= ma * 0.99:
                        touches += 1
                        if touches == 1:
                            first_date = str(df.at[i, "trade_date"])
                            first_valid = (
                                float(df.at[i, "vol"]) < float(df.at[i, "prev_vol5"])
                                and float(df.at[i, "open"]) >= float(df.at[i - 1, "close"])
                                and float(df.at[i, "close"]) >= ma
                            )
                w.update(touch_count=touches, first_touch_date=first_date,
                         first_touch_valid=first_valid,
                         status="first_touch_valid" if first_valid else
                         ("first_touch_invalid" if touches else "watching"))
            df.to_csv(HISTORY / f"{code}.csv.gz", index=False, compression="gzip")
            completed[code] = now
            errors.pop(code, None)
        except Exception as exc:
            errors[code] = str(exc)[:300]
            print(f"FAILED {code}: {exc}")
        finally:
            progress["completed"], progress["errors"] = completed, errors
            save("progress.json", progress)
            save("breakouts.json", breakouts)
            save("watchlist.json", list(watch_index.values()))
            time.sleep(0.25)

    save("status.json", {
        "as_of": now, "processed_today": sum(v == now for v in completed.values()),
        "total": len(universe), "complete": len(universe) > 0 and
        all(completed.get(c) == now for c in universe.ts_code),
        "errors": errors, "batch_size": BATCH,
        "warning": "Incomplete until every listed/delisted/suspended code is processed; source gaps not independently audited"
    })
    print(f"Processed {len(selected)}; total {len(universe)}")


if __name__ == "__main__":
    main()
