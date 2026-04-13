import asyncio

from app.core.database import engine
from app.models.base import Base


async def init_db() -> None:
    """
    异步初始化数据库表结构：
    - 使用 engine.begin() 打开异步事务连接
    - 使用 run_sync + Base.metadata.create_all 创建全部 ORM 对应表
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    # 直接运行本文件即可自动建表
    asyncio.run(init_db())