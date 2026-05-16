"""
L3 分析引擎 — 全量评分
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import config
from core.logging import get_logger
from .technical import compute_technicals, compute_factor_scores

logger = get_logger("scoring")


def score_all_stocks() -> dict:
    """对所有持仓股票计算技术评分"""
    results = {}
    weights = config.get("strategy", "factor_weights", default={})

    for stock in config.stocks:
        code = stock["code"]
        name = stock["name"]
        logger.info(f"评分: {name} ({code})")

        technicals = compute_technicals(code)
        if "error" in technicals:
            results[code] = {**stock, "error": technicals["error"], "score": 0}
            continue

        factor_result = compute_factor_scores(technicals, weights)
        results[code] = {
            **stock,
            "technicals": technicals,
            "factor_scores": factor_result["scores"],
            "total_score": factor_result["total_score"],
            "signal": factor_result["signal"],
        }

    # 按总分排序
    sorted_results = dict(
        sorted(results.items(), key=lambda x: x[1].get("total_score", 0), reverse=True)
    )
    return sorted_results
