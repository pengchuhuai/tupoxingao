"""Fetch the latest THS all-time-high ranking without full-market history scans."""
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import akshare as ak
import pandas as pd

OUT = Path("data")
OUT.mkdir(exist_ok=True)
now = datetime.now(ZoneInfo("Asia/Shanghai"))
df = ak.stock_rank_cxg_ths(symbol="历史新高")
if df is None or df.empty:
    raise RuntimeError("THS historical-high ranking returned no rows; retaining previous data")
rows = df.where(pd.notna(df), None).to_dict(orient="records")
records = [{str(k): (v.item() if hasattr(v, "item") else v) for k, v in row.items()} for row in rows]
payload = {
    "fetched_at": now.isoformat(),
    "source": "THS via AKShare stock_rank_cxg_ths",
    "category": "历史新高",
    "count": len(records),
    "columns": list(df.columns),
    "records": records,
    "note": "Source ranking snapshot; not independently verified as listing-to-date high. Source date may differ from fetch date.",
}
target = OUT / "ath_source_latest.json"
tmp = target.with_suffix(".tmp")
tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
os.replace(tmp, target)
print(f"Fetched {len(records)} source ranking rows at {now.isoformat()}")
print("Columns:", list(df.columns))
