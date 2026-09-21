import time

from nttl.video.jobs import JobQueue, JobState


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_job_runs_and_reports_progress():
    queue = JobQueue()
    try:

        def work(report):
            report(1, 2)
            report(2, 2)
            return "done"

        job = queue.submit("compile", work)
        assert wait_for(lambda: queue.get(job.id).state is JobState.FINISHED)
        finished = queue.get(job.id)
        assert finished.progress == 1.0
        assert finished.result == "done"
        assert finished.error is None
    finally:
        queue.shutdown()


def test_failed_job_keeps_error_message():
    queue = JobQueue()
    try:

        def work(report):
            raise RuntimeError("encoder exploded")

        job = queue.submit("compile", work)
        assert wait_for(lambda: queue.get(job.id).state is JobState.FAILED)
        assert "encoder exploded" in (queue.get(job.id).error or "")
    finally:
        queue.shutdown()


def test_jobs_run_in_submission_order():
    queue = JobQueue()
    order = []
    try:
        for index in range(3):
            queue.submit(f"job{index}", lambda report, index=index: order.append(index))
        assert wait_for(lambda: len(order) == 3)
        assert order == [0, 1, 2]
    finally:
        queue.shutdown()


def test_pending_job_can_be_cancelled():
    queue = JobQueue()
    try:
        blocker = {"go": False}

        def slow(report):
            while not blocker["go"]:
                time.sleep(0.01)

        first = queue.submit("slow", slow)
        second = queue.submit("queued", lambda report: None)
        assert wait_for(lambda: queue.get(first.id).state is JobState.RUNNING)
        assert queue.cancel(second.id) is True
        assert queue.get(second.id).state is JobState.CANCELLED
        blocker["go"] = True
        assert wait_for(lambda: queue.get(first.id).state is JobState.FINISHED)
    finally:
        queue.shutdown()


def test_list_returns_newest_first():
    queue = JobQueue()
    try:
        queue.submit("a", lambda report: None)
        queue.submit("b", lambda report: None)
        assert wait_for(lambda: all(j.state is JobState.FINISHED for j in queue.list()))
        assert [job.name for job in queue.list()] == ["b", "a"]
    finally:
        queue.shutdown()


def test_unknown_job_is_none():
    queue = JobQueue()
    try:
        assert queue.get("missing") is None
        assert queue.cancel("missing") is False
    finally:
        queue.shutdown()
