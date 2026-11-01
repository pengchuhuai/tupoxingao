"""Diagnostic comparison of Eastmoney and TDX daily data for one symbol.

Install: pip install akshare pandas pytdx
Run: python tests/compare_tdx_eastmoney.py --symbol 600000 --date 2026-10-30
This is a connectivity/coverage probe, NOT a complete market-wide ATH screener.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

def run(symbol, date):
    import akshare as ak
    from pytdx.hq import TdxHq_API
    from pytdx.config.hosts import hq_hosts
    result = {"symbol": symbol, "date": date, "sources": {}}
    try:
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date="19900101", end_date=date.replace("-", ""), adjust="")
        row = df.loc[df["日期"].astype(str) == date]
        result["sources"]["eastmoney"] = {"rows": len(df), "date_found": not row.empty, "last_date": str(df.iloc[-1]["日期"]) if len(df) else None}
        if not row.empty:
            prev = df.loc[df["日期"].astype(str) < date]
            result["sources"]["eastmoney"]["ath_intraday_unadjusted"] = bool(len(prev) and float(row.iloc[0]["最高"]) > float(prev["最高"].max()))
    except Exception as exc:
        result["sources"]["eastmoney"] = {"error": type(exc).__name__ + ": " + str(exc)[:300]}
    api = TdxHq_API()
    try:
        host = hq_hosts[0]
        if not api.connect(host[1], host[2]):
            raise ConnectionError("TDX connection refused")
        market = 1 if symbol.startswith(("6", "9")) else 0
        bars = []
        offset = 0
        while True:
            batch = api.get_security_bars(9, market, symbol, offset, 800)
            if not batch:
                break
            bars.extend(batch)
            offset += len(batch)
            if len(batch) < 800 or offset >= 12000:
                break
        dates = [str(x["datetime"])[:10] for x in bars]
        result["sources"]["tdx"] = {"rows": len(bars), "date_found": date in dates, "oldest_date": min(dates) if dates else None, "newest_date": max(dates) if dates else None, "truncated": offset >= 12000}
        if date in dates:
            current = next(x for x in bars if str(x["datetime"])[:10] == date)
            previous = [x["high"] for x in bars if str(x["datetime"])[:10] < date]
            result["sources"]["tdx"]["ath_intraday_unadjusted"] = bool(previous and current["high"] > max(previous))
    except Exception as exc:
        result["sources"]["tdx"] = {"error": type(exc).__name__ + ": " + str(exc)[:300]}
    finally:
        try: api.disconnect()
        except Exception: pass
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="600000")
    parser.add_argument("--date", default="2026-10-30")
    args = parser.parse_args()
    datetime.strptime(args.date, "%Y-%m-%d")
    run(args.symbol, args.date)
