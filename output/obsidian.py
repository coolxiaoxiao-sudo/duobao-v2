"""Obsidian 输出 — 将分析结果自动写入 solo 仓库（并自动更新 HOME）"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import config
from core.logging import get_logger

logger = get_logger("obsidian_out")


def _vault() -> str:
    return config.get("system", "obsidian_vault", default="")


def _root_dir() -> str:
    # 如果你仍使用同一 Vault 多系统共存，可用 root_dir 做隔离；solo 独立仓库场景通常为空
    return config.get("notifications", "obsidian", "root_dir", default="")


def _root_path() -> str:
    v = _vault()
    r = _root_dir()
    return os.path.join(v, r) if r else v


def _home_path() -> str:
    return os.path.join(_root_path(), "HOME.md")


def _write_home(last_date: str | None = None) -> None:
    """每次输出后更新 HOME，让你打开仓库第一眼就看到入口。"""
    try:
        root = _root_path()
        if not root:
            return
        os.makedirs(root, exist_ok=True)

        ds = last_date or datetime.now().strftime("%Y-%m-%d")
        daily_rel = config.get("notifications", "obsidian", "daily_report_path", default="30-日报")
        audit_rel = config.get("notifications", "obsidian", "trade_log_path", default="10-交易/交易日志")

        content = (
            "---\n"
            "tags: [SOLO, 多宝v2]\n"
            "---\n\n"
            "# HOME（SOLO · 多宝 v2）\n\n"
            f"- 更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            "## 今日入口\n"
            f"- [[{daily_rel}/盘后报告-{ds}|📝 盘后报告-{ds}]]\n"
            f"- [[{audit_rel}/持仓审计-{ds}|📋 持仓审计-{ds}]]\n\n"
            "## 目录\n"
            f"- [[{daily_rel}/|30-日报]]\n"
            f"- [[{audit_rel}/|10-交易/交易日志]]\n"
        )

        with open(_home_path(), "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        logger.warning(f"HOME 更新失败: {e}")


def save_daily(report_text, date_str=None):
    if not config.get("notifications", "obsidian", "enabled", default=True):
        return

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
            f"> [[HOME|← 返回HOME]]\n"
        )

    _write_home(last_date=ds)
    logger.info(f"日报已存: {p}")


def save_audit(audit_data, date_str=None):
    if not config.get("notifications", "obsidian", "enabled", default=True):
        return

    ds = date_str or datetime.now().strftime("%Y-%m-%d")
    audit_rel = config.get("notifications", "obsidian", "trade_log_path", default="10-交易/交易日志")
    d = os.path.join(_root_path(), audit_rel)
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

    lines.append("---\n> [[HOME|← 返回HOME]]\n")

    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    _write_home(last_date=ds)
    logger.info(f"审计已存: {p}")
