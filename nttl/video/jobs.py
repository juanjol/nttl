from __future__ import annotations

import queue
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

ProgressReporter = Callable[[int, int], None]
JobWork = Callable[[ProgressReporter], Any]


class JobState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    id: str
    name: str
    state: JobState = JobState.PENDING
    progress: float = 0.0
    frames_done: int = 0
    frames_total: int = 0
    result: Any = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "state": str(self.state),
            "progress": self.progress,
            "frames_done": self.frames_done,
            "frames_total": self.frames_total,
            "result": str(self.result) if self.result is not None else None,
            "error": self.error,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


class JobQueue:
    """Single worker queue so encoding never competes with capture."""

    def __init__(self, on_change: Callable[[Job], None] | None = None) -> None:
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._queue: queue.Queue[tuple[str, JobWork] | None] = queue.Queue()
        self._lock = threading.Lock()
        self._on_change = on_change
        self._worker = threading.Thread(target=self._loop, name="nttl-jobs", daemon=True)
        self._worker.start()

    def submit(self, name: str, work: JobWork) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], name=name)
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
        self._queue.put((job.id, work))
        self._notify(job)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return [self._jobs[job_id] for job_id in reversed(self._order)]

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state is not JobState.PENDING:
                return False
            job.state = JobState.CANCELLED
            job.finished_at = datetime.now(UTC).isoformat()
        self._notify(job)
        return True

    def shutdown(self, *, timeout: float = 5.0) -> None:
        self._queue.put(None)
        self._worker.join(timeout=timeout)

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            job_id, work = item
            job = self.get(job_id)
            if job is None or job.state is JobState.CANCELLED:
                continue
            job.state = JobState.RUNNING
            self._notify(job)

            def report(done: int, total: int, job: Job = job) -> None:
                job.frames_done = done
                job.frames_total = total
                job.progress = done / total if total else 0.0
                self._notify(job)

            try:
                job.result = work(report)
                job.state = JobState.FINISHED
                job.progress = 1.0
            except Exception as exc:  # surfaced through the job record
                job.state = JobState.FAILED
                job.error = str(exc)
            job.finished_at = datetime.now(UTC).isoformat()
            self._notify(job)

    def _notify(self, job: Job) -> None:
        if self._on_change is not None:
            self._on_change(job)
