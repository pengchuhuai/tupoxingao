"""Fetch WenCai intraday HIGH all-time-high candidates; no full-market scan."""
import json
import os
import traceback
import importlib.metadata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pywencai

DAY = os.environ.get("ATH_TRADE_DATE", "20261030")
day = f"{DAY[:4]}年{int(DAY[4:6])}月{int(DAY[6:])}日"
questions = [
    "2026年10月30日涨停股票",
    f"{day}A股当日最高价创上市以来历史新高，股票代码，股票简称，当日最高价",
    f"{day}A股盘中最高价突破上市以来历史最高价，股票代码，股票简称，当日最高价",
]
out = {"diagnostics": {"pywencai_version": importlib.metadata.version("pywencai")}, "trade_date": DAY, "fetched_at": datetime.now(timezone.utc).isoformat(),
       "source": "pywencai (unofficial WenCai client)", "queries": [], "records": [],
       "verified": False, "note": "Candidates only; not independently verified against historical intraday highs."}
all_rows = {}
for question in questions:
    result = {"question": question}
    try:
        df = pywencai.get(query=question, query_type="stock", loop=True)
        if not isinstance(df, pd.DataFrame):
            raise RuntimeError(f"Unexpected response type: {type(df).__name__}")
        result["count"] = len(df)
        result["columns"] = list(map(str, df.columns))
        result["sample"] = json.loads(df.head(3).to_json(orient="records", force_ascii=False))
        code_cols = [c for c in df.columns if "股票代码" in str(c) or str(c).lower() == "code"]
        name_cols = [c for c in df.columns if "股票简称" in str(c) or "股票名称" in str(c)]
        if not code_cols:
            raise RuntimeError("No stock-code column in returned dataframe")
        for _, row in df.iterrows():
            code = str(row[code_cols[0]]).strip()
            if not code or code == "nan":
                continue
            name = str(row[name_cols[0]]) if name_cols else ""
            all_rows.setdefault(code, {"code": code, "name": name, "matched_queries": []})
            all_rows[code]["matched_queries"].append(question)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc(limit=12)
    out["queries"].append(result)
out["records"] = list(all_rows.values())
out["count"] = len(out["records"])
Path("data").mkdir(exist_ok=True)
Path("data/ath_wencai_latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"date": DAY, "count": out["count"], "queries": out["queries"],
                  "stocks": out["records"]}, ensure_ascii=False, indent=2))
if not any("count" in q for q in out["queries"]):
    raise SystemExit("All WenCai queries failed; see output and saved diagnostic JSON")
