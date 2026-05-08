"""FastAPI server entrypoint for async crawl jobs."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.crawl import router as crawl_router

app = FastAPI(
    title="Amazon Image Crawler API",
    description="异步提交图片抓取任务并查询执行状态",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(crawl_router, prefix="/api")


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok"}
