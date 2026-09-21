from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nttl.scheduler.runner import SchedulerRunner
from nttl.scheduler.windows import ScheduleConfig, ScheduleMode

MADRID = ZoneInfo("Europe/Madrid")


def config(**kwargs) -> ScheduleConfig:
    base = dict(
        enabled=True,
        mode=ScheduleMode.FIXED,
        fixed_start="22:00",
        fixed_end="05:00",
        timezone="Europe/Madrid",
    )
    base.update(kwargs)
    return ScheduleConfig(**base)


class Recorder:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.stopped = 0
        self.compiled: list[str] = []
        self.active = False

    def start(self, window):
        self.started.append(window.session_name("night_{night}"))
        self.active = True

    def stop(self):
        self.stopped += 1
        self.active = False

    def compile(self, window):
        self.compiled.append(window.night.isoformat())

    def is_active(self):
        return self.active


def runner_for(recorder, cfg, moment):
    clock = {"now": moment}
    runner = SchedulerRunner(
        cfg,
        start_session=recorder.start,
        stop_session=recorder.stop,
        compile_night=recorder.compile,
        is_session_active=recorder.is_active,
        now=lambda: clock["now"],
    )
    return runner, clock


def test_session_starts_when_window_opens():
    recorder = Recorder()
    runner, clock = runner_for(recorder, config(), datetime(2026, 2, 1, 21, 59, tzinfo=MADRID))
    runner.tick()
    assert recorder.started == []
    clock["now"] = datetime(2026, 2, 1, 22, 0, tzinfo=MADRID)
    runner.tick()
    assert recorder.started == ["night_2026-02-01"]


def test_session_is_not_started_twice():
    recorder = Recorder()
    runner, clock = runner_for(recorder, config(), datetime(2026, 2, 1, 22, 30, tzinfo=MADRID))
    runner.tick()
    clock["now"] += timedelta(hours=1)
    runner.tick()
    assert len(recorder.started) == 1


def test_session_stops_and_compiles_at_dawn():
    recorder = Recorder()
    runner, clock = runner_for(recorder, config(), datetime(2026, 2, 1, 23, 0, tzinfo=MADRID))
    runner.tick()
    clock["now"] = datetime(2026, 2, 2, 5, 1, tzinfo=MADRID)
    runner.tick()
    assert recorder.stopped == 1
    assert recorder.compiled == ["2026-02-01"]


def test_compile_can_be_disabled():
    recorder = Recorder()
    runner, clock = runner_for(
        recorder, config(compile_at_end=False), datetime(2026, 2, 1, 23, 0, tzinfo=MADRID)
    )
    runner.tick()
    clock["now"] = datetime(2026, 2, 2, 6, 0, tzinfo=MADRID)
    runner.tick()
    assert recorder.stopped == 1
    assert recorder.compiled == []


def test_consecutive_nights_each_get_a_session():
    recorder = Recorder()
    runner, clock = runner_for(recorder, config(), datetime(2026, 2, 1, 22, 5, tzinfo=MADRID))
    runner.tick()
    clock["now"] = datetime(2026, 2, 2, 5, 5, tzinfo=MADRID)
    runner.tick()
    clock["now"] = datetime(2026, 2, 2, 22, 5, tzinfo=MADRID)
    runner.tick()
    assert recorder.started == ["night_2026-02-01", "night_2026-02-02"]
    assert recorder.compiled == ["2026-02-01"]


def test_disabled_scheduler_does_nothing():
    recorder = Recorder()
    runner, _ = runner_for(
        recorder, config(enabled=False), datetime(2026, 2, 1, 23, 0, tzinfo=MADRID)
    )
    status = runner.tick()
    assert recorder.started == []
    assert status.enabled is False


def test_status_reports_next_transition():
    recorder = Recorder()
    runner, _ = runner_for(recorder, config(), datetime(2026, 2, 1, 12, 0, tzinfo=MADRID))
    status = runner.tick()
    assert status.in_window is False
    assert status.next_start is not None
    assert status.next_start.hour == 22
    assert status.seconds_to_next_start > 0


def test_status_reports_remaining_time_inside_window():
    recorder = Recorder()
    runner, _ = runner_for(recorder, config(), datetime(2026, 2, 1, 23, 0, tzinfo=MADRID))
    status = runner.tick()
    assert status.in_window is True
    assert status.seconds_to_end == 6 * 3600


def test_unreachable_window_is_reported_without_crashing():
    recorder = Recorder()
    runner, _ = runner_for(
        recorder,
        ScheduleConfig(
            enabled=True,
            mode=ScheduleMode.SOLAR,
            latitude=78.2,
            longitude=15.6,
            timezone="UTC",
        ),
        datetime(2026, 6, 21, 12, 0, tzinfo=ZoneInfo("UTC")),
    )
    status = runner.tick()
    assert status.error is not None
    assert recorder.started == []
