"""
backend/scripts/seed_products.py
=================================
清空旧数据，注入 18 条理财产品种子数据。
覆盖保守型 / 稳健型 / 激进型三类，每类 6 条，
并补充年化收益、最大回撤、夏普比率与真实购买链接。

运行方式：
  python backend/scripts/seed_products.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text

from app.core.database import engine
from app.models.base import Product


PRODUCTS = [
    # ── 保守型（货币 / 中短债 / 纯债）────────────────────────────
    {
        "product_name": "天弘余额宝货币A(000198)",
        "product_type": "货币基金",
        "risk_rating": "保守型",
        "annual_yield": 1.86,
        "max_drawdown": 0.03,
        "sharpe_ratio": 2.42,
        "tags": ["现金管理", "低波动", "活期替代", "高流动性"],
        "purchase_url": "https://fund.eastmoney.com/000198.html",
    },
    {
        "product_name": "建信现金添益货币A(000693)",
        "product_type": "货币基金",
        "risk_rating": "保守型",
        "annual_yield": 2.04,
        "max_drawdown": 0.05,
        "sharpe_ratio": 2.18,
        "tags": ["货币增强", "低风险", "短久期", "稳健申赎"],
        "purchase_url": "https://fund.eastmoney.com/000693.html",
    },
    {
        "product_name": "易方达天天理财货币A(000009)",
        "product_type": "货币基金",
        "risk_rating": "保守型",
        "annual_yield": 1.92,
        "max_drawdown": 0.04,
        "sharpe_ratio": 2.27,
        "tags": ["现金仓位", "高流动性", "稳健增值", "短期配置"],
        "purchase_url": "https://fund.eastmoney.com/000009.html",
    },
    {
        "product_name": "招商产业债券A(217022)",
        "product_type": "纯债基金",
        "risk_rating": "保守型",
        "annual_yield": 3.78,
        "max_drawdown": 0.62,
        "sharpe_ratio": 1.83,
        "tags": ["信用债", "票息策略", "低回撤", "稳健收息"],
        "purchase_url": "https://fund.eastmoney.com/217022.html",
    },
    {
        "product_name": "广发纯债债券A(270048)",
        "product_type": "纯债基金",
        "risk_rating": "保守型",
        "annual_yield": 3.41,
        "max_drawdown": 0.74,
        "sharpe_ratio": 1.69,
        "tags": ["纯债底仓", "低波动", "机构偏好", "票息累积"],
        "purchase_url": "https://fund.eastmoney.com/270048.html",
    },
    {
        "product_name": "易方达稳健收益债券B(110008)",
        "product_type": "债券基金",
        "risk_rating": "保守型",
        "annual_yield": 3.96,
        "max_drawdown": 0.88,
        "sharpe_ratio": 1.58,
        "tags": ["债券增强", "稳健票息", "低风险", "中短久期"],
        "purchase_url": "https://fund.eastmoney.com/110008.html",
    },

    # ── 稳健型（宽基 / 偏债混合 / 平衡混合）──────────────────────
    {
        "product_name": "易方达沪深300ETF联接A(110020)",
        "product_type": "指数基金",
        "risk_rating": "稳健型",
        "annual_yield": 7.64,
        "max_drawdown": 11.8,
        "sharpe_ratio": 1.06,
        "tags": ["沪深300", "宽基配置", "蓝筹核心", "长期定投"],
        "purchase_url": "https://fund.eastmoney.com/110020.html",
    },
    {
        "product_name": "天弘沪深300ETF联接A(000961)",
        "product_type": "指数基金",
        "risk_rating": "稳健型",
        "annual_yield": 6.88,
        "max_drawdown": 10.6,
        "sharpe_ratio": 0.94,
        "tags": ["宽基底仓", "被动投资", "低费率", "大盘风格"],
        "purchase_url": "https://fund.eastmoney.com/000961.html",
    },
    {
        "product_name": "景顺长城新兴成长混合(260108)",
        "product_type": "混合基金",
        "risk_rating": "稳健型",
        "annual_yield": 8.57,
        "max_drawdown": 14.2,
        "sharpe_ratio": 0.88,
        "tags": ["成长均衡", "主动管理", "行业分散", "中风险"],
        "purchase_url": "https://fund.eastmoney.com/260108.html",
    },
    {
        "product_name": "交银稳健配置混合A(519690)",
        "product_type": "平衡混合",
        "risk_rating": "稳健型",
        "annual_yield": 6.12,
        "max_drawdown": 8.9,
        "sharpe_ratio": 1.14,
        "tags": ["股债平衡", "稳中求进", "分散配置", "回撤可控"],
        "purchase_url": "https://fund.eastmoney.com/519690.html",
    },
    {
        "product_name": "兴全合润混合LOF(163406)",
        "product_type": "偏股混合",
        "risk_rating": "稳健型",
        "annual_yield": 9.36,
        "max_drawdown": 13.7,
        "sharpe_ratio": 0.92,
        "tags": ["长期绩优", "主动精选", "核心持仓", "稳健进攻"],
        "purchase_url": "https://fund.eastmoney.com/163406.html",
    },
    {
        "product_name": "富国天惠成长混合A(161005)",
        "product_type": "混合基金",
        "risk_rating": "稳健型",
        "annual_yield": 8.91,
        "max_drawdown": 12.5,
        "sharpe_ratio": 1.01,
        "tags": ["价值成长", "均衡配置", "明星老基", "中长期持有"],
        "purchase_url": "https://fund.eastmoney.com/161005.html",
    },

    # ── 激进型（行业 ETF / 主题基金 / 股票基金）──────────────────
    {
        "product_name": "招商中证白酒指数A(161725)",
        "product_type": "行业指数基金",
        "risk_rating": "激进型",
        "annual_yield": 18.70,
        "max_drawdown": 29.4,
        "sharpe_ratio": 0.79,
        "tags": ["白酒赛道", "消费龙头", "行业集中", "高弹性"],
        "purchase_url": "https://fund.eastmoney.com/161725.html",
    },
    {
        "product_name": "国联安中证全指半导体ETF联接A(007300)",
        "product_type": "行业指数基金",
        "risk_rating": "激进型",
        "annual_yield": 24.80,
        "max_drawdown": 36.2,
        "sharpe_ratio": 0.72,
        "tags": ["半导体", "科技成长", "高波动", "行业Beta"],
        "purchase_url": "https://fund.eastmoney.com/007300.html",
    },
    {
        "product_name": "华夏中证新能源汽车ETF联接A(013013)",
        "product_type": "行业指数基金",
        "risk_rating": "激进型",
        "annual_yield": 16.35,
        "max_drawdown": 31.7,
        "sharpe_ratio": 0.68,
        "tags": ["新能源车", "景气赛道", "高成长", "主题配置"],
        "purchase_url": "https://fund.eastmoney.com/013013.html",
    },
    {
        "product_name": "中欧医疗健康混合A(003095)",
        "product_type": "主题混合基金",
        "risk_rating": "激进型",
        "annual_yield": 15.42,
        "max_drawdown": 27.9,
        "sharpe_ratio": 0.74,
        "tags": ["医疗赛道", "创新药", "高成长", "波动较高"],
        "purchase_url": "https://fund.eastmoney.com/003095.html",
    },
    {
        "product_name": "诺安成长混合(320007)",
        "product_type": "股票型基金",
        "risk_rating": "激进型",
        "annual_yield": 22.60,
        "max_drawdown": 38.5,
        "sharpe_ratio": 0.58,
        "tags": ["芯片成长", "高贝塔", "科技主题", "高风险高收益"],
        "purchase_url": "https://fund.eastmoney.com/320007.html",
    },
    {
        "product_name": "东方新能源汽车主题混合(400015)",
        "product_type": "主题混合基金",
        "risk_rating": "激进型",
        "annual_yield": 19.84,
        "max_drawdown": 33.6,
        "sharpe_ratio": 0.66,
        "tags": ["新能源", "主题进攻", "高成长", "高回撤"],
        "purchase_url": "https://fund.eastmoney.com/400015.html",
    },
]


async def main() -> None:
    print("=" * 58)
    print(" SentInvest 理财产品种子数据扩容注入（18条）")
    print("=" * 58)

    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM products"))
        print("已清空旧产品数据")

        await conn.execute(Product.__table__.insert(), PRODUCTS)

        total = (await conn.execute(text("SELECT COUNT(*) FROM products"))).scalar_one()
        print(f"注入完成，products 表当前记录数: {total}")
        print()
        print("产品列表：")
        rows = (
            await conn.execute(
                text(
                    """
                    SELECT product_name, risk_rating, annual_yield, max_drawdown, sharpe_ratio
                    FROM products
                    ORDER BY FIELD(risk_rating, '保守型', '稳健型', '激进型'), annual_yield
                    """
                )
            )
        ).fetchall()
        for r in rows:
            print(
                f"  [{r.risk_rating}] {r.product_name} "
                f"年化{r.annual_yield:.2f}% / 回撤{r.max_drawdown:.2f}% / 夏普{r.sharpe_ratio:.2f}"
            )

    await engine.dispose()
    print()
    print("=" * 58)
    print(" 种子数据注入完成！")
    print("=" * 58)


if __name__ == "__main__":
    asyncio.run(main())
