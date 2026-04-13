from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应包裹结构。"""

    code: int = Field(..., description="业务状态码，200/400/404")
    data: T | None = Field(default=None, description="响应数据体")
    msg: str = Field(..., description="响应信息")


class RecommendationProduct(BaseModel):
    """推荐产品结构。"""

    product_id: int
    product_name: str
    product_type: str
    risk_rating: str
    annual_yield: float
    max_drawdown: float
    sharpe_ratio: float
    recommendation_score: float
    recommend_reason: str
    tags: list[str]
    purchase_url: str | None = None


class TrendHistoryPoint(BaseModel):
    """真实历史情绪点（来自 raw_data.post_time）。"""

    time: str
    score: float


class UserProfileInfo(BaseModel):
    """用户画像结构。"""

    user_id: str
    avg_sentiment: float
    volatility: float
    post_count: int
    risk_level: str
    update_time: datetime


class RecommendationData(BaseModel):
    """用户推荐接口返回数据。"""

    profile: UserProfileInfo
    products: list[RecommendationProduct]
    trend_history: list[TrendHistoryPoint] = Field(default_factory=list)


class RiskLevelCountItem(BaseModel):
    """风险等级人数统计项。"""

    risk_level: str
    user_count: int


class DashboardData(BaseModel):
    """大盘聚合数据结构。"""

    global_avg_sentiment: float
    risk_level_distribution: list[RiskLevelCountItem]


class SentimentTrend24HData(BaseModel):
    """全站过去 24 小时情绪走势。"""

    labels: list[str]
    data: list[float]
    point_types: list[str] = Field(default_factory=list, description="每个点的来源：real / interpolated / anchor")
    start_time: datetime
    end_time: datetime
    fill_strategy: str = "linear_interpolation_with_global_edge_anchors"


class TrendPoint(BaseModel):
    """用户情绪趋势点结构。"""

    analyze_time: datetime
    sentiment_score: float
    sentiment_label: str


class TrendData(BaseModel):
    """用户情绪趋势数据结构。"""

    user_id: str
    points: list[TrendPoint]
