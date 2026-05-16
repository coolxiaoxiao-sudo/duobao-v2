"""Obsidian 输出 — 将分析结果自动写入笔记库（SOLO专区）"""
import os, sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import config
from core.logging import get_logger

logger = get_logger("obsidian_out")


def _vault() -> str:
    return config.get("system", "obsidian_vault", default="")


def _root_dir() -> str:
    # 用于与其他工具/Claude Code 共用 Obsidian Vault 时隔离输出
    return config.get("notifications", "obsidian", "root_dir", default="")


def _root_path() -> str:
    v = _vault()
    r = _root_dir()
    return os.path.join(v, r) if r else v


def _ensure_home() -> None:
    """确保专区有一个 HOME/索引页，方便回跳。"""
    try:
        root = _root_path()
        if not root:
            return
        os.makedirs(root, exist_ok=True)
        p = os.path.join(root, "HOME.md")
        if os.path.exists(p):
            return
        with open(p, "w", encoding="utf-8") as f:
            f.write(
                "# SOLO · 多宝 v2\n\n"
                "这是 SOLO 生成的分析内容专区（与其他工具输出隔离）。\n\n"
                "## 快速入口\n"
                "- [[30-日报/]]\n"
                "- [[10-交易/交易日志/]]\n"
            )
    except Exception as e:
        logger.warning(f"HOME 初始化失败: {e}")


def save_daily(report_text, date_str=None):
    if not config.get("notifications", "obsidian", "enabled", default=True):
        return

    _ensure_home()

    ds = date_str or datetime.now().strftime("%Y-%m-%d")
    daily_rel = config.get("notifications", "obsidian", "daily_report_path", default="30-日报")
    d = os.path.join(_root_path(), daily_rel)
    os.makedirs(d, exist_ok=True)

    p = os.path.join(d, f"盘后报告-{ds}.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(
            f"---\n"
            f"date: {ds}\n"
            f"tags: [日报, 盘后报告, 多宝v2, SOLO]\n"
            f"---\n\n"
            f"# 盘后报告 {ds}\n\n"
            f"{report_text}\n\n"
            f"---\n"
            f"> [[HOME|← 返回SOLO专区]]\n"
        )

    logger.info(f"日报已存: {p}")


def save_audit(audit_data, date_str=None):
    if not config.get("notifications", "obsidian", "enabled", default=True):
        return

    _ensure_home()

    ds = date_str or datetime.now().strftime("%Y-%m-%d")
    trade_rel = config.get("notifications", "obsidian", "trade_log_path", default="10-交易/交易日志")
    d = os.path.join(_root_path(), trade_rel)
    os.makedirs(d, exist_ok=True)

    p = os.path.join(d, f"持仓审计-{ds}.md")
    lines = [
        f"---\n"
        f"date: {ds}\n"
        f"tags: [审计, 持仓, 多宝v2, SOLO]\n"
        f"---\n\n"
        f"# 持仓审计 {ds}\n"
    ]

    for _, a in audit_data.items():
        sc = a.get("scores", {})
        lines.append(f"## {a.get('name','?')} — {a.get('action','?')} (总分 {a.get('total','?')})\n")
        lines.append(f"- 现价: {a.get('price','?')} | 成本: {a.get('cost','?')}")
        lines.append(
            f"- T趋势:{sc.get('T','?')} B买入:{sc.get('B','?')} F基本面:{sc.get('F','?')} R风险:{sc.get('R','?')}\n"
        )

    lines.append("---\n> [[HOME|← 返回SOLO专区]]\n")

    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info(f"审计已存: {p}")
