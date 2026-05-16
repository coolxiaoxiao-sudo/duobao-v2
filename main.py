"""多宝 v2.0 — 一键入口

默认：六段式融合日报（含自检摘要 + 自动二次审计）

用法:
  python main.py              全量分析
  python main.py --brief      快速行情
  python main.py --audit      持仓审计
  python main.py --monitor    预警检查
  python main.py --health     健康检查
  python main.py --selfcheck  自检报告
  python main.py --dashboard  启动Web看板
"""

import json
import os
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from ai.deepseek import deepseek
from core.config import config
from core.selfcheck import run as selfcheck_run
from core.logging import get_logger
from layer1_data.tencent_api import get_indices
from layer2_pipeline.pipeline import run as pipeline, health
from layer3_analysis.technical import score_all
from layer5_execution.audit import audit
from layer5_execution.monitor import get_all as get_monitor
from output.obsidian import save_daily, save_audit

logger = get_logger("main")

BANNER = """
╔══════════════════════════════════════╗
║   🔮 多宝 v2.0  股票分析系统         ║
║   六段式融合 · 自动审计 · 可视化     ║
╚══════════════════════════════════════╝"""


def _md_table(headers, rows):
    h = "|" + "|".join(headers) + "|\n"
    h += "|" + "|".join(["---"] * len(headers)) + "|\n"
    for r in rows:
        h += "|" + "|".join(str(x) for x in r) + "|\n"
    return h


def _selfcheck_md() -> str:
    res = selfcheck_run(quiet=True)
    checks = res.get("checks", {})

    def line(k):
        v = checks.get(k, {})
        return ("✅" if v.get("ok") else "❌") + f" {k}: {v.get('msg')}"

    lines = [
        f"- 总体: {'OK' if res.get('ok') else 'FAIL'}",
        line("config"),
        line("db"),
        line("tencent"),
        line("deepseek"),
    ]
    return "## 自检状态\n" + "\n".join(lines) + "\n"


def _pick_reasoner_targets(sc: dict, au: dict, mn: dict, max_n: int = 5):
    """自动挑选需要二次审计的股票（神经反射）：
    1) 止损触发（CRITICAL）
    2) 大亏（pct_cost <= -20）
    3) 信号冲突（评分WAIT但审计ADD）
    """
    targets = []

    stop_codes = [x.get("code") for x in (mn.get("stops") or []) if x.get("code")]
    for c in stop_codes:
        if c not in targets:
            targets.append(c)

    for c, a in (au or {}).items():
        try:
            if float(a.get("pct_cost", 0)) <= -20 and c not in targets:
                targets.append(c)
        except Exception:
            pass

    for c, s in (sc or {}).items():
        if s.get("signal") == "WAIT" and (au.get(c, {}).get("action") == "ADD") and c not in targets:
            targets.append(c)

    return targets[:max_n]


def _reasoner_audit_md(sc: dict, au: dict, mn: dict) -> str:
    targets = _pick_reasoner_targets(sc, au, mn)
    if not targets:
        return ""

    if not config.deepseek_key:
        return "## 二次审计（Reasoner）\n- [SKIP] DeepSeek Key未配置\n"

    blocks = ["## 二次审计（Reasoner）\n> 触发条件：止损触发 / 大亏 / 信号冲突\n"]

    for code in targets:
        s = sc.get(code, {})
        a = au.get(code, {})
        stop = None
        for x in (mn.get("stops") or []):
            if x.get("code") == code:
                stop = x
                break

        ctx = {
            "code": code,
            "name": s.get("name") or a.get("name"),
            "quote": s.get("technicals") or {},
            "factors": s.get("factors") or {},
            "score": {"total": s.get("total"), "signal": s.get("signal")},
            "audit": {
                "action": a.get("action"),
                "total": a.get("total"),
                "scores": a.get("scores"),
                "pct_cost": a.get("pct_cost"),
                "cost": a.get("cost"),
                "stop": a.get("stop"),
                "target": a.get("target"),
            },
            "monitor_stop": stop,
        }

        q = (
            "你是风控审计官（强制严格）。仅基于给定数据输出：\n"
            "1) 是否建议立即止损/减仓/观望（必须三选一）；\n"
            "2) 给出 3 条反证/风险点；\n"
            "3) 给出关键失效位/确认位（价格区间或条件）；\n"
            "4) 给出置信度 0-1。\n"
            "用要点列表输出，避免长篇叙事。"
        )

        ans = deepseek.reason(q, ctx)
        blocks.append(f"### {ctx.get('name','?')}（{code}）\n{ans.strip()}\n")

    return "\n".join(blocks) + "\n"


