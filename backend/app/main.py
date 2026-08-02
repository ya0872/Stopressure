"""FastAPI エントリポイント。

起動:
  cd backend
  uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .routers import atmosphere, auth_google, context, generate, plan, reflection, settings, usage

# 起動ディレクトリに依存しないよう backend/.env を絶対パスで読み込む。
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# フロントは別ポートで動くためCORSが必要。既定はモックアップとViteの開発サーバー。
# localhost と 127.0.0.1 は別オリジンとして扱われるため、両方を許可しておく
# （Windowsでは localhost が ::1 に解決されて繋がらないことがあり、その回避で
#   127.0.0.1 で開く場面があるため）
_DEFAULT_ORIGINS = (
    "http://localhost:8765,http://127.0.0.1:8765,"
    "http://localhost:5173,http://127.0.0.1:5173"
)
ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", _DEFAULT_ORIGINS).split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時にDBスキーマを用意する
    init_db()
    yield


app = FastAPI(
    title="低気圧のすゝめ API",
    description="Atmosphere Studio のローカルバックエンド",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(settings.router, prefix="/api/v1")
app.include_router(auth_google.router, prefix="/api/v1")
app.include_router(atmosphere.router, prefix="/api/v1")
app.include_router(plan.router, prefix="/api/v1")
app.include_router(context.router, prefix="/api/v1")
app.include_router(generate.router, prefix="/api/v1")
app.include_router(reflection.router, prefix="/api/v1")
app.include_router(usage.router, prefix="/api/v1")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    """疎通確認用。フロントから起動状態を判定するのに使う。"""
    return {"status": "ok"}
