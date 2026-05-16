"""L5 持仓审计 — T/B/F/R 四维评分"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import config
from core.logging import get_logger
from layer3_analysis.technical import compute
logger = get_logger("audit")

def audit():
    r = {}
    for s in config.stocks:
        c, n, cost, stop, tgt = s["code"], s["name"], s.get("cost",0), s.get("stop",0), s.get("target",0)
        t = compute(c)
        if "error" in t: r[c] = {**s, "error": t["error"], "action": "HOLD"}; continue
        p = t.get("price", 0)

        # T=趋势
        abv20 = p > t.get("ma20", p); abv10 = p > t.get("ma10", p); rsi = t.get("rsi14", 50)
        T = 8 if (abv20 and abv10 and rsi > 50) else (6 if abv20 else (4 if abv10 else 2))

        # B=买入信号
        drop = abs(t.get("pct_ma20", 0))
        B = 7 if (drop > 5 and rsi < 40) else (5 if (drop > 3 or rsi < 45) else (3 if (drop < 2 and rsi > 60) else 5))

        # F=基本面(盈亏状态)
        pct_c = (p / cost - 1) * 100 if cost else 0
        F = 8 if pct_c > 10 else (6 if pct_c > 0 else (4 if pct_c > -10 else 2))

        # R=风险(距止损距离)
        dts = (p / stop - 1) * 100 if stop else 100
        R = 8 if dts > 20 else (6 if dts > 10 else (4 if dts > 5 else 2))

        tot = (T + B + F + R) / 4
        act = "ADD" if tot >= 7 else ("HOLD" if tot >= 5 else ("REDUCE" if tot >= 3 else "CLOSE"))
        r[c] = {**s, "price": p, "scores": {"T": T, "B": B, "F": F, "R": R}, "total": round(tot, 1), "action": act,
                "pct_cost": round(pct_c, 2), "rsi": rsi}

    return dict(sorted(r.items(), key=lambda x: x[1].get("total", 0), reverse=True))