def _write_local_report(text: str, date_str: str):
    out_dir = os.path.join(BASE, "data")
    os.makedirs(out_dir, exist_ok=True)
    latest = os.path.join(out_dir, "latest_report.md")
    dated = os.path.join(out_dir, f"report_{date_str}.md")
    with open(latest, "w", encoding="utf-8") as f:
        f.write(text)
    with open(dated, "w", encoding="utf-8") as f:
        f.write(text)
    return latest, dated


def _build_report(date_str, pl, hlt, indices, scoring, audit_data, monitor, ai_market, ai_stocks, selfcheck_block, reasoner_block):
    idx_rows = []
    for name, d in (indices or {}).items():
        pct = d.get("pct_chg", 0)
        idx_rows.append([name, d.get("price"), f"{pct:+.2f}%"])

    sc_items = list(scoring.values())
    top5 = sc_items[:5]
    bottom5 = sc_items[-5:] if len(sc_items) >= 5 else sc_items

    actions = []
    for a in monitor.get("stops", [])[:10]:
        actions.append(f"- 🚨【止损触发】{a.get('name')} 现价{a.get('price')} ≤ 止损{a.get('stop')}（建议优先处理）")
    for _, a in audit_data.items():
        if a.get("action") in ("CLOSE", "REDUCE"):
            actions.append(f"- ⚠️【{a.get('action')}】{a.get('name')}：四维总分{a.get('total')}（T/B/F/R={a.get('scores')})")

    l4 = []
    if monitor.get("stops"):
        l4.append("- 先处理止损：止损触发的仓位优先减/清，避免情绪化拖延。")
    if any(a.get("action") == "ADD" for a in audit_data.values()):
        l4.append("- 加仓只对‘ADD’且无止损风险的标的，分批、设置回撤止损，不追涨。")
    l4.append("- 若指数走弱且量能放大：优先防守（减少高波动/高估值仓位），等待信号回到 WATCH/BUY 再进攻。")

    report = []
    report.append(f"# 六段式融合日报 · {date_str}\n")
    report.append(selfcheck_block)

    report.append("## 0) 大盘概况\n")
    report.append(_md_table(["指数", "点位", "涨跌幅"], idx_rows) if idx_rows else "（指数数据缺失）\n")

    report.append("## 1) 管线健康 / 数据校验\n")
    report.append(f"- 管线状态：{pl.get('status')}，耗时：{pl.get('elapsed')}s\n")
    report.append(f"- 数据库检查：{hlt.get('checks', {}).get('database')}\n")
    fr = hlt.get("checks", {}).get("freshness", {})
    if isinstance(fr, dict):
        report.append(f"- 数据新鲜度：total={fr.get('total')} stale={fr.get('stale')} sample={fr.get('sample')}\n")

    report.append("## 2) 双脑评审（AI复盘）\n")
    report.append((ai_market.strip() + "\n") if ai_market else "（未启用AI或AI调用失败）\n")

    if reasoner_block:
        report.append(reasoner_block)

    report.append("## 3) 操作清单（先风险后机会）\n")
    report.append("\n".join(actions) + "\n" if actions else "- 今日无止损/减仓清单\n")

    report.append("## 4) 明日预测 / 机会排序（六因子）\n")
    report.append("### TOP5\n")
    report.append(_md_table(["股票", "总分", "信号"], [[x.get("name"), f"{x.get('total',0):.3f}", x.get("signal")] for x in top5]))
    report.append("\n### Bottom5\n")
    report.append(_md_table(["股票", "总分", "信号"], [[x.get("name"), f"{x.get('total',0):.3f}", x.get("signal")] for x in bottom5]))

    report.append("## 5) L4 决策支持（仓位节奏 / 风险提示）\n")
    report.append("\n".join(l4) + "\n")

    if ai_stocks:
        report.append("\n---\n\n## 附：AI 个股分析（TOP3）\n")
        for name, txt in ai_stocks:
            report.append(f"### {name}\n{txt.strip()}\n")

    return "\n".join(report)


