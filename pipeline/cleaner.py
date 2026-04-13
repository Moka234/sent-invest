from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# 使用当前 Python 解释器给 Spark worker/driver
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select, update
from app.core.database import AsyncSessionLocal
from app.models.base import RawData


def get_spark():
    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder
        .master("local[*]")
        .appName("SentInvestCleaner")
        .config("spark.driver.host", "127.0.0.1")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.driver.memory", "1g")
        .config("spark.sql.shuffle.partitions", "1")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


async def fetch_pending_records() -> list[dict[str, Any]]:
    stmt = (
        select(RawData.id, RawData.content)
        .where(RawData.process_status == 0)
        .order_by(RawData.id)
    )
    async with AsyncSessionLocal() as session:
        result = await session.execute(stmt)
        rows = result.fetchall()

    records = [{"id": row.id, "content": row.content or ""} for row in rows]
    print(f"[读取] 共发现 {len(records)} 条 process_status=0 的待清洗记录")
    return records


def clean_with_spark(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from pyspark.sql import Row, functions as F
    from pyspark.sql.types import LongType, StringType, StructField, StructType

    if not records:
        return []

    spark = get_spark()

    schema = StructType([
        StructField("id", LongType(), False),
        StructField("content", StringType(), True),
    ])
    spark_rows = [Row(id=int(r["id"]), content=r["content"]) for r in records]
    sdf = spark.createDataFrame(spark_rows, schema=schema).coalesce(1)

    cleaned_sdf = (
        sdf
        .withColumn("clean", F.regexp_replace(F.col("content"), "<[^>]+>", ""))
        .withColumn("clean", F.regexp_replace(F.col("clean"), "https?://[^\\s]+", ""))
        .withColumn("clean", F.regexp_replace(F.col("clean"), "\\$[^$]+\\$", ""))
        .withColumn("clean", F.regexp_replace(F.col("clean"), "[\\r\\n\\t]+", " "))
        .withColumn("clean", F.regexp_replace(F.col("clean"), "[ ]{2,}", " "))
        .withColumn("clean", F.trim(F.col("clean")))
        .withColumn("clean", F.substring(F.col("clean"), 1, 1000))
    )

    rows = cleaned_sdf.select("id", "clean").collect()
    result = [{"id": row["id"], "clean_content": row["clean"]} for row in rows]
    print(f"[清洗] Spark 清洗完成，共处理 {len(result)} 条")
    return result


async def update_cleaned_records(cleaned: list[dict[str, Any]]) -> None:
    if not cleaned:
        print("[写回] 无数据需要写回")
        return

    now = datetime.now()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            for item in cleaned:
                stmt = (
                    update(RawData)
                    .where(
                        RawData.id == item["id"],
                        RawData.process_status == 0,
                    )
                    .values(
                        clean_content=item["clean_content"],
                        update_time=now,
                        process_status=1,
                    )
                )
                await session.execute(stmt)

    print(f"[写回] 成功更新 {len(cleaned)} 条记录，process_status 已推进至 1")


async def run_cleaner() -> None:
    print("=" * 50)
    print(" SentInvest Spark 清洗引擎启动")
    print("=" * 50)

    records = await fetch_pending_records()
    if not records:
        print("[退出] 暂无待清洗数据，流程结束")
        return

    cleaned = clean_with_spark(records)
    await update_cleaned_records(cleaned)

    print("=" * 50)
    print(" 清洗完成！")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(run_cleaner())
