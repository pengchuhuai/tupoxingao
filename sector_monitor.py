"""Separate verified all-time intraday highs from media closing-high candidates."""
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

def read(path, default):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

def build(root=Path("data"), as_of=None):
    root = Path(root)
    status = read(root / "status.json", {})
    as_of = as_of or status.get("as_of") or datetime.now().strftime("%Y%m%d")
    as_of = as_of.replace("-", "")
    industry = read(root / "industry_map.json", {})
    start5 = (datetime.strptime(as_of, "%Y%m%d") - timedelta(days=7)).strftime("%Y%m%d")
    start10 = (datetime.strptime(as_of, "%Y%m%d") - timedelta(days=14)).strftime("%Y%m%d")
    groups = defaultdict(lambda: {"codes5": set(), "codes10": set(), "days5": set()})
    seen = set()
    for event in read(root / "breakouts.json", []):
        if event.get("basis") != "raw" or event.get("verification") != "source_history_fetched":
            continue
        code, day = event.get("ts_code", ""), event.get("date", "")
        if not (start10 <= day <= as_of) or (code, day) in seen:
            continue
        seen.add((code, day))
        name = industry.get(code) or event.get("industry") or "未分类"
        g = groups[name]
        g["codes10"].add(code)
        if day >= start5:
            g["codes5"].add(code)
            g["days5"].add(day)
    ranked = [{"industry": name, "high_stocks_5d_approx": len(g["codes5"]),
               "high_stocks_10d_approx": len(g["codes10"]),
               "days_with_highs_5d_approx": len(g["days5"]),
               "codes": sorted(g["codes10"])} for name, g in groups.items()]
    ranked.sort(key=lambda x: (-x["high_stocks_5d_approx"], -x["days_with_highs_5d_approx"], x["industry"]))
    candidates = defaultdict(set)
    for file in sorted((root / "candidates").glob("*.json")):
        obj = read(file, {})
        if str(obj.get("date", "")).replace("-", "") != as_of:
            continue
        for item in obj.get("candidates", []):
            candidates[item.get("industry") or "未分类"].add(item.get("code"))
    return {"as_of": as_of, "mode": "daily_after_close_not_realtime",
            "verified_highs_by_industry": ranked,
            "reported_closing_high_candidates_by_industry":
                [{"industry": k, "count": len(v), "codes": sorted(v)}
                 for k, v in sorted(candidates.items(), key=lambda x: (-len(x[1]), x[0]))],
            "verified_total_unique_stock_industry_pairs": sum(x["high_stocks_10d_approx"] for x in ranked),
            "window_note": "7/14 calendar-day approximate windows; not exact 5/10 trading sessions",
            "warning": "Reported closing highs are NOT verified intraday all-time highs. No live feed or verified money flow."}

def main():
    root = Path("data")
    root.mkdir(exist_ok=True)
    report = build(root)
    (root / "sector_attention.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Sector report", report["as_of"], "verified", report["verified_total_unique_stock_industry_pairs"])

if __name__ == "__main__":
    main()
