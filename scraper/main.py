import argparse
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import random
import re
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import aiohttp
from bs4 import BeautifulSoup
from sqlalchemy import delete
from sqlalchemy.dialects.mysql import insert as mysql_insert

from config import (
    BASE_LIST_URL,
    COLD_START_PAGES,
    POLL_INTERVAL_MAX,
    POLL_INTERVAL_MIN,
    PRUNE_DAYS,
    REQUEST_TIMEOUT,
    SEMAPHORE,
    random_headers,
)

# -----------------------------
# 复用 backend 的连接池与 ORM 模型
# -----------------------------
ROOT_DIR = Path(__file__).resolve().parents[1]  # sent-invest/
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.base import RawData  # noqa: E402

# -----------------------------
# 生产级运行参数
# -----------------------------
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_BASE = 2
BATCH_SIZE = 3
METRIC_LOG_EVERY = 20


def parse_args() -> argparse.Namespace:
    """命令行参数：支持一次性运行与轮询模式切换。"""
    parser = argparse.ArgumentParser(description="Eastmoney Guba scraper runner")
    parser.add_argument(
        "--once",
        action="store_true",
        help="仅执行冷启动抓取后退出（不进入实时轮询）",
    )
    parser.add_argument(
        "--poll-only",
        action="store_true",
        help="跳过冷启动，直接进入实时轮询",
    )
    parser.add_argument(
        "--metric-every",
        type=int,
        default=METRIC_LOG_EVERY,
        help="每 N 轮输出一次指标日志（默认 20）",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="冷启动起始页（默认 1，用于历史回溯 Backfill）",
    )
    parser.add_argument(
        "--end-page",
        type=int,
        default=COLD_START_PAGES,
        help="冷启动结束页（默认 config.COLD_START_PAGES）",
    )
    return parser.parse_args()

LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "scraper.log"

console_handler = logging.StreamHandler()
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=5 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[console_handler, file_handler],
)
logger = logging.getLogger("scraper")

STATS = {
    "ok_pages": 0,
    "failed_pages": 0,
    "retry_count": 0,
    "http_403": 0,
    "http_5xx": 0,
    "upsert_rows": 0,
}


def parse_post_time(time_text: str) -> datetime:
    """
    解析股吧页面中的时间字符串。
    支持格式：
      - 2026-03-20 14:30
      - 03-20 14:30（缺年时补当前年）
    """
    time_text = (time_text or "").strip()
    now = datetime.now()

    for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(time_text, fmt)
        except ValueError:
            pass

    for fmt in ("%m-%d %H:%M", "%m/%d %H:%M"):
        try:
            return datetime.strptime(time_text, fmt).replace(year=now.year)
        except ValueError:
            pass

    return now


def _extract_balanced_object(text: str, anchor_index: int) -> str:
    start = text.rfind("{", 0, anchor_index + 1)
    if start == -1:
        return ""

    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(text)):
        char = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]

    return ""


def extract_post_publish_time_from_scripts(soup: BeautifulSoup, source_post_id: str) -> str:
    """
    以 <script> 中的 JSON 数据为准提取发帖时间。
    同一条帖子在 DOM 和 script 中可能各有一份时间，script 里的 post_publish_time 更准确。
    """
    if not source_post_id:
        return ""

    escaped_id = re.escape(source_post_id)
    id_patterns = [
        rf'"post_id"\s*:\s*{escaped_id}',
        rf'"post_id"\s*:\s*"{escaped_id}"',
        rf'"source_post_id"\s*:\s*"{escaped_id}"',
    ]

    for script in soup.find_all("script"):
        script_text = script.string or script.get_text() or ""
        if not script_text or source_post_id not in script_text or "post_publish_time" not in script_text:
            continue

        for id_pattern in id_patterns:
            id_match = re.search(id_pattern, script_text)
            if not id_match:
                continue

            object_text = _extract_balanced_object(script_text, id_match.start())
            if not object_text:
                continue

            time_match = re.search(r'"post_publish_time"\s*:\s*"([^"]+)"', object_text)
            if time_match:
                return time_match.group(1).strip()

    return ""


