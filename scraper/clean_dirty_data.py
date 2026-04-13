"""一次性清洗脚本：删除 raw_data 中 source_post_id 不合规的脏数据"""
import asyncio
import sys
sys.path.insert(0, 'backend')

from sqlalchemy import text
from app.core.database import engine


async def main():
    async with engine.begin() as conn:
        # 统计脏数据：长度不在 8~11 之间，或含非数字字符
        dirty_count = (await conn.execute(text(
            "SELECT COUNT(*) FROM raw_data "
            "WHERE LENGTH(source_post_id) < 8 "
            "   OR LENGTH(source_post_id) > 11 "
            "   OR source_post_id REGEXP '[^0-9]'"
        ))).scalar_one()
        print(f"检测到脏数据: {dirty_count} 条")

        if dirty_count == 0:
            print("无需清洗。")
            await engine.dispose()
            return

        # 打印脏数据样本
        samples = (await conn.execute(text(
            "SELECT source_post_id, LENGTH(source_post_id) as id_len, LEFT(content, 30) "
            "FROM raw_data "
            "WHERE LENGTH(source_post_id) < 8 "
            "   OR LENGTH(source_post_id) > 11 "
            "   OR source_post_id REGEXP '[^0-9]' "
            "LIMIT 10"
        ))).fetchall()
        print("--- 脏数据样本 ---")
        for r in samples:
            print(f"  id={r[0]} len={r[1]} content={r[2]}")

        # 执行删除
        result = await conn.execute(text(
            "DELETE FROM raw_data "
            "WHERE LENGTH(source_post_id) < 8 "
            "   OR LENGTH(source_post_id) > 11 "
            "   OR source_post_id REGEXP '[^0-9]'"
        ))
        print(f"\n成功删除脏数据: {result.rowcount} 条")

        # 清洗后统计
        total = (await conn.execute(text("SELECT COUNT(*) FROM raw_data"))).scalar_one()
        print(f"清洗后 raw_data 总计: {total} 条")

    await engine.dispose()

asyncio.run(main())
