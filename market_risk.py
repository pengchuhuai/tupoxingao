"""Research-only market risk budget; no orders or invented market scores."""
from dataclasses import dataclass
from typing import Optional

WEIGHTS={"trend":40,"breadth":25,"volume":20,"sectors":15}

@dataclass(frozen=True)
class MarketAssessment:
    score: Optional[float]
    regime: str
    max_exposure: float
    components: dict
    reason: str

def assess_market(trend=None,breadth=None,volume=None,sectors=None):
    parts=dict(trend=trend,breadth=breadth,volume=volume,sectors=sectors)
    missing=[k for k,v in parts.items() if v is None]
    if missing:
        return MarketAssessment(None,"unknown",0.0,parts,"Missing verified inputs: "+", ".join(missing))
    for k,v in parts.items():
        if not isinstance(v,(int,float)) or not 0<=v<=100:
            raise ValueError(f"{k} must be a verified 0-100 subscore")
    score=sum(parts[k]*WEIGHTS[k]/100 for k in WEIGHTS)
    if score>=80:
        return MarketAssessment(round(score,2),"strong_up",1.0,parts,"research threshold")
    if score>=60:
        return MarketAssessment(round(score,2),"sideways_up",0.6,parts,"research threshold")
    if score>=40:
        return MarketAssessment(round(score,2),"sideways_down",0.3,parts,"research threshold")
    return MarketAssessment(round(score,2),"down",0.1,parts,"research threshold")

def size_position(equity,cash,price,stop_price,current_total_exposure,sector_exposure,
                  assessment,lot=100,risk_fraction=0.01,single_cap=0.20,sector_cap=0.40):
    """Return board-lot shares; existing exposure inputs are fractions of current equity."""
    if assessment.regime=="unknown" or equity<=0 or cash<=0 or price<=0 or stop_price<=0 or stop_price>=price:
        return 0
    risk_per_share=price-stop_price
    limits=[equity*risk_fraction/risk_per_share,
            equity*single_cap/price,
            equity*max(0,sector_cap-sector_exposure)/price,
            equity*max(0,assessment.max_exposure-current_total_exposure)/price,
            cash/price]
    return max(0,int(min(limits)//lot)*lot)

def decision(trend=None,breadth=None,volume=None,sectors=None):
    a=assess_market(trend,breadth,volume,sectors)
    return {"score":a.score,"regime":a.regime,"max_exposure":a.max_exposure,
            "components":a.components,"reason":a.reason,
            "policy":"No trade with missing inputs. Research thresholds only."}