def parse_posts(html: str) -> list[dict[str, Any]]:
    """
    解析东方财富股吧列表页。
    帖子链接格式：<a data-postid="xxx" href="/news,zssh000001,xxx.html">
    直接从 data-postid 属性读取帖子 ID，避免与股票代码混淆。
    """
    soup = BeautifulSoup(html, "html.parser")
    posts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    # 优先用 data-postid（新版东方财富股吧结构）
    post_links = soup.select("a[data-postid]")

    # 兼容旧版 articleh 结构
    if not post_links:
        for row in soup.select("div.articleh"):
            a = row.select_one("a[href*='/news,']")
            if a:
                post_links.append(a)

    for a_tag in post_links:
        # 从 data-postid 读取，避免提取到股票代码
        source_post_id = a_tag.get("data-postid", "").strip()
        if not source_post_id:
            # 兜底：从 href 末段提取，/news,zssh000001,1685981016.html -> 1685981016
            href = a_tag.get("href", "")
            parts = re.split(r"[,/]", href.rstrip(".html"))
            # 取最后一段纯数字且长度>8的部分（帖子ID比股票代码长）
            for part in reversed(parts):
                if re.fullmatch(r"\d{8,}", part):
                    source_post_id = part
                    break
        if not source_post_id or source_post_id in seen_ids:
            continue
        seen_ids.add(source_post_id)

        title = a_tag.get_text(strip=True)
        if not title:
            continue

        # 向上找行容器，提取作者和时间
        container = a_tag.parent
        for _ in range(5):
            if container is None:
                break
            if container.select_one(".l4, .author, .uname, .l5, .update, [class*=time]"):
                break
            container = container.parent

        user_id = "unknown"
        time_extract_source = "script_json"
        post_time_text = extract_post_publish_time_from_scripts(soup, source_post_id)
        html_hit = bool(post_time_text)
        if container:
            author_tag = container.select_one(".l4, .author, .uname")
            if author_tag:
                user_id = author_tag.get_text(strip=True) or "unknown"
            if not post_time_text:
                time_tag = container.select_one(".l5, .update, [class*=time]")
                if time_tag:
                    post_time_text = time_tag.get_text(strip=True)
                    time_extract_source = "dom_time_tag"

        # 兜底：只有 HTML 级精准提取失败、且 DOM 节点也拿不到时，才退回到全文本正则
        if not post_time_text:
            text = container.get_text(" ", strip=True) if container else ""
            m = re.search(
                r"(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}(?::\d{2})?|\d{2}[-/]\d{2}\s+\d{2}:\d{2})",
                text,
            )
            if m:
                post_time_text = m.group(1)
                time_extract_source = "container_text_regex"

        if time_extract_source == "container_text_regex" or not post_time_text:
            logger.info(
                "[TIME-EXTRACT] post_id=%s source=%s resolved_time=%r script_hit=%s dom_container=%s title=%r",
                source_post_id,
                time_extract_source if post_time_text else "not_found",
                post_time_text,
                html_hit,
                bool(container),
                title[:80],
            )

        # 严格校验：只接受 8~11 位纯数字的帖子 ID（排除新闻资讯长 ID 和股票代码短 ID）
        if not re.fullmatch(r"^\d{8,11}$", source_post_id):
            continue

        posts.append(
            {
                "source_post_id": source_post_id,
                "user_id": user_id,
                "content": title,
                "post_time": parse_post_time(post_time_text),
            }
        )

    return posts


async def fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    """受 Semaphore 限流的单页请求"""
    async with SEMAPHORE:
        # 强制 HTTPS，避免 HTTP 被 302 重定向再触发反爬
        url = url.replace("http://", "https://")
        async with session.get(
            url,
            headers=random_headers(),
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            allow_redirects=True,
        ) as resp:
            resp.raise_for_status()
            return await resp.text(encoding="utf-8", errors="ignore")


