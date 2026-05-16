"""L2 数据管线 — 自动采集+健康检查+K线补齐+DB自修复"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import config
from core.database import db
from core.dbfix import run as dbfix_run
from core.logging import get_logger
from layer1_data.tencent_api import get_all_quotes, get_indices

logger = get_logger("pipeline")


def health() -> dict:
    s = {"ok": True, "checks": {}}
    try:
        db.query_one("SELECT 1")
        s["checks"]["database"] = "ok"
    except Exception as e:
        s["checks"]["database"] = str(e)
        s["ok"] = False

    try:
        now = datetime.now().strftime("%Y%m%d")
        rows = db.query("SELECT ts_code, MAX(trade_date) as last FROM stock_daily GROUP BY ts_code")
        stale = [r for r in rows if (r.get("last") or "") < now]
        s["checks"]["freshness"] = {
            "total": len(rows),
            "stale": len(stale),
            "sample": [r.get("ts_code") for r in stale[:5]],
        }
    except Exception as e:
        s["checks"]["freshness"] = str(e)

    return s


def backfill_kline(n_days: int = 60) -> dict:
    """当本地K线不足时，用 TuShare 补齐到 n_days。"""
    if not config.get("data_sources", "tushare", "enabled", default=True):
        return {"enabled": False, "filled": 0, "skipped": 0, "errors": 0}
    if not config.get("data_sources", "tushare", "backfill", default=False):
        return {"enabled": False, "filled": 0, "skipped": 0, "errors": 0}

    from layer1_data.tushare_api import fetch_last_n_trading_days

    filled = 0
    skipped = 0
    errors = 0

    for s in config.stocks:
        code = s["code"]
        try:
            row = db.query_one("SELECT COUNT(*) AS cnt FROM stock_daily WHERE ts_code=?", (code,))
            cnt = row.get("cnt", 0) if isinstance(row, dict) else 0
            if cnt >= n_days:
                skipped += 1
                continue

            rows = fetch_last_n_trading_days(code, n_days)
            for r in rows:
                db.execute(
                    "INSERT OR REPLACE INTO stock_daily (ts_code,trade_date,open,high,low,close,vol,amount,pct_chg) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        r.get("ts_code"),
                        str(r.get("trade_date")),
                        r.get("open"),
                        r.get("high"),
                        r.get("low"),
                        r.get("close"),
                        r.get("vol"),
                        r.get("amount"),
                        r.get("pct_chg"),
                    ),
                )

            filled += 1
        except Exception as e:
            errors += 1
            logger.error(f"backfill失败 {code}: {e}")

    return {"enabled": True, "filled": filled, "skipped": skipped, "errors": errors}


def run(brief: bool = False):
    t0 = datetime.now()
    r = {"time": t0.strftime("%Y-%m-%d %H:%M:%S"), "steps": {}, "status": "ok"}

    logger.info("Step 0: DB自修复")
    r["steps"]["dbfix"] = dbfix_run(auto_fix=True)

    logger.info("Step 1: 健康检查")
    h = health()
    r["steps"]["health"] = h
    if not h.get("ok"):
        r["status"] = "degraded"

    logger.info("Step 1b: K线补齐")
    n_days = config.get("data_sources", "tushare", "backfill_days", default=60)
    bf = backfill_kline(int(n_days or 60))
    r["steps"]["backfill"] = bf

    logger.info("Step 2: 实时行情")
    qs = get_all_quotes()
    idx = get_indices()
    r["steps"]["realtime"] = {"stocks": len(qs), "indices": {k: v.get("price") for k, v in idx.items()}}

    if not brief:
        logger.info("Step 3: 存储行情")
        now = datetime.now().strftime("%Y%m%d")
        saved = 0
        for c, d in qs.items():
            if d.get("price"):
                try:
                    db.execute(
                        "INSERT OR REPLACE INTO stock_daily (ts_code,trade_date,open,high,low,close,vol,amount,pct_chg) VALUES (?,?,?,?,?,?,?,?,?)",
                        (c, now, d.get("open"), d.get("high"), d.get("low"), d.get("price"), d.get("volume"), d.get("amount"), d.get("pct_chg")),
                    )
                    saved += 1
                except Exception:
                    pass
        r["steps"]["storage"] = {"saved": saved}

    r["elapsed"] = round((datetime.now() - t0).total_seconds(), 1)
    logger.info(f"管线完成 {r['elapsed']}s")
    return r
