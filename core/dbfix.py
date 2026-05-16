"""数据库自修复：统一 trade_date 格式、做基础一致性检查"""
from __future__ import annotations

import re
from typing import Dict

from core.database import db
from core.logging import get_logger

logger = get_logger("dbfix")

DATE8 = re.compile(r"^\d{8}$")
DATE10 = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalize_trade_date(v: str) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if DATE8.match(s):
        return s
    if DATE10.match(s):
        return s.replace("-", "")
    # 其它格式不自动修
    return None


def fix_trade_date_formats(limit: int | None = None) -> Dict:
    """把 stock_daily.trade_date 从 YYYY-MM-DD 迁移为 YYYYMMDD。

    策略：逐行迁移：INSERT OR REPLACE 新日期行 -> 删除旧日期行。
    这样可以规避唯一键冲突（若存在 (ts_code, trade_date) 唯一约束）。
    """
    rows = db.query(
        "SELECT ts_code, trade_date, open, high, low, close, vol, amount, pct_chg "
        "FROM stock_daily WHERE trade_date LIKE '%-%'"
    )
    if limit:
        rows = rows[: int(limit)]

    changed = 0
    skipped = 0
    errors = 0

    for r in rows:
        try:
            ts_code = r.get("ts_code")
            old = r.get("trade_date")
            new = normalize_trade_date(old)
            if not new or new == old:
                skipped += 1
                continue

            db.execute(
                "INSERT OR REPLACE INTO stock_daily (ts_code, trade_date, open, high, low, close, vol, amount, pct_chg) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    ts_code,
                    new,
                    r.get("open"),
                    r.get("high"),
                    r.get("low"),
                    r.get("close"),
                    r.get("vol"),
                    r.get("amount"),
                    r.get("pct_chg"),
                ),
            )
            db.execute("DELETE FROM stock_daily WHERE ts_code=? AND trade_date=?", (ts_code, old))
            changed += 1
        except Exception as e:
            errors += 1
            logger.error(f"trade_date 修复失败 {r.get('ts_code')} {r.get('trade_date')}: {e}")

    return {"checked": len(rows), "changed": changed, "skipped": skipped, "errors": errors}


def summary() -> Dict:
    total = db.query_one("SELECT COUNT(*) AS c FROM stock_daily")
    bad = db.query_one("SELECT COUNT(*) AS c FROM stock_daily WHERE trade_date LIKE '%-%'")
    return {
        "total_rows": (total or {}).get("c"),
        "bad_trade_date_rows": (bad or {}).get("c"),
    }


def run(auto_fix: bool = True) -> Dict:
    before = summary()
    fixed = None
    if auto_fix and before.get("bad_trade_date_rows"):
        fixed = fix_trade_date_formats()
    after = summary()
    return {"before": before, "fixed": fixed, "after": after}
