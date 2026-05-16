"""L5 持仓审计 — T/B/F/R 四维评分（T 维度已激活趋势因子）

T = 趋势因子 (layer3_analysis/trend.py 的 MA排列/ADX/MACD/相对强度)
B = 买入时机 (均值回归信号)
F = 基本面 (盈亏状态)
R = 风险 (距止损距离)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import config
from core.logging import get_logger
from layer3_analysis.technical import compute as tech_compute
from layer3_analysis.trend import compute_all as trend_compute

logger = get_logger("audit")


def audit() -> dict:
    r = {}
    for s in config.stocks:
        code, name, cost = s["code"], s["name"], s.get("cost", 0)
        stop = s.get("stop", 0)
        tgt = s.get("target", 0)

        t = tech_compute(code)
        if "error" in t:
            r[code] = {**s, "error": t["error"], "action": "HOLD"}
            continue
        price = t.get("price", 0)

        # ── T = 趋势因子（已激活 trend.py）──
        trend = trend_compute(code, 60)
        trend_total = trend.get("trend_total", 5)
        ma_status = trend.get("ma_status", "unknown")
        adx_val = trend.get("adx", 0)
        macd_div = trend.get("divergence", "none")

        # 趋势映射到 2-10 分
        if trend_total >= 8:
            T = 10
        elif trend_total >= 6.5:
            T = 8
        elif trend_total >= 5:
            T = 6
        elif trend_total >= 3.5:
            T = 4
        else:
            T = 2

        # MACD 背离额外调整
        if macd_div == "bullish_divergence":
            T = min(10, T + 1)
        elif macd_div == "bearish_divergence":
            T = max(2, T - 1)

        # ── B = 买入信号 ──
        drop = abs(t.get("pct_ma20", 0))
        rsi_val = t.get("rsi14", 50)
        B = 7 if (drop > 5 and rsi_val < 40) else (5 if (drop > 3 or rsi_val < 45) else (3 if (drop < 2 and rsi_val > 60) else 5))

        # ── F = 基本面(盈亏状态) ──
        pct_c = (price / cost - 1) * 100 if cost else 0
        F = 8 if pct_c > 10 else (6 if pct_c > 0 else (4 if pct_c > -10 else 2))

        # ── R = 风险(距止损距离) ──
        dts = (price / stop - 1) * 100 if stop else 100
        R = 8 if dts > 20 else (6 if dts > 10 else (4 if dts > 5 else 2))

        tot = (T + B + F + R) / 4
        act = "ADD" if tot >= 7 else ("HOLD" if tot >= 5 else ("REDUCE" if tot >= 3 else "CLOSE"))

        r[code] = {
            **s,
            "price": price,
            "scores": {"T": T, "B": B, "F": F, "R": R},
            "total": round(tot, 1),
            "action": act,
            "pct_cost": round(pct_c, 2),
            "rsi": rsi_val,
            "_trend_detail": {
                "trend_total": trend_total,
                "ma_status": ma_status,
                "adx": adx_val,
                "macd_divergence": macd_div,
            },
        }

    return dict(sorted(r.items(), key=lambda x: x[1].get("total", 0), reverse=True))
