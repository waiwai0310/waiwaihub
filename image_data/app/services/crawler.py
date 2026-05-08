"""Crawler service used by API background tasks."""

import logging
from pathlib import Path
from typing import List, Optional

import config
from app.job_store import job_store
from app.schemas import JobStatus
from database import DatabaseManager
from image_downloader import AmazonImageDownloader
from request_manager import RequestManager

logger = logging.getLogger(__name__)


class CrawlerService:
    """Wrap crawler execution for asynchronous API jobs."""

    def _read_asins_from_file(self, filepath: str) -> List[str]:
        path = Path(filepath)
        if not path.is_absolute():
            path = config.BASE_DIR / filepath

        if not path.exists():
            raise FileNotFoundError(f"ASIN 文件不存在: {path}")

        with open(path, "r", encoding="utf-8") as file:
            asins = [line.strip() for line in file if line.strip()]

        if not asins:
            raise ValueError("ASIN 文件为空")
        return asins

    def run(
        self,
        job_id: str,
        asins: Optional[List[str]] = None,
        asin_file: Optional[str] = None,
        domain: str = "us",
        max_images: int = config.MAX_IMAGES_PER_PRODUCT,
        skip_existing: bool = True,
    ) -> None:
        request_manager = None
        try:
            job_store.update(job_id, status=JobStatus.RUNNING, progress=10, message="初始化组件...")

            db_manager = DatabaseManager()
            request_manager = RequestManager(db_manager)
            downloader = AmazonImageDownloader(request_manager, db_manager)

            crawl_asins = asins or []
            if not crawl_asins and asin_file:
                job_store.update(job_id, status=JobStatus.RUNNING, progress=20, message="读取 ASIN 文件...")
                crawl_asins = self._read_asins_from_file(asin_file)

            if not crawl_asins:
                raise ValueError("未提供有效 ASIN")

            job_store.update(
                job_id,
                status=JobStatus.RUNNING,
                progress=40,
                message=f"开始抓取，共 {len(crawl_asins)} 个 ASIN",
            )
            all_stats = downloader.batch_download(
                asin_list=crawl_asins,
                domain=domain,
                max_images_per_product=max_images,
                skip_existing=skip_existing,
            )

            summary = {
                "total_products": len(crawl_asins),
                "total_images": sum(item["total"] for item in all_stats),
                "success": sum(item["success"] for item in all_stats),
                "failed": sum(item["failed"] for item in all_stats),
                "skipped": sum(item["skipped"] for item in all_stats),
                "skip_existing": skip_existing,
            }
            job_store.update(
                job_id,
                status=JobStatus.DONE,
                progress=100,
                message="抓取完成",
                result=summary,
            )
        except Exception as exc:
            logger.exception("任务失败: %s", job_id)
            job_store.update(
                job_id,
                status=JobStatus.FAILED,
                progress=100,
                message="抓取失败",
                error=str(exc),
            )
        finally:
            if request_manager is not None:
                request_manager.close()


crawler_service = CrawlerService()