async def save_posts_to_db(posts: list[dict[str, Any]]) -> int:
    """
    保留幂等写入机制：
    - on_duplicate_key_update
    - 冲突时刷新 post_time，修正历史误解析时间
    - 同时刷新 update_time
    """
    if not posts:
        return 0

    now = datetime.now()
    values = [
        {
            "source_platform": "eastmoney_guba",
            "source_post_id": item["source_post_id"],
            "user_id": item["user_id"],
            "topic": "股吧",
            "content": item["content"],
            "clean_content": None,
            "sentiment_score": None,
            "sentiment_label": None,
            "post_time": item["post_time"],
            "create_time": now,
            "update_time": now,
            "process_status": 0,
        }
        for item in posts
    ]

    stmt = mysql_insert(RawData).values(values)
    stmt = stmt.on_duplicate_key_update(
        post_time=stmt.inserted.post_time,
        update_time=stmt.inserted.update_time,
    )

    async with AsyncSessionLocal() as db:
        await db.execute(stmt)
        await db.commit()

    return len(values)


async def prune_old_data() -> int:
    """删除 create_time 早于 (当前时间 - PRUNE_DAYS) 的历史数据。"""
    cutoff = datetime.now() - timedelta(days=PRUNE_DAYS)
    stmt = delete(RawData).where(RawData.create_time < cutoff)

    async with AsyncSessionLocal() as db:
        result = await db.execute(stmt)
        await db.commit()

    deleted = int(result.rowcount or 0)
    logger.info("[PRUNE] cutoff=%s deleted=%s", cutoff.strftime("%Y-%m-%d %H:%M:%S"), deleted)
    return deleted


def log_metrics(prefix: str = "[METRIC]") -> None:
    logger.info(
        "%s ok_pages=%s failed_pages=%s retries=%s http_403=%s http_5xx=%s upsert_rows=%s",
        prefix,
        STATS["ok_pages"],
        STATS["failed_pages"],
        STATS["retry_count"],
        STATS["http_403"],
        STATS["http_5xx"],
        STATS["upsert_rows"],
    )


async def crawl_one_page(http_session: aiohttp.ClientSession, page: int) -> int:
    """抓取单页并写库，返回本页尝试入库条数（含重试与耗时统计）。"""
    url = BASE_LIST_URL.format(page=page)

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        started = time.perf_counter()
        try:
            html = await fetch_html(http_session, url)
            posts = parse_posts(html)
            count = await save_posts_to_db(posts)
            elapsed = time.perf_counter() - started

            STATS["ok_pages"] += 1
            STATS["upsert_rows"] += count

            logger.info(
                "[OK] page=%s parsed=%s upsert=%s elapsed=%.2fs attempt=%s",
                page,
                len(posts),
                count,
                elapsed,
                attempt,
            )
            return count

        except aiohttp.ClientResponseError as e:
            elapsed = time.perf_counter() - started
            if e.status == 403:
                STATS["http_403"] += 1
            if 500 <= e.status < 600:
                STATS["http_5xx"] += 1

            if attempt < RETRY_ATTEMPTS:
                STATS["retry_count"] += 1
                backoff = RETRY_BACKOFF_BASE ** (attempt - 1)
                logger.warning(
                    "[RETRY] page=%s attempt=%s/%s status=%s elapsed=%.2fs backoff=%ss",
                    page,
                    attempt,
                    RETRY_ATTEMPTS,
                    e.status,
                    elapsed,
                    backoff,
                )
                await asyncio.sleep(backoff)
                continue

            STATS["failed_pages"] += 1
            logger.error(
                "[ERR] page=%s attempt=%s/%s status=%s elapsed=%.2fs",
                page,
                attempt,
                RETRY_ATTEMPTS,
                e.status,
                elapsed,
            )

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            elapsed = time.perf_counter() - started
            if attempt < RETRY_ATTEMPTS:
                STATS["retry_count"] += 1
                backoff = RETRY_BACKOFF_BASE ** (attempt - 1)
                logger.warning(
                    "[RETRY] page=%s attempt=%s/%s elapsed=%.2fs err=%s backoff=%ss",
                    page,
                    attempt,
                    RETRY_ATTEMPTS,
                    elapsed,
                    e,
                    backoff,
                )
                await asyncio.sleep(backoff)
                continue

            STATS["failed_pages"] += 1
            logger.error(
                "[ERR] page=%s attempt=%s/%s network_fail err=%s",
                page,
                attempt,
                RETRY_ATTEMPTS,
                e,
            )

        except Exception as e:
            elapsed = time.perf_counter() - started
            STATS["failed_pages"] += 1
            logger.error(
                "[ERR] page=%s attempt=%s/%s unknown_fail elapsed=%.2fs err=%s",
                page,
                attempt,
                RETRY_ATTEMPTS,
                elapsed,
                e,
            )
            break

    return 0


