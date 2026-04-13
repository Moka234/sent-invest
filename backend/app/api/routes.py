from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models.base import Product, RawData, RiskProfile, UserSentiment
from app.schemas.api_models import (
    ApiResponse,
    DashboardData,
    RecommendationData,
    RecommendationProduct,
    RiskLevelCountItem,
    SentimentTrend24HData,
    TrendData,
    TrendHistoryPoint,
    TrendPoint,
    UserProfileInfo,
)


router = APIRouter(prefix="/api", tags=["sent-invest"])


def build_recommend_reason(
    *,
    product: Product,
    user_avg_sentiment: float,
    user_volatility: float,
    score: float,
) -> str:
    """
    基于产品风险收益特征 + 用户当前情绪波动状态，生成可解释性推荐文案。

    设计原则：
    1) 高波动用户：强调低回撤、较高夏普比率，突出“抗波动能力”
    2) 低波动用户：强调收益弹性与风险收益比，突出“进攻效率”
    3) 文案中直接引用关键金融指标，便于前端展示时具备解释依据
    """
    if user_volatility >= 0.20:
        return (
            f"该产品夏普比率为 {float(product.sharpe_ratio):.2f}，且最大回撤仅为 "
            f"{float(product.max_drawdown):.2f}%，在您近期情绪波动较高的情况下，"
            f"更有助于兼顾稳健性与收益质量。综合匹配得分为 {score:.2f}。"
        )

    if user_avg_sentiment >= 0.60 and float(product.annual_yield) >= 12:
        return (
            f"该产品年化收益达到 {float(product.annual_yield):.2f}%，同时夏普比率为 "
            f"{float(product.sharpe_ratio):.2f}，说明其在高收益之外仍具备一定风险收益效率，"
            f"适合当前情绪相对稳定、可承受更高弹性的配置需求。综合匹配得分为 {score:.2f}。"
        )

    return (
        f"该产品年化收益为 {float(product.annual_yield):.2f}%，最大回撤为 "
        f"{float(product.max_drawdown):.2f}%，夏普比率为 {float(product.sharpe_ratio):.2f}，"
        f"在收益、回撤与风险收益比之间较为均衡，适合作为当前风险偏好的优先配置标的。"
        f"综合匹配得分为 {score:.2f}。"
    )


