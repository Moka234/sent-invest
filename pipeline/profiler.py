from __future__ import annotations

"""
pipeline/profiler.py

Phase 3：三维立体风控用户动态画像引擎
--------------------------------------------------
核心职责：
1) 从 user_sentiment 表读取全量情绪明细（SQLAlchemy 2.0 异步）
2) 在 Python 内存按 user_id 聚合，计算用户级画像指标：
   - post_count：历史言论总条数
   - avg_sentiment：情绪得分均值
   - volatility：样本标准差（count<2 则为 0.0）
3) 按风控决策树计算 risk_level
4) 使用 MySQL upsert（on_duplicate_key_update）幂等写回 risk_profile

注意：
- 本文件仅新增，不修改 scraper/cleaner/analyzer 既有逻辑
- 严格遵守 SQLAlchemy 2.0 异步规范
"""

import asyncio
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from tqdm import tqdm


# -----------------------------------------------------------------------------
# 复用后端异步数据库连接池与 ORM 模型
# -----------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.base import RiskProfile, UserSentiment  # noqa: E402


@dataclass
class UserRiskMetrics:
    """用户风控画像中间结构。"""

    user_id: str
    post_count: int
    avg_sentiment: float
    volatility: float
    risk_level: str


def compute_standard_deviation(scores: list[float], mean: float) -> float:
    """
    计算样本标准差：
      s = sqrt(Σ(x_i - mean)^2 / (n - 1))

    业务约束：当 n < 2，标准差定义为 0.0。
    """
    n = len(scores)
    if n < 2:
        return 0.0

    squared_sum = sum((x - mean) ** 2 for x in scores)
    variance = squared_sum / (n - 1)
    return math.sqrt(variance)


def decide_risk_level(post_count: int, avg_sentiment: float, std_dev: float) -> str:
    """
    三级风控判定树：

    前置条件：
      - 外层 build_user_profiles 已执行有效用户过滤，只处理 post_count >= 2 的用户

    基础画像划分（非对称阈值）：
      - avg_sentiment < 0.45 => 保守型
      - 0.45 <= avg_sentiment < 0.52 => 稳健型
      - avg_sentiment >= 0.52 => 激进型

    波动率降级机制：
      - std_dev > 0.25 时执行一级降级：
        激进型 -> 稳健型
        稳健型 -> 保守型
        保守型 -> 保守型
    """
    if avg_sentiment >= 0.52:
        provisional = "激进型"
    elif avg_sentiment >= 0.45:
        provisional = "稳健型"
    else:
        provisional = "保守型"

    if std_dev > 0.25:
        if provisional == "激进型":
            return "稳健型"
        if provisional == "稳健型":
            return "保守型"

    return provisional


async def fetch_all_user_sentiment() -> list[tuple[str, float]]:
    """读取 user_sentiment 全量明细（user_id, sentiment_score）。"""
    stmt = select(UserSentiment.user_id, UserSentiment.sentiment_score).order_by(UserSentiment.id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(stmt)
        rows = result.fetchall()

    records = [(str(row.user_id), float(row.sentiment_score)) for row in rows]
    print(f"[读取] user_sentiment 总记录数: {len(records)}")
    return records


def build_user_profiles(records: list[tuple[str, float]]) -> list[UserRiskMetrics]:
    """
    在 Python 内存中按 user_id 做 GroupBy 聚合，生成用户画像。
    """
    grouped: dict[str, list[float]] = {}
    for user_id, score in records:
        grouped.setdefault(user_id, []).append(score)

    profiles: list[UserRiskMetrics] = []
    for user_id in tqdm(grouped.keys(), desc="聚合画像", unit="user"):
        scores = grouped[user_id]
        post_count = len(scores)
        if post_count < 2:
            continue

        avg_sentiment = sum(scores) / post_count
        volatility = compute_standard_deviation(scores, avg_sentiment)
        risk_level = decide_risk_level(post_count, avg_sentiment, volatility)

        profiles.append(
            UserRiskMetrics(
                user_id=user_id,
                post_count=post_count,
                avg_sentiment=float(avg_sentiment),
                volatility=float(volatility),
                risk_level=risk_level,
            )
        )

    print(f"[聚合] 生成用户画像数: {len(profiles)}")
    return profiles


async def upsert_risk_profiles(profiles: list[UserRiskMetrics]) -> None:
    """
    使用 MySQL upsert 幂等写回 risk_profile：
    insert().on_duplicate_key_update()

    若主键 user_id 已存在，则更新：
    - avg_sentiment
    - volatility
    - post_count
    - risk_level
    - update_time
    """
    if not profiles:
        print("[写回] 无画像数据需要回写")
        return

    now = datetime.now()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            for p in tqdm(profiles, desc="写回画像", unit="user"):
                insert_stmt = mysql_insert(RiskProfile.__table__).values(
                    user_id=p.user_id,
                    avg_sentiment=p.avg_sentiment,
                    volatility=p.volatility,
                    post_count=p.post_count,
                    risk_level=p.risk_level,
                    update_time=now,
                )

                upsert_stmt = insert_stmt.on_duplicate_key_update(
                    avg_sentiment=insert_stmt.inserted.avg_sentiment,
                    volatility=insert_stmt.inserted.volatility,
                    post_count=insert_stmt.inserted.post_count,
                    risk_level=insert_stmt.inserted.risk_level,
                    update_time=insert_stmt.inserted.update_time,
                )

                await session.execute(upsert_stmt)

    print(f"[写回] risk_profile upsert 完成: {len(profiles)} 用户")


async def run_profiler() -> None:
    """Phase 3 主流程：读取 -> 聚合 -> 定级 -> 幂等回写。"""
    print("=" * 60)
    print(" SentInvest 三维立体风控画像引擎启动（Phase 3）")
    print("=" * 60)

    records = await fetch_all_user_sentiment()
    if not records:
        print("[退出] user_sentiment 暂无数据，无法生成画像")
        return

    profiles = build_user_profiles(records)
    await upsert_risk_profiles(profiles)

    print("=" * 60)
    print(" 风控画像计算完成")
    print(f" 用户画像总数: {len(profiles)}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_profiler())
