"""Crawl API routes."""

from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

import config
from app.job_store import job_store
from app.schemas import CrawlRequest, CrawlStartResponse, JobDetailResponse, JobStatus
from app.services.crawler import crawler_service

router = APIRouter(tags=["crawl"])


@router.post(
    "/crawl/start",
    response_model=CrawlStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="提交抓取任务",
    description="异步抓取亚马逊图片，立即返回 job_id。",
)
def start_crawl(req: CrawlRequest, bg: BackgroundTasks) -> CrawlStartResponse:
    if req.domain not in config.AMAZON_DOMAINS:
        raise HTTPException(status_code=400, detail=f"不支持的域名: {req.domain}")

    job_id = uuid4().hex
    job_store.create(job_id)
    job_store.update(job_id, status=JobStatus.PENDING, progress=0, message="等待执行")

    bg.add_task(
        crawler_service.run,
        job_id=job_id,
        asins=req.asins,
        asin_file=req.asin_file,
        domain=req.domain,
        max_images=req.max_images,
        skip_existing=req.skip_existing,
    )
    return CrawlStartResponse(job_id=job_id)


@router.get(
    "/jobs/{job_id}",
    response_model=JobDetailResponse,
    summary="查询任务状态",
)
def get_job(job_id: str) -> JobDetailResponse:
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"job_id 不存在: {job_id}")
    return JobDetailResponse(**job)
