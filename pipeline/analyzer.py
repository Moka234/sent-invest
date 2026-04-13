from __future__ import annotations

"""
pipeline/analyzer.py

AI 情感分析引擎（Phase 2）
---------------------------------
职责：
1) 从 raw_data 读取 process_status=1（已清洗）数据
2) 使用 HuggingFace 金融情感模型批量推理（含 no_grad 防爆存）
3) 将结果写回 raw_data，并将 process_status 严格推进到 2
4) 同步冗余写入 user_sentiment，供后续用户画像使用

说明：
- 严格使用 SQLAlchemy 2.0 异步语法
- 仅新增本文件，不修改 scraper/ 与 cleaner.py
"""

import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import torch
from sqlalchemy import select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from tqdm import tqdm
from transformers import AutoModelForSequenceClassification, AutoTokenizer


# -----------------------------------------------------------------------------
# 复用 backend 异步连接池与 ORM 模型
# -----------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.base import RawData, UserSentiment  # noqa: E402


# -----------------------------------------------------------------------------
# 模型配置
# -----------------------------------------------------------------------------
MODEL_NAME = "hw2942/bert-base-chinese-finetuning-financial-news-sentiment-v2"
DEFAULT_BATCH_SIZE = 16
MAX_LENGTH = 256


@dataclass
class AnalyzedRecord:
    raw_id: int
    user_id: str
    clean_content: str
    sentiment_score: float  # 方向性情感指数（0-1）：P_pos*1 + P_neu*0.5 + P_neg*0
    sentiment_label: str    # 乐观 / 中立 / 悲观


def _normalize_label(label: str) -> str:
    """统一标签文本，便于关键词匹配。"""
    return (label or "").strip().lower().replace("_", "").replace("-", "")


def _resolve_label_mapping(
    id2label: dict[int, str],
    num_labels: int,
) -> tuple[int, int, int, dict[int, str]]:
    """
    根据模型 id2label 解析：
    - 正向/中立/负向类别索引（用于方向性情感指数）
    - 各 index 映射到中文标签（乐观/中立/悲观）

    若模型标签文本不标准，则采用常见三分类兜底：0=负面, 1=中性, 2=正面。
    """
    positive_idx: int | None = None
    neutral_idx: int | None = None
    negative_idx: int | None = None
    chinese_map: dict[int, str] = {}

    for idx, raw_label in id2label.items():
        n = _normalize_label(raw_label)

        if any(k in n for k in ["positive", "bullish", "optimistic", "乐观", "积极", "pos"]):
            chinese_map[idx] = "乐观"
            if positive_idx is None:
                positive_idx = idx
        elif any(k in n for k in ["neutral", "中立", "中性", "neu"]):
            chinese_map[idx] = "中立"
            if neutral_idx is None:
                neutral_idx = idx
        elif any(k in n for k in ["negative", "bearish", "pessimistic", "悲观", "消极", "neg"]):
            chinese_map[idx] = "悲观"
            if negative_idx is None:
                negative_idx = idx

    # 兜底策略：三分类常见顺序 (neg, neu, pos)
    if num_labels >= 3:
        chinese_map.setdefault(0, "悲观")
        chinese_map.setdefault(1, "中立")
        chinese_map.setdefault(2, "乐观")
        if negative_idx is None:
            negative_idx = 0
        if neutral_idx is None:
            neutral_idx = 1
        if positive_idx is None:
            positive_idx = 2
    elif num_labels == 2:
        # 二分类兜底：0=悲观,1=乐观；中立缺失时后处理固定按 0.5 贡献
        chinese_map.setdefault(0, "悲观")
        chinese_map.setdefault(1, "乐观")
        if negative_idx is None:
            negative_idx = 0
        if positive_idx is None:
            positive_idx = 1
        if neutral_idx is None:
            neutral_idx = negative_idx
    else:
        # 极端场景：单分类（通常不会发生）
        chinese_map.setdefault(0, "中立")
        if positive_idx is None:
            positive_idx = 0
        if neutral_idx is None:
            neutral_idx = 0
        if negative_idx is None:
            negative_idx = 0

    return positive_idx, neutral_idx, negative_idx, chinese_map


class SentimentEngine:
    """封装模型加载与批量推理逻辑。"""

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self.model_name = model_name
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        print(f"[模型] 正在加载: {model_name}")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.to(self.device)
        self.model.eval()

        raw_id2label: dict[Any, Any] = self.model.config.id2label or {}
        self.id2label: dict[int, str] = {
            int(k): str(v) for k, v in raw_id2label.items()
        } if raw_id2label else {}

        num_labels = int(getattr(self.model.config, "num_labels", len(self.id2label) or 3))
        (
            self.positive_idx,
            self.neutral_idx,
            self.negative_idx,
            self.zh_label_map,
        ) = _resolve_label_mapping(self.id2label, num_labels)

        print(f"[模型] 加载完成，device={self.device}")
        print(f"[模型] id2label={self.id2label}")
        print(
            "[模型] idx映射 "
            f"pos={self.positive_idx}, neu={self.neutral_idx}, neg={self.negative_idx}, "
            f"zh_map={self.zh_label_map}"
        )

    def predict_batch(self, texts: list[str]) -> tuple[list[float], list[str]]:
        """
        批量推理。
        返回：
        - 基于多空净差非线性极化激活后的情感指数列表（0-1）
        - 预测标签中文列表（乐观/中立/悲观），仍由 argmax 决定
        """
        encoded = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=MAX_LENGTH,
            return_tensors="pt",
        )
        encoded = {k: v.to(self.device) for k, v in encoded.items()}

        # 关键：禁用梯度，降低内存/显存占用，防止 OOM
        with torch.no_grad():
            outputs = self.model(**encoded)
            logits = outputs.logits
            probs = torch.softmax(logits, dim=-1)

        p_pos = probs[:, self.positive_idx]
        p_neu = probs[:, self.neutral_idx]
        p_neg = probs[:, self.negative_idx]

        # 非线性极化激活：放大多空净差，缓解中立概率主导导致的分值塌陷
        diff = p_pos - p_neg
        amplified_diff = torch.sign(diff) * torch.sqrt(torch.abs(diff))
        scores_tensor = 0.5 + 0.5 * amplified_diff

        pred_indices = torch.argmax(probs, dim=-1).detach().cpu().tolist()
        labels = [self.zh_label_map.get(int(idx), "中立") for idx in pred_indices]
        scores = [float(max(0.0, min(1.0, s))) for s in scores_tensor.detach().cpu().tolist()]

        return scores, labels


