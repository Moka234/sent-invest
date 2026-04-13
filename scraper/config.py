import asyncio
import random

# 目标：东方财富「上证指数吧」
BASE_LIST_URL = "http://guba.eastmoney.com/list,zssh000001,f_{page}.html"

# 冷启动：首次基建抓取页数（约 50 页，~4000 条基础数据）
COLD_START_PAGES = 50

# 冷启动与轮询共用并发控制（防封禁）
CONCURRENCY = 5
SEMAPHORE = asyncio.Semaphore(CONCURRENCY)

# 请求超时（秒）
REQUEST_TIMEOUT = 15

# 实时轮询随机休眠区间（秒）
POLL_INTERVAL_MIN = 300
POLL_INTERVAL_MAX = 600

# 数据最大保留天数（TTL）
PRUNE_DAYS = 15

# User-Agent 池（每次请求随机选一个）
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


def random_headers() -> dict:
    """随机返回一组请求头，模拟真实浏览器行为"""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Referer": "https://guba.eastmoney.com/",
        "Cookie": "fullscreengg=1; fullscreengg2=1; qgqp_b_id=6f308dbaf5eb880240ab35fd14bb1e31; st_nvi=EdGnzO0LjaYq30wdNL2ySd868; st_si=53701324001852; websitepoptg_api_time=1774600628115; nid18=010d039dd427dc4d187090491f47d7ad; nid18_create_time=1774600628231; gviem=etVY9pwB3k0fHdVJ1bM2l226e; gviem_create_time=1774600628231; st_pvi=95887844139347; st_sp=2026-03-27%2016%3A37%3A07; st_inirUrl=https%3A%2F%2Fcn.bing.com%2F; st_sn=122; st_psi=2026032717305271-117001356556-8614872276; st_asi=2026032717305271-117001356556-8614872276-gb.ggb.qhlb-3; listtype=0",
    }
