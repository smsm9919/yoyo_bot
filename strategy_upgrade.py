# strategy_upgrade.py — Pro decision layer (no API calls)
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

@dataclass
class Params:
    rsi_buy: float = 55.0
    rsi_sell: float = 45.0
    adx_min: float = 23.0
    adx_strong: float = 28.0
    range_min_pct: float = 1.0
    require_h1_alignment: bool = False
    block_same_dir_minutes: int = 45
    min_tp_percent: float = 0.60

@dataclass
class Guard:
    spike_1bar_atr: float = 2.0
    move_3bars_pct: float = 3.0
    early_window_min: int = 10
    early_adverse_atr: float = 1.5
    trail_start_atr: float = 1.0
    trail_step_atr: float = 0.5

class StrategyUpgrade:
    def __init__(self, p: Params = Params(), g: Guard = Guard()):
        self.p = p; self.g = g

    def decide(self, s: Dict[str, Any]) -> Dict[str, Any]:
        r: List[str] = []
        price=s["price"]; atr=s["atr"]; ema200=s["ema200"]; rsi=s["rsi"]; adx=s["adx"]
        st = 1 if int(s.get("supertrend", 1))>0 else -1
        sma3, sma5, sma7 = s["sma3"], s["sma5"], s["sma7"]
        prange = s["range"]; last_dir=s.get("last_direction")
        mins = int(s.get("mins_since_last_trade", 9_999)); spike=bool(s.get("spike", False))

        ok=True
        if prange < self.p.range_min_pct: ok=False; r.append(f"Range<{self.p.range_min_pct}%")
        if adx < self.p.adx_min:          ok=False; r.append(f"ADX<{self.p.adx_min}")
        if spike:                         ok=False; r.append("Spike bar")

        bull = (price>ema200 and st>0 and sma3>sma5> sma7 and rsi>=self.p.rsi_buy)
        bear = (price<ema200 and st<0 and sma3<sma5<sma7 and rsi<=self.p.rsi_sell)

        if last_dir and mins < self.p.block_same_dir_minutes:
            if (last_dir=="BUY" and bull) or (last_dir=="SELL" and bear):
                ok=False; r.append(f"SameDir<{self.p.block_same_dir_minutes}m")

        side = "BUY" if (ok and bull) else ("SELL" if (ok and bear) else None)
        tp_mult = 1.8 if adx>=self.p.adx_strong else 1.3
        est_tp_pct = (tp_mult*atr/price*100) if (atr>0 and price>0) else 0.0
        return {"enter": bool(side) and ok, "side": side, "reasons": r if not side else [],
                "est_tp_percent": est_tp_pct, "min_tp_percent": self.p.min_tp_percent, "tp_mult": tp_mult}

    def pre_trade(self, s: Dict[str, Any], side: Optional[str]):
        ok=True; r=[]
        price=s["price"]; prev=s.get("prev", price); atr=s["atr"]; pct3=float(s.get("pct3", 0.0))
        if atr>0 and abs(price-prev)>self.g.spike_1bar_atr*atr: ok=False; r.append(f"1bar spike>{self.g.spike_1bar_atr}*ATR")
        if abs(pct3)>self.g.move_3bars_pct: ok=False; r.append(f"3bars>{self.g.move_3bars_pct}%")
        adx=s.get("adx",0.0); ema200=s.get("ema200",0.0); st=1 if int(s.get("supertrend",1))>0 else -1
        if side=="BUY" and adx>=28.0 and not(price>ema200 and st>0): ok=False; r.append("Counter-trend (strong ADX)")
        if side=="SELL" and adx>=28.0 and not(price<ema200 and st<0): ok=False; r.append("Counter-trend (strong ADX)")
        return ok, r
