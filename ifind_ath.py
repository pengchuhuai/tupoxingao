"""Official iFinD smart stock picking; candidates, NOT independently verified ATH signals."""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
import requests

DAY = os.getenv("ATH_TRADE_DATE", "20261030")
ACCESS = os.getenv("IFIND_ACCESS_TOKEN", "").strip()
REFRESH = os.getenv("IFIND_REFRESH_TOKEN", "").strip()
BASE = "https://quantapi.51ifind.com/api/v1"
DEST = Path("data/ath_ifind_latest.json")
questions = [
    f"{DAY[:4]}年{int(DAY[4:6])}月{int(DAY[6:])}日A股盘中最高价创上市以来历史新高，股票代码，股票简称，当日最高价",
    f"{DAY[:4]}年{int(DAY[4:6])}月{int(DAY[6:])}日A股最高价突破历史最高价，股票代码，股票简称，当日最高价",
]
output = {"trade_date": DAY, "fetched_at": datetime.now(timezone.utc).isoformat(),
          "source": "iFinD official smart_stock_picking HTTP API", "verified": False,
          "queries": [], "records": [], "count": 0,
          "note": "Candidates only; no independent comparison with prior historical intraday highs."}
session = requests.Session()

def access_token():
    if REFRESH:
        response = session.post(BASE + "/get_access_token",
            headers={"Content-Type": "application/json", "refresh_token": REFRESH}, timeout=30)
        response.raise_for_status()
        body = response.json()
        if body.get("errorcode", 0) != 0:
            raise RuntimeError("iFinD token API error: " + str(body.get("errorcode")) + " " + str(body.get("errmsg", "")))
        token = (body.get("data") or {}).get("access_token")
        if not token:
            raise RuntimeError("iFinD token API response lacks data.access_token")
        return token
    if ACCESS:
        return ACCESS
    raise RuntimeError("MISSING_IFIND_TOKEN: set IFIND_REFRESH_TOKEN (preferred) or IFIND_ACCESS_TOKEN as GitHub Actions secret")

def rows_from_response(body):
    """Preserve raw response separately; parse common iFinD table layouts conservatively."""
    tables = body.get("tables")
    if isinstance(tables, dict):
        tables = [tables]
    rows = []
    for table in tables if isinstance(tables, list) else []:
        if not isinstance(table, dict):
            continue
        data = table.get("table", table.get("data"))
        if isinstance(data, list):
            rows.extend(r for r in data if isinstance(r, dict))
        elif isinstance(data, dict):
            keys = list(data)
            values = list(data.values())
            if values and all(isinstance(v, list) for v in values):
                rows.extend(dict(zip(keys, v)) for v in zip(*values))
            else:
                rows.append(data)
    if not rows and isinstance(body.get("data"), list):
        rows.extend(r for r in body["data"] if isinstance(r, dict))
    return rows

def normalize(row):
    keys = {str(k).lower(): k for k in row}
    def pick(*names):
        for name in names:
            for key, original in keys.items():
                if name in key:
                    value = row[original]
                    if value is not None and str(value).strip():
                        return str(value).strip()
        return ""
    code = pick("thscode", "股票代码", "证券代码", "stockcode")
    if not code:
        return None
    m = re.search(r"(?<!\d)\d{6}(?!\d)", code)
    if not m:
        return None
    return {"code": m.group(), "name": pick("股票简称", "股票名称", "证券简称", "secname", "stockname"),
            "high": pick("最高价", "high"), "raw": row}

try:
    token = access_token()
    merged = {}
    for question in questions:
        item = {"question": question}
        try:
            response = session.post(BASE + "/smart_stock_picking",
                headers={"Content-Type": "application/json", "access_token": token, "ifindlang": "cn"},
                json={"searchstring": question, "searchtype": "stock"}, timeout=60)
            item["http_status"] = response.status_code
            response.raise_for_status()
            body = response.json()
            item["errorcode"] = body.get("errorcode")
            item["errmsg"] = body.get("errmsg")
            item["dataVol"] = body.get("dataVol")
            # Save full server response to inspect all fields and missing candidates.
            item["response"] = body
            if body.get("errorcode") != 0:
                raise RuntimeError(f"iFinD API errorcode={body.get('errorcode')}: {body.get('errmsg')}")
            rows = rows_from_response(body)
            item["parsed_rows"] = len(rows)
            for row in rows:
                rec = normalize(row)
                if rec:
                    code = rec["code"]
                    if code not in merged:
                        merged[code] = dict(rec, matched_queries=[])
                    merged[code]["matched_queries"].append(question)
            item["parsed_codes"] = len([r for r in rows if normalize(r)])
            if not rows:
                item["warning"] = "API success but no parseable rows; inspect response and confirm actual stock count"
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
        output["queries"].append(item)
    output["records"] = list(merged.values())
    output["count"] = len(merged)
    output["api_success"] = any(q.get("errorcode") == 0 for q in output["queries"])
    output["usable"] = output["api_success"] and bool(merged)
except Exception as exc:
    output["fatal_error"] = f"{type(exc).__name__}: {exc}"
finally:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"date": DAY, "count": output["count"],
        "api_success": output.get("api_success", False),
        "usable": output.get("usable", False),
        "errors": [q.get("error") for q in output["queries"] if q.get("error")],
        "fatal_error": output.get("fatal_error")}, ensure_ascii=False))
if not output.get("usable"):
    sys.exit(1)
