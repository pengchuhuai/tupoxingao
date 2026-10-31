"""Research-only, end-of-day backtest. No orders, no fabricated returns."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

def load_bars(path):
    d = pd.read_csv(path, dtype={"trade_date": str}).sort_values("trade_date").drop_duplicates("trade_date").copy()
    for c in ("open","high","low","close","vol"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["open","high","low","close","vol"]).reset_index(drop=True)
    d["ma10"] = d.close.rolling(10).mean()
    d["ma20"] = d.close.rolling(20).mean()
    d["ma60"] = d.close.rolling(60).mean()
    d["prior_high"] = d.high.cummax().shift(1)
    d["breakout"] = (d.high > d.prior_high) & d.prior_high.notna()
    d["prev_vol5"] = d.vol.shift(1).rolling(5).mean()
    return d

def market_regime(index_bars, date):
    if index_bars is None:
        return "unknown"
    past = index_bars[index_bars.trade_date < date]
    if len(past) < 60:
        return "unknown"
    r = past.iloc[-1]
    if r.close > r.ma20 > r.ma60:
        return "up"
    if r.close < r.ma20 < r.ma60:
        return "down"
    return "sideways"

def backtest(history_dir, index_path=None, stop_pct=0.08, max_hold=20, fee_bps=15):
    index = load_bars(index_path) if index_path else None
    events, trades = [], []
    for path in sorted(Path(history_dir).glob("*.csv.gz")):
        try:
            d = load_bars(path)
        except (ValueError, KeyError, OSError):
            continue
        code = path.name.replace(".csv.gz", "")
        for i in np.flatnonzero(d.breakout.to_numpy()):
            if i + 21 >= len(d):
                continue
            row = d.iloc[i]
            date = str(row.trade_date)
            regime = market_regime(index, date)
            future = d.iloc[i+1:i+21]
            if len(future) < 20:
                continue
            # Signal known only at the close; evaluate future CLOSES, not intraday execution.
            e = {"code":code,"breakout_date":date,"regime":regime,
                 "ret_5d":float(future.iloc[4].close/row.close-1),
                 "ret_10d":float(future.iloc[9].close/row.close-1),
                 "ret_20d":float(future.iloc[19].close/row.close-1)}
            events.append(e)
            # First MA10 touch strictly after breakout, using adjusted basis only if separately modeled.
            first = None
            for j in range(i+1,min(i+21,len(d)-1)):
                b = d.iloc[j]
                if pd.isna(b.ma10) or pd.isna(b.prev_vol5):
                    continue
                if b.low <= b.ma10*1.01 and b.high >= b.ma10*0.99:
                    first = j
                    break
            if first is None:
                continue
            b = d.iloc[first]
            valid = bool(b.vol < b.prev_vol5 and b.open >= d.iloc[first-1].close and b.close >= b.ma10)
            if not valid:
                continue
            # Signal confirmed at touch close; enter NEXT session open (avoid lookahead).
            entry_idx = first+1
            entry = float(d.iloc[entry_idx].open)
            if entry <= 0:
                continue
            exit_idx = min(entry_idx+max_hold, len(d)-1)
            reason = "max_hold"
            # Daily stops: if opening gap breaches stop, fill at open; otherwise stop threshold.
            exit_price = float(d.iloc[exit_idx].close)
            for k in range(entry_idx, exit_idx+1):
                bar = d.iloc[k]
                stop = entry*(1-stop_pct)
                if bar.open <= stop:
                    exit_idx,exit_price,reason = k,float(bar.open),"gap_stop"
                    break
                if bar.low <= stop:
                    exit_idx,exit_price,reason = k,stop,"stop"
                    break
                # Exit on trend weakness, next open; signal based on current close.
                if k < exit_idx and pd.notna(bar.ma20) and bar.close < bar.ma20:
                    exit_idx,exit_price,reason = k+1,float(d.iloc[k+1].open),"trend"
                    break
            trades.append({"code":code,"breakout_date":date,"entry_date":str(d.iloc[entry_idx].trade_date),
                "exit_date":str(d.iloc[exit_idx].trade_date),"regime":regime,
                "return_net":float(exit_price/entry-1-fee_bps/10000),
                "exit_reason":reason})
    return events,trades

def summarize(events,trades):
    def stats(rows,key):
        if not rows:
            return {"n":0,"mean":None,"win_rate":None}
        v=np.array([r[key] for r in rows],dtype=float)
        return {"n":len(v),"mean":round(float(v.mean()),6),"win_rate":round(float((v>0).mean()),4)}
    return {"sample":"signal-level overlapping observations; NOT portfolio PnL",
        "breakouts":{h:stats(events,h) for h in ("ret_5d","ret_10d","ret_20d")},
        "trades":stats(trades,"return_net"),
        "by_regime":{r:{"breakout_20d":stats([x for x in events if x["regime"]==r],"ret_20d"),
                        "trades":stats([x for x in trades if x["regime"]==r],"return_net")}
                     for r in ("up","sideways","down","unknown")},
        "limitations":["No sector-relative ranking without historical point-in-time sector memberships and sector bars",
          "No reliable historical capital-flow series: flow exit NOT tested",
          "No price-limit, suspension, lot-size, realistic slippage or portfolio capital constraints",
          "Raw-price MA10 only; adjusted-price backtest needs consistent adjusted OHLC",
          "Repeated breakout events overlap; outcomes are not independent",
          "Index regime requires separately supplied historical index CSV; otherwise unknown"]}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--history",default="data/history")
    ap.add_argument("--index",default=None)
    ap.add_argument("--output",default="data/backtest.json")
    args=ap.parse_args()
    events,trades=backtest(args.history,args.index)
    result=summarize(events,trades)
    result["data_files"]=len(list(Path(args.history).glob("*.csv.gz")))
    result["status"]="no_history" if result["data_files"]==0 else "partial_research"
    p=Path(args.output);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"files":result["data_files"],
                      "events":len(events),"trades":len(trades)},ensure_ascii=False))
if __name__=="__main__":
    main()
