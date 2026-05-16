"""L3 技术面 — 六因子均值回归评分（继承原版quant_analytics逻辑）"""
import numpy as np, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.database import db
from core.config import config
from core.logging import get_logger
logger = get_logger("technical")

def load_kline(code, n=60):
    return db.query("SELECT trade_date,open,high,low,close,vol,pct_chg FROM stock_daily WHERE ts_code=? ORDER BY trade_date DESC LIMIT ?", (code, n))

def _rsi(closes, p=14):
    if len(closes) < p + 1: return 50
    g = l = 0
    for i in range(p):
        d = closes[i] - closes[i + 1]
        if d > 0: g += d
        else: l -= d
    if l == 0: return 100
    return round(100 - 100 / (1 + g / l), 1)

def _atr(highs, lows, closes, p=14):
    if len(closes) < p + 1: return 0
    trs = [max(highs[i] - lows[i], abs(highs[i] - closes[i + 1]), abs(lows[i] - closes[i + 1])) for i in range(len(closes) - 1)]
    return float(np.mean(trs[:p]))

def _consec(pct_chgs):
    days = cum = 0
    for chg in pct_chgs:
        if chg is None: break
        if days == 0: days = 1 if chg > 0 else (-1 if chg < 0 else 0); cum = chg
        elif (days > 0 and chg > 0) or (days < 0 and chg < 0): days += 1 if days > 0 else -1; cum += chg
        else: break
    return {"days": days, "cum": cum}

def compute(code):
    rows = load_kline(code, 60)
    if len(rows) < 10: return {"error": "数据不足(<10行)"}

    closes = [r["close"] for r in rows]
    highs = [r["high"] for r in rows]; lows = [r["low"] for r in rows]
    pct_chgs = [r["pct_chg"] for r in rows]; vols = [r["vol"] for r in rows]

    price = closes[0]
    ma5 = np.mean(closes[:5]) if len(closes) >= 5 else price
    ma10 = np.mean(closes[:10]) if len(closes) >= 10 else price
    ma20 = np.mean(closes[:20]) if len(closes) >= 20 else price
    rsi14 = _rsi(closes, 14)
    atr14 = _atr(highs, lows, closes, 14)
    cons = _consec(pct_chgs)
    vol5 = np.mean(vols[1:6]) if len(vols) >= 6 else vols[0]

    return {
        "price": price, "ma5": ma5, "ma10": ma10, "ma20": ma20, "rsi14": rsi14,
        "pct_ma10": round((price / ma10 - 1) * 100, 2) if ma10 else 0,
        "pct_ma20": round((price / ma20 - 1) * 100, 2) if ma20 else 0,
        "atr14": round(atr14, 2), "atr_pct": round(atr14 / price * 100, 2) if price else 0,
        "vol_ratio": round(vols[0] / vol5, 2) if vol5 else 1,
        "cons_days": cons["days"], "cons_cum": round(cons["cum"], 2),
        "points": len(rows),
    }

def score(techs, weights=None):
    """六因子评分"""
    if weights is None: weights = config.weights
    f = {}
    drop = abs(techs.get("pct_ma20", 0))
    f["回撤深度"] = min(drop / 10, 1.0)
    rsi = techs.get("rsi14", 50)
    f["超卖强度"] = max(0, min(1, (50 - rsi) / 30))
    cons = techs.get("cons_days", 0)
    f["连跌衰竭"] = min(abs(cons) / 5, 1.0) if cons < 0 else 0
    vr = techs.get("vol_ratio", 1)
    f["量价背离"] = max(0, min(1, 1 - vr / 2)) if cons < 0 else 0.3
    atr_pct = techs.get("atr_pct", 5)
    f["波动收敛"] = max(0, min(1, 1 - atr_pct / 10))
    f["支撑强度"] = max(0, min(1, 1 - drop / 15))
    total = sum(f.get(k, 0) * weights.get(k, 0) for k in weights)
    sig = "BUY" if total >= 0.6 else ("WATCH" if total >= 0.4 else "WAIT")
    return {"scores": {k: round(v, 3) for k, v in f.items()}, "total": round(total, 4), "signal": sig}

def score_all():
    r = {}
    for s in config.stocks:
        c = s["code"]
        t = compute(c)
        if "error" in t: r[c] = {**s, "error": t["error"]}; continue
        sc = score(t)
        r[c] = {**s, "technicals": t, "factors": sc["scores"], "total": sc["total"], "signal": sc["signal"]}
    return dict(sorted(r.items(), key=lambda x: x[1].get("total", 0), reverse=True))
