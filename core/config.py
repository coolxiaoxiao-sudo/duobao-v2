"""配置加载器 — 每次读取 config.yaml（不缓存）"""
import os
from pathlib import Path
import yaml

ROOT = Path(__file__).parent.parent
CONFIG_FILE = ROOT / "config.yaml"


def _resolve(obj):
    if isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
        return os.getenv(obj[2:-1], "")
    if isinstance(obj, dict):
        return {k: _resolve(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve(i) for i in obj]
    return obj


def _load() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return _resolve(yaml.safe_load(f) or {})


def g(*keys, default=None):
    v = _load()
    for k in keys:
        if not isinstance(v, dict):
            return default
        v = v.get(k)
        if v is None:
            return default
    return v


def deepseek_key() -> str:
    # 优先环境变量（deepseek_api_key），否则使用落盘配置（deepseek_api_key_fallback）
    return g("api_keys", "deepseek_api_key", default="") or g("api_keys", "deepseek_api_key_fallback", default="")


def deepseek_model() -> str:
    return g("deepseek", "model", default="deepseek-chat")


def deepseek_reasoner_model() -> str:
    return g("deepseek", "model_reasoner", default="deepseek-reasoner")


def deepseek_base_url() -> str:
    return g("deepseek", "base_url", default="https://api.deepseek.com/v1")


def weights() -> dict:
    return g("strategy", "factor_weights", default={})


def stocks() -> list:
    return g("portfolio", "stocks", default=[])


def db_path() -> str:
    return g("system", "source_db", default="")


def log_dir() -> str:
    return g("system", "log_dir", default="logs")


def tushare_token() -> str:
    return g("api_keys", "tushare_token", default="") or g("api_keys", "tushare_token_fallback", default="")


class _ConfigProxy:
    def get(self, *keys, default=None):
        return g(*keys, default=default)

    @property
    def stocks(self):
        return stocks()

    @property
    def db_path(self):
        return db_path()

    @property
    def log_dir(self):
        return log_dir()

    @property
    def tushare_token(self):
        return tushare_token()

    @property
    def deepseek_key(self):
        return deepseek_key()

    @property
    def deepseek_model(self):
        return deepseek_model()

    @property
    def deepseek_reasoner_model(self):
        return deepseek_reasoner_model()

    @property
    def weights(self):
        return weights()


config = _ConfigProxy()