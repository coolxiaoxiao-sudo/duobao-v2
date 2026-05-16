"""多宝 v2.0 — 一键入口

输出模式：六段式融合日报（Obsidian + 看板 + 本地文件）

用法:
  python main.py              全量分析
  python main.py --brief      快速行情
  python main.py --audit      持仓审计
  python main.py --monitor    预警检查
  python main.py --health     健康检查
  python main.py --dashboard  启动Web看板
"""

import json
import os
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from core.config import config
from core.logging import get_logger
from layer1_data.tencent_api import get_indices
from layer2_pipeline.pipeline import run as pipeline, health
from layer3_analysis.technical import score_all
from layer5_execution.audit import audit
from layer5_execution.monitor import get_all as get_monitor
from ai.deepseek import deepseek
from output.obsidian import save_daily, save_audit

logger = get_logger("main")

BANNER = """
╔══════════════════════════════════════╗
║   🔮 多宝 v2.0  股票分析系统         ║
║   六段式融合 · DeepSeek驱动 · 可视化  ║
╚══════════════════════════════════════╝"""


def _md_table(headers, rows):
    h = "|" + "|".join(headers) + "|\n"
    h += "|" + "|".join(["---"] * len(headers)) + "|\n"
    for r in rows:
        h += "|" + "|".join(str(x) for x in r) + "|\n"
    return h


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


def _build_six_section_report(date_str, pl, hlt, indices, scoring, audit_data, monitor, ai_market, ai_stocks):
    # 0) 大盘与概览
    idx_rows = []
    for name, d in (indices or {}).items():
        pct = d.get("pct_chg", 0)
        idx_rows.append([name, d.get("price"), f"{pct:+.2f}%"])

    # 评分 Top/Bottom
    sc_items = list(scoring.values())
    top5 = sc_items[:5]
    bottom5 = sc_items[-5:] if len(sc_items) >= 5 else sc_items

    # 操作清单：止损优先，其次审计 REDUCE/CLOSE
    actions = []
    for a in monitor.get("stops", [])[:10]:
        actions.append(f"- 🚨【止损触发】{a.get('name')} 现价{a.get('price')} ≤ 止损{a.get('stop')}（建议优先处理）")
    for code, a in audit_data.items():
        if a.get("action") in ("CLOSE", "REDUCE"):
            actions.append(f"- ⚠️【{a.get('action')}】{a.get('name')}：四维总分{a.get('total')}（T/B/F/R={a.get('scores')})")

    # 明日关注：评分高且非 WAIT
    focus = []
    for s in sc_items[:8]:
        if s.get("signal") != "WAIT":
            focus.append(f"- {s.get('name')}：六因子{s.get('total'):.3f} / {s.get('signal')}")

    # L4 决策支持：给出仓位节奏建议（规则版）
    l4 = []
    if monitor.get("stops"):
        l4.append("- 先处理止损：止损触发的仓位优先减/清，避免情绪化拖延。")
    if any(a.get("action") == "ADD" for a in audit_data.values()):
        l4.append("- 加仓只对‘ADD’且无止损风险的标的，分批、设置回撤止损，不追涨。")
    l4.append("- 若指数走弱且量能放大：优先防守（减少高波动/高估值仓位），等待信号回到 WATCH/BUY 再进攻。")

    report = []
    report.append(f"# 六段式融合日报 · {date_str}\n")

    report.append("## 0) 大盘概况\n")
    report.append(_md_table(["指数", "点位", "涨跌幅"], idx_rows) if idx_rows else "（指数数据缺失）\n")

    report.append("## 1) 管线健康 / 数据校验\n")
    report.append(f"- 管线状态：{pl.get('status')}，耗时：{pl.get('elapsed')}s\n")
    report.append(f"- 数据库检查：{hlt.get('checks', {}).get('database')}\n")
    fr = hlt.get('checks', {}).get('freshness', {})
    if isinstance(fr, dict):
        report.append(f"- 数据新鲜度：total={fr.get('total')} stale={fr.get('stale')} sample={fr.get('sample')}\n")

    report.append("## 2) 双脑评审（AI复盘）\n")
    if ai_market:
        report.append(ai_market.strip() + "\n")
    else:
        report.append("（未启用AI或AI调用失败）\n")

    report.append("## 3) 操作清单（先风险后机会）\n")
    report.append("\n".join(actions) + "\n" if actions else "- 今日无止损/减仓清单\n")

    report.append("## 4) 明日预测 / 机会排序（六因子）\n")
    report.append("### TOP5\n")
    report.append(_md_table(["股票", "总分", "信号"], [[x.get('name'), f"{x.get('total'):.3f}", x.get('signal')] for x in top5]))
    report.append("\n### Bottom5\n")
    report.append(_md_table(["股票", "总分", "信号"], [[x.get('name'), f"{x.get('total'):.3f}", x.get('signal')] for x in bottom5]))

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

    # 1) 管线 + 健康
    print("\n[1/5] 数据管线")
    pl = pipeline()
    hlt = health()
    print(f"  状态:{pl['status']}  耗时:{pl['elapsed']}s")

    # 2) 评分
    print("\n[2/5] 六因子均值回归评分")
    sc = score_all()
    for _, s in sc.items():
        print(f"  {s.get('name'):<8} 总分:{s.get('total',0):.3f}  信号:{s.get('signal','?')}")

    # 3) 审计
    print("\n[3/5] 持仓审计 T/B/F/R")
    au = audit()
    for _, a in au.items():
        print(f"  {a.get('name', ''):<8} 总分:{a.get('total',0):.1f}  建议:{a.get('action','HOLD')}")

    # 4) 监控
    print("\n[4/5] 预警监控")
    mn = get_monitor()
    print(f"  止损预警:{len(mn.get('stops',[]))}  止盈信号:{len(mn.get('targets',[]))}")

    # 5) AI
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

    # 六段式融合日报
    report_md = _build_six_section_report(date_str, pl, hlt, indices, sc, au, mn, ai_market, ai_stocks)

    # 输出：Obsidian + 本地文件
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
        from core.selfcheck import run as _selfcheck
        _selfcheck()
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