async def cold_start(
    http_session: aiohttp.ClientSession,
    stop_event: asyncio.Event,
    start_page: int = 1,
    end_page: int = COLD_START_PAGES,
) -> None:
    """
    第一阶段：冷启动基建（防封禁）
    - 抓取 start_page..end_page
    - 每批 3 页并发
    - 批间随机休眠 5~15s
    """
    pages = list(range(start_page, end_page + 1))
    total = 0

    logger.info("[BOOT] start pages=%s..%s batch_size=%s", start_page, end_page, BATCH_SIZE)

    for i in range(0, len(pages), BATCH_SIZE):
        if stop_event.is_set():
            logger.info("[BOOT] stop signal received, cold start interrupted")
            break

        batch = pages[i : i + BATCH_SIZE]
        logger.info("[BOOT] batch=%s pages=%s", i // BATCH_SIZE + 1, batch)

        results = await asyncio.gather(*(crawl_one_page(http_session, p) for p in batch))
        total += sum(results)

        if i + BATCH_SIZE < len(pages):
            pause = random.uniform(5, 15)
            logger.info("[BOOT] batch done, sleep %.1fs", pause)
            await asyncio.sleep(pause)

    logger.info("[BOOT] done upsert_total=%s", total)


async def realtime_poll(
    http_session: aiohttp.ClientSession,
    stop_event: asyncio.Event,
    metric_every: int,
) -> None:
    """
    第二阶段：实时盯盘
    - while True 每轮只抓第 1 页
    - 每轮随机休眠 POLL_INTERVAL_MIN ~ POLL_INTERVAL_MAX
    - 每 50 轮执行一次 prune_old_data
    - 顶层异常隔离，5 分钟后重试，主进程永不崩溃
    """
    loop_count = 0
    logger.info("[POLL] realtime mode started")

    while not stop_event.is_set():
        try:
            loop_count += 1
            round_started = time.perf_counter()

            await crawl_one_page(http_session, 1)

            if loop_count % 50 == 0:
                await prune_old_data()

            if loop_count % metric_every == 0:
                log_metrics("[METRIC][POLL]")

            round_elapsed = time.perf_counter() - round_started
            sleep_s = random.uniform(POLL_INTERVAL_MIN, POLL_INTERVAL_MAX)
            logger.info(
                "[POLL] loop=%s round_elapsed=%.2fs sleep=%.1fs",
                loop_count,
                round_elapsed,
                sleep_s,
            )
            await asyncio.sleep(sleep_s)

        except Exception as e:
            logger.error("[FATAL-GUARD] poll loop error=%s, sleep 300s then retry", e)
            await asyncio.sleep(300)

    logger.info("[POLL] stop signal received, realtime polling exited")


def install_signal_handlers(stop_event: asyncio.Event) -> None:
    """注册优雅停机信号（Ctrl+C / SIGTERM）。"""

    def _request_shutdown() -> None:
        if not stop_event.is_set():
            logger.warning("[SHUTDOWN] signal received, finishing current cycle then exit")
            stop_event.set()

    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            signal.signal(sig, lambda *_: _request_shutdown())


async def main() -> None:
    """主入口：冷启动 -> 实时盯盘。"""
    args = parse_args()

    if args.once and args.poll_only:
        raise ValueError("--once 与 --poll-only 不能同时使用")

    metric_every = max(1, args.metric_every)

    stop_event = asyncio.Event()
    install_signal_handlers(stop_event)

    connector = aiohttp.TCPConnector(limit=20, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as http_session:
        if not args.poll_only:
            await cold_start(http_session, stop_event, args.start_page, args.end_page)

        if not stop_event.is_set() and not args.once:
            await realtime_poll(http_session, stop_event, metric_every)

    log_metrics("[METRIC][EXIT]")


if __name__ == "__main__":
    asyncio.run(main())
