from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from enum import StrEnum
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import dawn, dusk
from pydantic import BaseModel, Field


class ScheduleMode(StrEnum):
    SOLAR = "solar"
    FIXED = "fixed"


class ScheduleConfig(BaseModel):
    enabled: bool = False
    mode: ScheduleMode = ScheduleMode.SOLAR
    latitude: float = Field(default=0.0, ge=-90.0, le=90.0)
    longitude: float = Field(default=0.0, ge=-180.0, le=180.0)
    elevation_m: float = 0.0
    timezone: str | None = None
    sun_depression_deg: float = Field(default=12.0, ge=0.0, le=30.0)
    start_offset_min: int = 0
    end_offset_min: int = 0
    fixed_start: str = "21:00"
    fixed_end: str = "05:00"
    compile_at_end: bool = True
    session_name_template: str = "night_{night}"


@dataclass(frozen=True, slots=True)
class Window:
    night: date
    start: datetime
    end: datetime

    @property
    def duration_s(self) -> float:
        return (self.end - self.start).total_seconds()

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment < self.end

    def session_name(self, template: str) -> str:
        return template.format(night=self.night.isoformat(), date=self.night.isoformat())


def zone_for(config: ScheduleConfig) -> tzinfo:
    if config.timezone:
        return ZoneInfo(config.timezone)
    local = datetime.now().astimezone().tzinfo
    return local if local is not None else UTC


def _parse_clock(value: str) -> time:
    hours, _, minutes = value.partition(":")
    return time(hour=int(hours), minute=int(minutes or 0))


def window_for_night(config: ScheduleConfig, night: date) -> Window:
    zone = zone_for(config)
    if config.mode is ScheduleMode.FIXED:
        start_time = _parse_clock(config.fixed_start)
        end_time = _parse_clock(config.fixed_end)
        start = datetime.combine(night, start_time, tzinfo=zone)
        end_day = night if end_time > start_time else night + timedelta(days=1)
        end = datetime.combine(end_day, end_time, tzinfo=zone)
    else:
        location = LocationInfo(
            name="nttl",
            region="",
            timezone=config.timezone or "UTC",
            latitude=config.latitude,
            longitude=config.longitude,
        )
        observer = location.observer
        observer.elevation = config.elevation_m
        try:
            start = dusk(observer, night, depression=config.sun_depression_deg).astimezone(zone)
            end = dawn(
                observer, night + timedelta(days=1), depression=config.sun_depression_deg
            ).astimezone(zone)
        except ValueError as exc:
            raise ValueError(f"no twilight window for {night} at this location: {exc}") from exc

    start += timedelta(minutes=config.start_offset_min)
    end += timedelta(minutes=config.end_offset_min)
    if end <= start:
        raise ValueError(f"empty capture window for {night}")
    return Window(night=night, start=start, end=end)


def current_or_next_window(config: ScheduleConfig, moment: datetime) -> Window:
    zone = zone_for(config)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=zone)
    local = moment.astimezone(zone)
    for offset in (-1, 0, 1):
        candidate = window_for_night(config, local.date() + timedelta(days=offset))
        if candidate.contains(local) or candidate.start > local:
            return candidate
    return window_for_night(config, local.date() + timedelta(days=2))
