"""通天晓业务层入口

启动（在 server/ 目录下）:
    uvicorn app.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .routers import admin, auth, reports, tasks

app = FastAPI(title="通天晓业务层", version="0.1.0")

# 内网实验环境：放开 CORS，生产如需收紧再改
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(reports.router)
app.include_router(admin.router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "tongtianxiao-business"}
