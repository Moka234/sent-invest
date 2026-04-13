# 智心理财 (SentInvest) - 大厂级架构与核心开发指南

## 1. 架构定位与核心业务流 (Architecture & Business Flow)
本项目《理财社群用户情感分析与理财产品推荐系统》采用**微服务化解耦**思想，在单体仓库（Monorepo）下实现“数据采集-流式清洗-大模型推理-业务推荐-数据可视化”的完整闭环。
* **数据流向**：异步高并发采集 -> MySQL缓冲池 -> PySpark微批清洗 -> FinBERT批量推理 -> FastAPI画像聚合与推荐匹配 -> Vue3/ECharts大屏渲染。
* **设计哲学**：轻量、高可用、状态单向流转、读写完全解耦。

## 2. 技术栈与环境隔离规范 (Tech Stack & Isolation)
为了彻底解决依赖冲突（如PySpark的Java依赖与FastAPI的轻量化冲突），系统实施严格的**物理与环境隔离**。AI 在生成代码时，必须遵守以下子域约束：
* **`scraper/` (数据采集)**：Python 3.10+, `aiohttp`, `BeautifulSoup4`。必须具备重试机制（如引入 `tenacity`）和反爬应对（随机User-Agent）。
* **`pipeline/` (清洗与AI)**：Python 3.10+, `pyspark.sql` (本地模式), `transformers` (FinBERT), `torch`。必须具备批次大小（Batch Size）控制，防止显存/内存溢出（OOM）。
* **`backend/` (业务后端)**：FastAPI, `uvicorn`, `SQLAlchemy 2.0+` (全异步), `Pydantic V2`。
* **`frontend/` (业务前端)**：Vue 3 (Composition API, `<script setup>`), Vite, Element Plus, ECharts, Axios。
* **全局配置**：所有数据库凭据、API Keys 必须通过 `.env` 文件读取，**绝对禁止**在代码中硬编码密码。

## 3. 核心数据库模型 (Database Schema)
系统依托 MySQL 8.0 作为数据流转枢纽。AI 编写 ORM (`models.py`) 和 SQL 时，必须严格遵照以下结构设计：

| 表名 | 字段与类型 | 业务意义与核心逻辑 |
| :--- | :--- | :--- |
| `raw_data` | `id` (PK)<br>`source_platform` (VARCHAR)<br>`source_post_id` (VARCHAR, **UNIQUE**)<br>`user_id` (VARCHAR)<br>`topic` (VARCHAR)<br>`content` (TEXT)<br>`clean_content` (TEXT)<br>`sentiment_score` (FLOAT)<br>`sentiment_label` (VARCHAR)<br>`post_time` (DATETIME)<br>`create_time` (DATETIME)<br>`update_time` (DATETIME)<br>`process_status` (INT) | **核心状态机缓冲表**。<br>`source_post_id`: 源站帖子唯一ID，利用数据库UNIQUE约束实现爬虫秒级去重。<br>`process_status=0`: 爬虫入库初始状态。<br>`process_status=1`: Spark清洗后写入`clean_content`并修改此状态。<br>`process_status=2`: FinBERT打分后写入score与label并修改此状态。 |
| `user_sentiment` | `id` (PK)<br>`user_id` (INDEX)<br>`clean_content` (TEXT)<br>`sentiment_score` (FLOAT)<br>`sentiment_label` (VARCHAR)<br>`analyze_time` (DATETIME) | **个体情感明细表**。<br>当`raw_data`状态变为`2`时同步插入，专用于前端查询个体的历史情绪时间序列。 |
| `risk_profile` | `user_id` (PK)<br>`avg_sentiment` (FLOAT)<br>`volatility` (FLOAT)<br>`post_count` (INT)<br>`risk_level` (VARCHAR)<br>`update_time` (DATETIME) | **动态风险画像表**。<br>`post_count`: 参与计算的发言总数，用于判断画像置信度（如少于5条判定为置信度低）。<br>`risk_level`: 激进型/稳健型/保守型。 |
| `products` | `product_id` (PK)<br>`product_name` (VARCHAR)<br>`product_type` (VARCHAR)<br>`risk_rating` (VARCHAR)<br>`annual_yield` (FLOAT)<br>`tags` (JSON) | **理财产品资产池**。<br>`tags`: 用于前端UI卡片展示的产品亮点（如"固收+"）。<br>`risk_rating`: 用于与用户的`risk_level`进行匹配推荐。 |

## 4. 目录结构规范 (Monorepo Structure)
创建新文件必须放置在对应层级内：

```text
sent-invest/
├── .env                  # 全局环境变量 (DB_URL, etc.)
├── scraper/              # 异步爬虫模块
│   └── requirements.txt  # 爬虫专属依赖
├── pipeline/             # Spark清洗与FinBERT推理
│   └── requirements.txt  # 大数据与AI专属依赖
├── backend/              # FastAPI 后端服务
│   ├── requirements.txt  # Web专属依赖
│   └── app/
│       ├── api/          # 路由层 (RESTful APIs)
│       ├── core/         # 配置(Pydantic BaseSettings)与数据库连接池
│       ├── models/       # SQLAlchemy 2.0 异步 ORM 模型
│       ├── schemas/      # Pydantic 校验模型
│       └── services/     # 核心业务逻辑 (画像聚合、推荐算法)
└── frontend/             # Vue 3 前端工程
```

## 5. 核心研发军规 (Vibe Coding Strict Rules)
当请求 AI 编写代码时，AI 必须将以下规则视为最高优先级指令：

1. **状态单向流转（防死锁）**：针对 `raw_data` 表的流转操作，必须是单向的（0 -> 1 -> 2）。不同脚本（爬虫/Spark/FinBERT）只能查询符合自己处理状态的记录，处理完毕后通过 `UPDATE` 推进状态并修改 `update_time`。
2. **异步 ORM 强制规范 (SQLAlchemy 2.0)**：
   - **绝对禁止**使用 1.x 语法（如 `session.query(Model)` 或 `Model.query.all()`）。
   - **必须使用** 2.0 标准异步语法：`stmt = select(Model).where(...)`，并使用 `result = await session.execute(stmt)` 和 `result.scalars().all()`。
   - 数据库引擎必须使用 `async_sessionmaker` 和 `create_async_engine`。
3. **Pydantic V2 契约**：所有跨层数据传递（特别是API的Request/Response）必须通过 Pydantic V2 模型（`BaseModel`）进行校验，利用 `model_dump()` 替代旧版的 `dict()`。
4. **全局异常防线**：FastAPI 后端必须设计全局异常捕获中间件，任何报错（包括内部计算崩溃或数据库连接失败）都必须被包装为标准的 JSON 响应结构返回给前端：`{"code": error_code, "data": null, "msg": "error details"}`。
5. **增量交付原则**：输出代码时，仅输出需要新增或修改的具体函数/代码块，并用注释清晰标注插入位置，拒绝大段覆盖式输出。

## 6. 当前冲刺目标 (Sprint Goal)
* **阶段**：Phase 1 (数据底座构建)
* **下一步优先操作**：在 `backend/app/models/` 中建立基于 SQLAlchemy 2.0 的异步 ORM 数据表映射代码；配置 `backend/app/core/` 下的异步数据库连接池。
```