async def fetch_cleaned_records() -> list[dict[str, Any]]:
    """读取所有 process_status=1 且 clean_content 有效的数据。"""
    stmt = (
        select(RawData.id, RawData.user_id, RawData.clean_content)
        .where(
            RawData.process_status == 1,
            RawData.clean_content.is_not(None),
            RawData.clean_content != "",
        )
        .order_by(RawData.id)
    )

    async with AsyncSessionLocal() as session:
        result = await session.execute(stmt)
        rows = result.fetchall()

    records = [
        {
            "id": int(r.id),
            "user_id": str(r.user_id),
            "clean_content": str(r.clean_content),
        }
        for r in rows
    ]
    print(f"[读取] 待分析记录数（status=1）: {len(records)}")
    return records


async def write_back_results(analyzed: list[AnalyzedRecord]) -> None:
    """
    将推理结果写回数据库：
    1) 更新 raw_data（score/label/update_time/process_status=2）
    2) 冗余插入 user_sentiment

    全流程使用 SQLAlchemy 2.0 异步语法。
    """
    if not analyzed:
        print("[写回] 无可写回数据")
        return

    now = datetime.now()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            # 1) 更新 raw_data 状态机 1 -> 2
            for item in tqdm(analyzed, desc="写回 raw_data", unit="row"):
                stmt = (
                    update(RawData)
                    .where(
                        RawData.id == item.raw_id,
                        RawData.process_status == 1,  # 二次校验，保证单向流转
                    )
                    .values(
                        sentiment_score=item.sentiment_score,
                        sentiment_label=item.sentiment_label,
                        update_time=now,
                        process_status=2,
                    )
                )
                await session.execute(stmt)

            # 2) 同步冗余写入 user_sentiment（基于 raw_data_id 幂等去重）
            sentiment_values = [
                {
                    "raw_data_id": item.raw_id,
                    "user_id": item.user_id,
                    "clean_content": item.clean_content,
                    "sentiment_score": item.sentiment_score,
                    "sentiment_label": item.sentiment_label,
                    "analyze_time": now,
                }
                for item in analyzed
            ]
            sentiment_stmt = mysql_insert(UserSentiment.__table__).values(sentiment_values)
            sentiment_stmt = sentiment_stmt.on_duplicate_key_update(
                user_id=sentiment_stmt.inserted.user_id,
                clean_content=sentiment_stmt.inserted.clean_content,
                sentiment_score=sentiment_stmt.inserted.sentiment_score,
                sentiment_label=sentiment_stmt.inserted.sentiment_label,
                analyze_time=sentiment_stmt.inserted.analyze_time,
            )
            await session.execute(sentiment_stmt)

    print(f"[写回] raw_data 已更新并推进为 status=2：{len(analyzed)} 条")
    print(f"[写回] user_sentiment 已基于 raw_data_id 幂等写入：{len(analyzed)} 条")


async def run_analyzer(batch_size: int = DEFAULT_BATCH_SIZE) -> None:
    """分析主流程：读取 -> 批量推理 -> 写回。"""
    print("=" * 60)
    print(" SentInvest AI 情感分析引擎启动（Phase 2）")
    print("=" * 60)

    records = await fetch_cleaned_records()
    if not records:
        print("[退出] 当前无 process_status=1 的待分析数据")
        return

    engine = SentimentEngine(model_name=MODEL_NAME)

    analyzed: list[AnalyzedRecord] = []

    for i in tqdm(range(0, len(records), batch_size), desc="模型推理", unit="batch"):
        batch = records[i : i + batch_size]
        texts = [r["clean_content"] for r in batch]

        scores, labels = engine.predict_batch(texts)

        for r, score, label in zip(batch, scores, labels, strict=False):
            analyzed.append(
                AnalyzedRecord(
                    raw_id=r["id"],
                    user_id=r["user_id"],
                    clean_content=r["clean_content"],
                    sentiment_score=score,
                    sentiment_label=label,
                )
            )

    await write_back_results(analyzed)

    print("=" * 60)
    print(" AI 情感分析完成")
    print(f" 总处理条数: {len(analyzed)}")
    print(" 状态流转: raw_data.process_status 1 -> 2")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_analyzer())
