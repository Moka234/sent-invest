from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

_UTF8MB4 = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


class Base(DeclarativeBase):
    pass


class RawData(Base):
    __tablename__ = "raw_data"
    __table_args__ = _UTF8MB4

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_platform: Mapped[str] = mapped_column(String(255), nullable=False)
    source_post_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    clean_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    post_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    # process_status 状态机：
    # 0 = 爬虫入库初始状态
    # 1 = Spark 清洗完成（已写入 clean_content）
    # 2 = FinBERT 打分完成（已写入 sentiment_score/sentiment_label）
    process_status: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class UserSentiment(Base):
    __tablename__ = "user_sentiment"
    __table_args__ = _UTF8MB4

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_data_id: Mapped[int] = mapped_column(ForeignKey("raw_data.id"), unique=True, index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    clean_content: Mapped[str] = mapped_column(Text, nullable=False)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False)
    sentiment_label: Mapped[str] = mapped_column(String(64), nullable=False)
    analyze_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class RiskProfile(Base):
    __tablename__ = "risk_profile"
    __table_args__ = _UTF8MB4

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    avg_sentiment: Mapped[float] = mapped_column(Float, nullable=False)
    volatility: Mapped[float] = mapped_column(Float, nullable=False)
    post_count: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(64), nullable=False)
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Product(Base):
    __tablename__ = "products"
    __table_args__ = _UTF8MB4

    product_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    product_type: Mapped[str] = mapped_column(String(255), nullable=False)
    risk_rating: Mapped[str] = mapped_column(String(64), nullable=False)
    annual_yield: Mapped[float] = mapped_column(Float, nullable=False)
    max_drawdown: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sharpe_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tags: Mapped[dict] = mapped_column(JSON, nullable=False)
    purchase_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