@router.get("/market/dashboard", response_model=ApiResponse[DashboardData])
async def get_market_dashboard(
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[DashboardData]:
    """
    大盘看板接口：
    - 计算 risk_profile 全局平均情绪
    - 统计各 risk_level 人数分布
    """
    try:
        avg_stmt = select(func.avg(RiskProfile.avg_sentiment))
        avg_result = await db.execute(avg_stmt)
        global_avg = avg_result.scalar_one_or_none()

        dist_stmt = (
            select(RiskProfile.risk_level, func.count(RiskProfile.user_id))
            .group_by(RiskProfile.risk_level)
            .order_by(RiskProfile.risk_level)
        )
        dist_result = await db.execute(dist_stmt)
        dist_rows = dist_result.fetchall()

        distribution = [
            RiskLevelCountItem(risk_level=str(risk_level), user_count=int(user_count))
            for risk_level, user_count in dist_rows
        ]

        data = DashboardData(
            global_avg_sentiment=float(global_avg) if global_avg is not None else 0.0,
            risk_level_distribution=distribution,
        )
        return ApiResponse(code=200, data=data, msg="ok")

    except SQLAlchemyError as e:
        return ApiResponse(code=400, data=None, msg=f"数据库查询失败: {e}")


@router.get("/sentiment/trend/24h", response_model=ApiResponse[SentimentTrend24HData])
async def get_market_sentiment_trend_24h(
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SentimentTrend24HData]:
    """
    全站过去 24 小时情绪走势：
    1) 以当前时间为终点，回溯过去 24 个整点小时
    2) 以数据库无关写法读取原始记录后，在 Python 内按小时聚合 avg(sentiment_score)
    3) 对缺失小时做线性插值，避免出现长段不自然的水平直线
    4) 对头尾缺失段使用全局均值作为锚点做平滑过渡，确保整段曲线连续自然
    """
    try:
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        start_time = now - timedelta(hours=23)
        end_time = now + timedelta(hours=1)

        global_avg_stmt = select(func.avg(RawData.sentiment_score)).where(RawData.sentiment_score.is_not(None))
        global_avg_result = await db.execute(global_avg_stmt)
        global_avg = round(float(global_avg_result.scalar_one_or_none() or 0.5), 4)

        raw_stmt = (
            select(RawData.post_time, RawData.sentiment_score)
            .where(
                RawData.post_time >= start_time,
                RawData.post_time < end_time,
                RawData.sentiment_score.is_not(None),
            )
            .order_by(RawData.post_time.asc())
        )
        raw_result = await db.execute(raw_stmt)
        raw_rows = raw_result.fetchall()

        bucket_values: dict[datetime, list[float]] = {}
        for row in raw_rows:
            hour_key = row.post_time.replace(minute=0, second=0, microsecond=0)
            bucket_values.setdefault(hour_key, []).append(float(row.sentiment_score))

        aggregated_by_hour = {
            hour: round(sum(values) / len(values), 4)
            for hour, values in bucket_values.items()
        }

        timeline = [start_time + timedelta(hours=i) for i in range(24)]
        labels = [dt.strftime("%H:00") for dt in timeline]
        interpolated: list[float | None] = [aggregated_by_hour.get(dt) for dt in timeline]
        point_types: list[str] = ["real" if aggregated_by_hour.get(dt) is not None else "missing" for dt in timeline]

        known_indices = [idx for idx, value in enumerate(interpolated) if value is not None]

        if not known_indices:
            filled_scores = [global_avg for _ in timeline]
            point_types = ["anchor" for _ in timeline]
        else:
            first_idx = known_indices[0]
            last_idx = known_indices[-1]

            if first_idx > 0:
                first_value = float(interpolated[first_idx])
                step = (first_value - global_avg) / (first_idx + 1)
                for idx in range(first_idx):
                    interpolated[idx] = round(global_avg + step * (idx + 1), 4)
                    point_types[idx] = "anchor"

            for left_idx, right_idx in zip(known_indices, known_indices[1:]):
                left_value = float(interpolated[left_idx])
                right_value = float(interpolated[right_idx])
                gap = right_idx - left_idx
                if gap > 1:
                    step = (right_value - left_value) / gap
                    for idx in range(left_idx + 1, right_idx):
                        interpolated[idx] = round(left_value + step * (idx - left_idx), 4)
                        point_types[idx] = "interpolated"

            if last_idx < len(interpolated) - 1:
                last_value = float(interpolated[last_idx])
                tail_span = len(interpolated) - last_idx
                step = (global_avg - last_value) / tail_span
                for idx in range(last_idx + 1, len(interpolated)):
                    interpolated[idx] = round(last_value + step * (idx - last_idx), 4)
                    point_types[idx] = "anchor"

            filled_scores = [round(float(value if value is not None else global_avg), 4) for value in interpolated]
            point_types = [point_type if point_type != "missing" else "anchor" for point_type in point_types]

        data = SentimentTrend24HData(
            labels=labels,
            data=filled_scores,
            point_types=point_types,
            start_time=start_time,
            end_time=now,
            fill_strategy="linear_interpolation_with_global_edge_anchors",
        )
        return ApiResponse(code=200, data=data, msg="ok")

    except SQLAlchemyError as e:
        return ApiResponse(code=400, data=None, msg=f"数据库查询失败: {e}")


@router.get("/users/{user_id}/recommendation", response_model=ApiResponse[RecommendationData])
async def get_user_recommendation(
    user_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[RecommendationData]:
    """
    用户推荐接口（多因子动态加权精排引擎 + XAI 可解释推荐）

    算法流程：
    1) 读取用户 risk_profile，提取风险等级、平均情绪、情绪波动率
    2) 按 risk_level 召回同风险等级下的全部候选产品
    3) 对每个候选产品进行多因子打分：
       Score = (annual_yield * 0.4) + (sharpe_ratio * 10 * 0.3) - (max_drawdown * volatility * 5)

       含义说明：
       - annual_yield * 0.4：奖励收益能力
       - sharpe_ratio * 10 * 0.3：奖励风险收益效率（夏普比率乘 10 是为了统一量纲）
       - max_drawdown * volatility * 5：对回撤做动态惩罚；用户波动率越高，惩罚越强

    4) 按 Score 降序排序，截取 Top 3
    5) 为 Top 3 生成 recommend_reason 解释文案，返回给前端用于 XAI 展示
    """
    try:
        # 第一步：读取用户画像，提取精排所需的核心用户因子
        profile_stmt = select(RiskProfile).where(RiskProfile.user_id == user_id)
        profile_result = await db.execute(profile_stmt)
        profile = profile_result.scalar_one_or_none()

        if profile is None:
            return ApiResponse(code=404, data=None, msg=f"用户 {user_id} 未找到风险画像")

        user_avg_sentiment = float(profile.avg_sentiment)
        user_volatility = float(profile.volatility)
        user_risk_level = profile.risk_level

        # 第二步：召回阶段，只召回与用户风险等级一致的候选产品
        candidate_stmt = select(Product).where(Product.risk_rating == user_risk_level)
        candidate_result = await db.execute(candidate_stmt)
        candidate_products = candidate_result.scalars().all()

        profile_info = UserProfileInfo(
            user_id=profile.user_id,
            avg_sentiment=user_avg_sentiment,
            volatility=user_volatility,
            post_count=int(profile.post_count),
            risk_level=user_risk_level,
            update_time=profile.update_time,
        )

        # 第三步：多因子动态加权精排
        ranked_candidates: list[tuple[float, Product]] = []
        for product in candidate_products:
            annual_yield = float(product.annual_yield)
            sharpe_ratio = float(product.sharpe_ratio)
            max_drawdown = float(product.max_drawdown)

            score = (
                (annual_yield * 0.4)
                + (sharpe_ratio * 10 * 0.3)
                - (max_drawdown * user_volatility * 5)
            )
            ranked_candidates.append((score, product))

        ranked_candidates.sort(key=lambda item: item[0], reverse=True)
        top_products = ranked_candidates[:3]

        # 第四步：XAI 解释生成
        product_list = [
            RecommendationProduct(
                product_id=int(product.product_id),
                product_name=product.product_name,
                product_type=product.product_type,
                risk_rating=product.risk_rating,
                annual_yield=float(product.annual_yield),
                max_drawdown=float(product.max_drawdown),
                sharpe_ratio=float(product.sharpe_ratio),
                recommendation_score=round(float(score), 2),
                recommend_reason=build_recommend_reason(
                    product=product,
                    user_avg_sentiment=user_avg_sentiment,
                    user_volatility=user_volatility,
                    score=score,
                ),
                tags=product.tags if isinstance(product.tags, list) else (list(product.tags.values()) if isinstance(product.tags, dict) else []),
                purchase_url=product.purchase_url,
            )
            for score, product in top_products
        ]

        # 从 raw_data 取该用户最近 10 条发言，按 post_time 升序，提供真实历史时间线
        trend_stmt = (
            select(RawData.post_time, RawData.sentiment_score)
            .where(
                RawData.user_id == user_id,
                RawData.sentiment_score.is_not(None),
            )
            .order_by(RawData.post_time.desc())
            .limit(10)
        )
        trend_result = await db.execute(trend_stmt)
        trend_rows = trend_result.fetchall()
        trend_history = [
            TrendHistoryPoint(
                time=row.post_time.strftime("%m-%d %H:%M:%S"),
                score=round(float(row.sentiment_score), 4),
            )
            for row in reversed(trend_rows)
        ]

        data = RecommendationData(profile=profile_info, products=product_list, trend_history=trend_history)
        return ApiResponse(code=200, data=data, msg="ok")

    except SQLAlchemyError as e:
        return ApiResponse(code=400, data=None, msg=f"数据库查询失败: {e}")


@router.get("/users/{user_id}/trend", response_model=ApiResponse[TrendData])
async def get_user_trend(
    user_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[TrendData]:
    """
    用户情绪趋势接口：
    - 从 user_sentiment 取最近 10 条（按 analyze_time 倒序）
    - 返回给前端用于 ECharts 折线图
    """
    try:
        trend_stmt = (
            select(UserSentiment)
            .where(UserSentiment.user_id == user_id)
            .order_by(UserSentiment.analyze_time.desc())
            .limit(10)
        )
        trend_result = await db.execute(trend_stmt)
        rows = trend_result.scalars().all()

        if not rows:
            return ApiResponse(code=404, data=None, msg=f"用户 {user_id} 暂无情绪趋势数据")

        # 为了前端折线图从左到右时间递增，返回前做一次反转
        points = [
            TrendPoint(
                analyze_time=row.analyze_time,
                sentiment_score=float(row.sentiment_score),
                sentiment_label=row.sentiment_label,
            )
            for row in reversed(rows)
        ]

        data = TrendData(user_id=user_id, points=points)
        return ApiResponse(code=200, data=data, msg="ok")

    except SQLAlchemyError as e:
        return ApiResponse(code=400, data=None, msg=f"数据库查询失败: {e}")
