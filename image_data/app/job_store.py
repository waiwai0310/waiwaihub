"""In-memory job store with thread safety."""

from datetime import datetime
from threading import Lock
from typing import Any, Dict, Optional

from app.schemas import JobStatus


class JobStore:
    """Store crawl jobs in memory."""

    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()

    def create(self, job_id: str) -> None:
        now = datetime.utcnow().isoformat()
        with self._lock:
            self._data[job_id] = {
                "job_id": job_id,
                "status": JobStatus.PENDING,
                "progress": 0,
                "message": "任务已创建",
                "error": None,
                "result": None,
                "created_at": now,
                "updated_at": now,
            }

    def update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            if job_id not in self._data:
                return
            self._data[job_id].update(fields)
            self._data[job_id]["updated_at"] = datetime.utcnow().isoformat()

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._data.get(job_id)
            return dict(row) if row else None


job_store = JobStore()
