"""DeepSeek AI 引擎 — 替代原 API2D 网关（带调用日志开关）"""
import json
import os
import sys
import time
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import config
from core.logging import get_logger

logger = get_logger("deepseek")


def _truthy(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "y", "on")


def _log_path() -> str:
    # 相对路径按项目根目录计算
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = config.get("deepseek", "call_log_path", default="logs/deepseek_calls.log")
    if not p:
        p = "logs/deepseek_calls.log"
    return p if os.path.isabs(p) else os.path.join(base, p)


def _log_enabled() -> bool:
    # config.yaml deepseek.log_calls 作为默认开关
    # 也支持临时环境变量覆盖：DEEPSEEK_LOG_CALLS=1
    env = os.getenv("DEEPSEEK_LOG_CALLS")
    if env is not None and env != "":
        return _truthy(env)
    return _truthy(config.get("deepseek", "log_calls", default=False))


def _append_log(obj: dict):
    try:
        p = _log_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception as e:
        # 不影响主流程
        logger.warning(f"写入 deepseek_calls.log 失败: {e}")


class Engine:
    def __init__(self):
        self.key = config.deepseek_key
        self.base = config.get("deepseek", "base_url", default="https://api.deepseek.com/v1")
        self.model = config.get("deepseek", "model", default="deepseek-chat")
        self.reasoner = config.get("deepseek", "model_reasoner", default="deepseek-reasoner")
        self.tokens = config.get("deepseek", "max_tokens", default=4096)
        self.temp = config.get("deepseek", "temperature", default=0.3)
        self.timeout = config.get("deepseek", "timeout", default=60)

    def chat(self, msgs, model=None, temp=None):
        if not self.key:
            return "[SKIP] DeepSeek Key未配置"

        used_model = model or self.model
        url = f"{self.base}/chat/completions"
        payload = {
            "model": used_model,
            "messages": msgs,
            "max_tokens": self.tokens,
            "temperature": self.temp if temp is None else temp,
        }

        t0 = time.time()
        status = None
        ok = False
        usage = None
        err = None

        try:
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )
            status = r.status_code
            r.raise_for_status()
            j = r.json()
            usage = j.get("usage")
            ok = True
            return j["choices"][0]["message"]["content"]
        except Exception as e:
            err = str(e)
            logger.error(f"DeepSeek API失败: {e}")
            return f"[ERROR] {e}"
        finally:
            if _log_enabled():
                elapsed_ms = int((time.time() - t0) * 1000)
                _append_log(
                    {
                        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "ok": ok,
                        "status": status,
                        "elapsed_ms": elapsed_ms,
                        "model": used_model,
                        "endpoint": "/chat/completions",
                        # 为隐私与体积考虑：只记录长度，不记录原文
                        "prompt_chars": sum(len(m.get("content", "")) for m in (msgs or []) if isinstance(m, dict)),
                        "usage": usage,
                        "error": err,
                    }
                )

    def analyze_stock(self, name, code, ctx):
        return self.chat(
            [
                {
                    "role": "system",
                    "content": "你是专业A股量化分析师。数据驱动，给出明确多空判断+置信度+风险提示。",
                },
                {
                    "role": "user",
                    "content": f"""## {name}({code})
### 行情: {json.dumps(ctx.get('quote',{}), ensure_ascii=False)}
### 六因子: {json.dumps(ctx.get('factors',{}), ensure_ascii=False)}
### 成本: {ctx.get('cost')} 止盈: {ctx.get('target')} 止损: {ctx.get('stop')}
请给出: 1.多空判断 2.置信度(0-1) 3.关键风险 4.操作建议""",
                },
            ]
        )

    def market_review(self, ctx):
        return self.chat(
            [
                {"role": "system", "content": "专业A股市场分析师。"},
                {
                    "role": "user",
                    "content": f"""请复盘今日A股:
### 大盘: {json.dumps(ctx.get('indices',{}), ensure_ascii=False)}
### 持仓评分: {json.dumps(ctx.get('scores',{}), ensure_ascii=False)}
请给出: 1.市场总结 2.板块方向 3.风险提示 4.明日关注""",
                },
            ]
        )

    def reason(self, question, ctx=None):
        content = question
        if ctx:
            content = f"{question}\n\n### 数据\n{json.dumps(ctx, ensure_ascii=False)}"
        return self.chat([{"role": "user", "content": content}], model=self.reasoner, temp=0.1)


deepseek = Engine()