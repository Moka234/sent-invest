# SentInvest

一个面向理财社群场景的**情感分析 + 风险画像 + 理财产品推荐**项目。

> 文档分工：`README.md` 用于快速了解项目与仓库结构；`项目启动说明书.md` 用于查看详细启动步骤、常见问题和排查说明。

核心链路：

```text
scraper 采集发言 -> pipeline 清洗/分析/画像 -> backend 提供接口 -> frontend 展示结果
```

---

## 技术栈

- 前端：Vue 3 + Vite + Element Plus + ECharts
- 后端：FastAPI + SQLAlchemy 2.0 Async + Pydantic v2
- 数据处理：PySpark + Transformers + Torch
- 数据采集：aiohttp + BeautifulSoup4
- 数据库：MySQL 8+

---

## 快速启动

### 1. 安装依赖

Python：

```bash
pip install -r requirements.txt
```

前端：

```bash
cd frontend
npm install
```

### 2. 配置环境变量

在项目根目录创建 `.env`：

```env
DATABASE_URL=mysql+aiomysql://用户名:密码@主机:端口/数据库名?charset=utf8mb4
```

### 3. 初始化数据库

```bash
python backend/app/core/init_db.py
python backend/scripts/seed_products.py
```

### 4. 启动服务

后端：

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

前端：

```bash
cd frontend
npm run dev
```

爬虫：

```bash
python scraper/main.py
```

调度：

```bash
python run_pipeline.py
```

---

## 仓库结构（简洁版）

```text
sent-invest/
├─ .env                      # 本地环境变量
├─ .gitignore                # 仓库忽略规则
├─ requirements.txt          # 全项目完整 Python 依赖
├─ run_pipeline.py           # 清洗/分析/画像调度入口
├─ README.md                 # 仓库首页说明
├─ 项目启动说明书.md          # 详细启动说明
├─ scraper/                  # 数据采集
├─ pipeline/                 # 清洗、情感分析、用户画像
├─ backend/                  # FastAPI 后端
├─ frontend/                 # Vue 前端
└─ logs/                     # 本地日志目录（不提交）
```

---

## 模块说明

- `scraper/`：抓取原始发言，写入 `raw_data`
- `pipeline/`：清洗文本、情感分析、生成 `risk_profile`
- `backend/`：提供大盘、走势、用户推荐等 API
- `frontend/`：展示全站情绪大盘和个人推荐中心

---

## 依赖文件说明

- `requirements.txt`：完整依赖，一次安装即可跑通项目
- `backend/requirements.txt`：后端专属依赖
- `scraper/requirements.txt`：爬虫专属依赖
- `pipeline/requirements.txt`：数据处理 / AI 专属依赖

---

## 详细文档

如果你需要更完整的说明，请看：

- `项目启动说明书.md`：详细启动步骤

---

## 当前推荐启动顺序

1. `python scraper/main.py`
2. `python run_pipeline.py`
3. 启动后端
4. 启动前端
