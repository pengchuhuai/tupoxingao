"""Fetch A-share all-time-high candidates from THS Wencai (not the THS ranking).

The result is a candidate snapshot, not independently verified historical highs.
Fail closed: never overwrite a previous snapshot when Wencai fails or returns no data.
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pywencai

OUT = Path("data")
TZ = ZoneInfo("Asia/Shanghai")
now = datetime.now(TZ)
day = os.environ.get("WENCAI_TRADE_DATE", "").strip()
if not day:
    d = now.date()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    day = d.isoformat()
datetime.strptime(day, "%Y-%m-%d")
query = f"{day} A股 上市以来历史新高"
print(f"Wencai query: {query}", flush=True)
# loop=True requests all pages in pywencai versions supporting this argument.
df = pywencai.get(query=query, query_type="stock", loop=True)
if not isinstance(df, pd.DataFrame) or df.empty:
    raise RuntimeError("Wencai returned no tabular rows; previous snapshot retained")
# Wencai columns are dynamic; preserve all original columns for later auditing.
df = df.astype(object).where(pd.notna(df), None)
records = json.loads(df.to_json(orient="records", force_ascii=False, date_format="iso"))
payload = {
    "fetched_at": now.isoformat(),
    "requested_trade_date": day,
    "source": "THS Wencai via pywencai",
    "query": query,
    "count": len(records),
    "columns": [str(c) for c in df.columns],
    "records": records,
    "verification_status": "UNVERIFIED",
    "note": "Wencai candidate output; pagination, market coverage, price adjustment, and listing-to-date highs require independent verification.",
}
OUT.mkdir(exist_ok=True)
target = OUT / "ath_wencai_latest.json"
temp = target.with_suffix(".tmp")
temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
os.replace(temp, target)
print(f"Saved {len(records)} Wencai candidate rows to {target}", flush=True)
