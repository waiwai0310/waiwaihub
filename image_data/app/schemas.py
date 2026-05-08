"""API request/response schemas."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class JobStatus(str, Enum):
    """Job lifecycle states."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class CrawlRequest(BaseModel):
    """Start crawl request payload."""

    asins: Optional[List[str]] = Field(
        default=None,
        description="ASIN 列表，传入时优先使用此字段",
        examples=[["B08N5WRWNW", "B0FVFGV3B7"]],
    )
    asin_file: Optional[str] = Field(
        default=None,
        description="ASIN 文件路径，每行一个 ASIN",
        examples=["asin_list_example.txt"],
    )
    domain: str = Field(default="us", description="Amazon 域名（us/uk/jp/de/fr）")
    max_images: int = Field(default=9, ge=1, le=50, description="每个产品最大下载图片数")
    skip_existing: bool = Field(default=True, description="是否跳过已下载图片")

    @model_validator(mode="after")
    def validate_source(self) -> "CrawlRequest":
        if not self.asins and not self.asin_file:
            raise ValueError("`asins` 和 `asin_file` 至少提供一个")
        return self


class CrawlStartResponse(BaseModel):
    """Start job response."""

    job_id: str


class JobDetailResponse(BaseModel):
    """Job detail response."""

    job_id: str
    status: JobStatus
    progress: int = 0
    message: str = ""
    error: Optional[str] = None
    result: Optional[dict] = None
