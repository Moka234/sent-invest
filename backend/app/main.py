from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router


app = FastAPI(
    title="SentInvest Backend API",
    version="1.0.0",
)

# 允许所有跨域，便于 Vue3 本地开发联调
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def health() -> dict[str, str]:
    return {"msg": "SentInvest backend is running"}


app.include_router(api_router)