def full():
    print(BANNER)
    print("═" * 50)
    t0 = datetime.now()
    date_str = t0.strftime("%Y-%m-%d")

    print("\n[1/5] 数据管线")
    pl = pipeline()
    hlt = health()
    print(f"  状态:{pl['status']}  耗时:{pl['elapsed']}s")

    print("\n[2/5] 六因子均值回归评分")
    sc = score_all()
    for _, s in sc.items():
        print(f"  {s.get('name'):<8} 总分:{s.get('total',0):.3f}  信号:{s.get('signal','?')}")

    print("\n[3/5] 持仓审计 T/B/F/R")
    au = audit()
    for _, a in au.items():
        print(f"  {a.get('name',''):<8} 总分:{a.get('total',0):.1f}  建议:{a.get('action','HOLD')}")

    print("\n[4/5] 预警监控")
    mn = get_monitor()
    print(f"  止损预警:{len(mn.get('stops',[]))}  止盈信号:{len(mn.get('targets',[]))}")

    print("\n[5/5] DeepSeek AI 分析")
    indices = get_indices()

    ai_market = ""
    ai_stocks = []
    if config.deepseek_key:
        ctx = {"indices": indices, "scores": {}}
        for c, s in sc.items():
            ctx["scores"][c] = {"name": s.get("name"), "total": s.get("total"), "signal": s.get("signal")}
        ai_market = deepseek.market_review(ctx)

        top = [s for s in sc.values() if s.get("signal") in ("BUY", "WATCH")][:3]
        for s in top:
            txt = deepseek.analyze_stock(
                s.get("name", ""),
                s.get("code", ""),
                {
                    "quote": s.get("technicals", {}),
                    "factors": s.get("factors", {}),
                    "cost": s.get("cost"),
                    "target": s.get("target"),
                    "stop": s.get("stop"),
                },
            )
            ai_stocks.append((s.get("name"), txt))

        print(f"  {ai_market[:200]}...")
    else:
        print("  [SKIP] Key未配置")

    # 自动二次审计（Reasoner）：仅在触发条件下执行
    reasoner_md = _reasoner_audit_md(sc, au, mn)

    report_md = _build_report(
        date_str,
        pl,
        hlt,
        indices,
        sc,
        au,
        mn,
        ai_market,
        ai_stocks,
        _selfcheck_md(),
        reasoner_md,
    )

    save_daily(report_md, date_str=date_str)
    if au:
        save_audit(au, date_str=date_str)
    latest, dated = _write_local_report(report_md, date_str)

    elapsed = (datetime.now() - t0).total_seconds()
    print("\n" + "═" * 50)
    print(f"  分析完成 · 耗时 {elapsed:.0f}s")
    print(f"  本地日报: {dated}")
    print("═" * 50)


def main():
    if "--selfcheck" in sys.argv:
        selfcheck_run(quiet=False)
        return
    if "--dashboard" in sys.argv:
        from dashboard.app import run as run_dash
        return run_dash()

    if "--brief" in sys.argv:
        print(json.dumps(pipeline(True), ensure_ascii=False, indent=2))
    elif "--audit" in sys.argv:
        print(json.dumps(audit(), ensure_ascii=False, indent=2))
    elif "--monitor" in sys.argv:
        print(json.dumps(get_monitor(), ensure_ascii=False, indent=2))
    elif "--health" in sys.argv:
        print(json.dumps(health(), ensure_ascii=False, indent=2))
    else:
        full()


if __name__ == "__main__":
    main()
