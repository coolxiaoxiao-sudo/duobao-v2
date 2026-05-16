from .config import g as config_get, deepseek_key, deepseek_model, weights, stocks, db_path, tushare_token

class _ConfigProxy:
    def get(self, *keys, default=None): return config_get(*keys, default=default)
    @property
    def stocks(self): return stocks()
    @property
    def db_path(self): return db_path()
    @property
    def tushare_token(self): return tushare_token()
    @property
    def deepseek_key(self): return deepseek_key()
    @property
    def deepseek_model(self): return deepseek_model()
    @property
    def weights(self): return weights()

config = _ConfigProxy()
