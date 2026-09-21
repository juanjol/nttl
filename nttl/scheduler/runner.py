from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from threading import Event

from nttl.scheduler.windows import (
    ScheduleConfig,
    Window,
    current_or_next_window,
    zone_for,
)


@dataclass
class SchedulerStatus:
    enabled: bool
    in_window: bool = False
    night: str | None = None
    next_start: datetime | None = None
    next_end: datetime | None = None
    seconds_to_next_start: float = 0.0
    seconds_to_end: float = 0.0
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "in_window": self.in_window,
            "night": self.night,
            "next_start": self.next_start.isoformat() if self.next_start else None,
            "next_end": self.next_end.isoformat() if self.next_end else None,
            "seconds_to_next_start": self.seconds_to_next_start,
            "seconds_to_end": self.seconds_to_end,
            "error": self.error,
        }


class SchedulerRunner:
    def __init__(
        self,
        config: ScheduleConfig,
        *,
        start_session: Callable[[Window], None],
        stop_session: Callable[[], None],
        compile_night: Callable[[Window], None] | None = None,
        is_session_active: Callable[[], bool] | None = None,
        now: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        poll_interval_s: float = 30.0,
    ) -> None:
        self.config = config
        self._start_session = start_session
        self._stop_session = stop_session
        self._compile_night = compile_night
        self._is_active = is_session_active or (lambda: False)
        self._now = now or (lambda: datetime.now(zone_for(config)))
        self._sleep = sleep
        self._poll_interval_s = poll_interval_s
        self._stop = Event()
        self.active_window: Window | None = None
        self.status = SchedulerStatus(enabled=config.enabled)

    def request_stop(self) -> None:
        self._stop.set()

    def tick(self) -> SchedulerStatus:
        if not self.config.enabled:
            self.status = SchedulerStatus(enabled=False)
            return self.status

        moment = self._now()
        try:
            window = current_or_next_window(self.config, moment)
        except ValueError as exc:
            self.status = SchedulerStatus(enabled=True, error=str(exc))
            return self.status

        active = self.active_window
        if active is not None and not active.contains(moment):
            self._close_window(active)
            active = None

        if window.contains(moment) and active is None:
            self.active_window = window
            self._start_session(window)
            active = window

        self.status = SchedulerStatus(
            enabled=True,
            in_window=active is not None,
            night=(active or window).night.isoformat(),
            next_start=window.start,
            next_end=(active or window).end,
            seconds_to_next_start=max((window.start - moment).total_seconds(), 0.0),
            seconds_to_end=max(((active or window).end - moment).total_seconds(), 0.0),
        )
        return self.status

    def run(self) -> None:
        while not self._stop.is_set():
            self.tick()
            self._sleep(self._poll_interval_s)

    def _close_window(self, window: Window) -> None:
        self.active_window = None
        self._stop_session()
        if self.config.compile_at_end and self._compile_night is not None:
            self._compile_night(window)
