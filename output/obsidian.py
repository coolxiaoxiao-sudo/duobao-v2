"""Obsidian 输出 — 固化“长期记忆”（持仓/操作清单/说明）并自动更新 HOME

目标：让任何新任务无需“提醒回忆”，只要读取 solo 仓库固定文件即可围绕你的投资需求工作。
"""

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
    # 若多个系统共用同一 Vault，可用 root_dir 隔离；solo 独立仓库通常为空
    return config.get("notifications", "obsidian", "root_dir", default="")


def _root_path() -> str:
    v = _vault()
    r = _root_dir()
    return os.path.join(v, r) if r else v


def _write_text(path: str, text: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _home_path() -> str:
    return os.path.join(_root_path(), "HOME.md")


def _portfolio_path() -> str:
    return os.path.join(_root_path(), "持仓清单.md")


def _action_path() -> str:
    return os.path.join(_root_path(), "今日操作清单.md")


def _system_guide_path() -> str:
    return os.path.join(_root_path(), "系统说明.md")


def update_home(last_date: str | None = None) -> None:
    """每次输出后更新 HOME，让你打开仓库第一眼看到入口。"""
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
            "## 固定入口（长期记忆）\n"
            "- [[持仓清单|📌 持仓清单]]\n"
            "- [[今日操作清单|✅ 今日操作清单]]\n"
            "- [[系统说明|ℹ️ 系统说明]]\n\n"
            "## 今日入口\n"
            f"- [[{daily_rel}/盘后报告-{ds}|📝 盘后报告-{ds}]]\n"
            f"- [[{audit_rel}/持仓审计-{ds}|📋 持仓审计-{ds}]]\n\n"
            "## 目录\n"
            f"- [[{daily_rel}/|30-日报]]\n"
            f"- [[{audit_rel}/|10-交易/交易日志]]\n"
        )

        _write_text(_home_path(), content)
    except Exception as e:
        logger.warning(f"HOME 更新失败: {e}")


def save_portfolio_snapshot(stocks: list[dict]) -> None:
    """把你的持仓“事实表”固化到 Obsidian，供新任务直接读取。"""
    try:
        rows = []
        for s in stocks:
            rows.append(
                [
                    s.get("code"),
                    s.get("name"),
                    s.get("broker", ""),
                    s.get("style", ""),
                    s.get("cost"),
                    s.get("stop"),
                    s.get("stop_type"),
                    s.get("target"),
                    s.get("note", ""),
                ]
            )

        header = ["代码", "名称", "券商", "风格", "成本", "止损", "止损类型", "目标", "备注"]
        md = []
        md.append("---")
        md.append("tags: [SOLO, 持仓, 事实表]")
        md.append("---\n")
        md.append("# 持仓清单（事实表）\n")
        md.append(f"- 更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        md.append("说明：这里记录的是系统用于分析的持仓基准（代码/成本/止损/目标/备注）。\n")
        md.append("|" + "|".join(header) + "|")
        md.append("|" + "|".join(["---"] * len(header)) + "|")
        for r in rows:
            md.append("|" + "|".join(str(x) if x is not None else "" for x in r) + "|")

        md.append("\n> 入口：[[HOME|返回HOME]]")

        _write_text(_portfolio_path(), "\n".join(md) + "\n")
    except Exception as e:
        logger.warning(f"持仓清单写入失败: {e}")


def save_action_plan(text: str, date_str: str | None = None) -> None:
    """写入今日操作清单（强执行版）。"""
    try:
        ds = date_str or datetime.now().strftime("%Y-%m-%d")
        md = []
        md.append("---")
        md.append("tags: [SOLO, 操作清单, 今日]")
        md.append("---\n")
        md.append(f"# 今日操作清单（{ds}）\n")
        md.append(text.strip() + "\n")
        md.append("> 入口：[[HOME|返回HOME]]")
        _write_text(_action_path(), "\n".join(md) + "\n")
    except Exception as e:
        logger.warning(f"今日操作清单写入失败: {e}")


def save_system_guide() -> None:
    """写入系统说明，作为新任务的“启动提示”。"""
    try:
        md = []
        md.append("---")
        md.append("tags: [SOLO, 系统说明, 使用指南]")
        md.append("---\n")
        md.append("# 系统说明（SOLO · 多宝 v2）\n")
        md.append("## 你要我在新任务里‘默认围绕股票投资’时，请先读哪几份文件？\n")
        md.append("- [[持仓清单]]：你的持仓事实表（代码/成本/止损/目标/备注）")
        md.append("- [[今日操作清单]]：今天要做什么（止损优先）")
        md.append("- [[30-日报/]]：每日日报归档")
        md.append("- [[10-交易/交易日志/]]：每日持仓审计归档\n")
        md.append("## 日常使用\n")
        md.append("- 生成日报：运行 `python .\\main.py`（或双击桌面脚本）")
        md.append("- 启动看板：运行 `python .\\main.py --dashboard`\n")
        md.append("## 数据与严谨性机制\n")
        md.append("- 实时行情：腾讯")
        md.append("- 历史K线：本地 investment.db；不足 60 天时自动用 TuShare 补齐")
        md.append("- 自检摘要：每次日报头部会显示 config/DB/腾讯/DeepSeek 是否 OK")
        md.append("- 二次审计：止损触发/大亏/信号冲突时自动调用 deepseek-reasoner 输出审计清单\n")
        md.append("> 入口：[[HOME|返回HOME]]")
        _write_text(_system_guide_path(), "\n".join(md) + "\n")
    except Exception as e:
        logger.warning(f"系统说明写入失败: {e}")


def save_daily(report_text, date_str=None):
    if not config.get("notifications", "obsidian", "enabled", default=True):
        return

    ds = date_str or datetime.now().strftime("%Y-%m-%d")
    daily_rel = config.get("notifications", "obsidian", "daily_report_path", default="30-日报")
    d = os.path.join(_root_path(), daily_rel)
    os.makedirs(d, exist_ok=True)

    p = os.path.join(d, f"盘后报告-{ds}.md")
    _write_text(
        p,
        "".join(
            [
                f"---\n",
                f"date: {ds}\n",
                f"tags: [日报, 盘后报告, 多宝v2, SOLO]\n",
                f"---\n\n",
                f"# 盘后报告 {ds}\n\n",
                f"{report_text}\n\n",
                f"---\n",
                f"> [[HOME|← 返回HOME]]\n",
            ]
        ),
    )

    update_home(last_date=ds)
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
        f"---\n",
        f"date: {ds}\n",
        f"tags: [审计, 持仓, 多宝v2, SOLO]\n",
        f"---\n\n",
        f"# 持仓审计 {ds}\n",
    ]

    for _, a in audit_data.items():
        sc = a.get("scores", {})
        lines.append(f"## {a.get('name','?')} — {a.get('action','?')} (总分 {a.get('total','?')})\n")
        lines.append(f"- 现价: {a.get('price','?')} | 成本: {a.get('cost','?')}")
        lines.append(f"- T趋势:{sc.get('T','?')} B买入:{sc.get('B','?')} F基本面:{sc.get('F','?')} R风险:{sc.get('R','?')}\n")

    lines.append("---\n> [[HOME|← 返回HOME]]\n")
    _write_text(p, "".join(lines))

    update_home(last_date=ds)
    logger.info(f"审计已存: {p}")
