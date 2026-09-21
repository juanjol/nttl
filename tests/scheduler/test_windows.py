from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from nttl.scheduler.windows import (
    ScheduleConfig,
    ScheduleMode,
    current_or_next_window,
    window_for_night,
)

MADRID = ZoneInfo("Europe/Madrid")


def solar(**kwargs) -> ScheduleConfig:
    base = dict(
        mode=ScheduleMode.SOLAR,
        latitude=40.4168,
        longitude=-3.7038,
        timezone="Europe/Madrid",
        sun_depression_deg=12.0,
    )
    base.update(kwargs)
    return ScheduleConfig(**base)


def test_solar_window_starts_at_dusk_and_ends_at_dawn():
    window = window_for_night(solar(), date(2026, 7, 15))
    assert window.start.date() == date(2026, 7, 15)
    assert window.end.date() == date(2026, 7, 16)
    assert window.start.hour >= 21
    assert window.end.hour <= 6
    assert window.night == date(2026, 7, 15)


def test_winter_nights_are_longer_than_summer_nights():
    summer = window_for_night(solar(), date(2026, 7, 15))
    winter = window_for_night(solar(), date(2026, 1, 15))
    assert winter.duration_s > summer.duration_s


def test_depression_extends_the_window():
    civil = window_for_night(solar(sun_depression_deg=6.0), date(2026, 3, 20))
    astronomical = window_for_night(solar(sun_depression_deg=18.0), date(2026, 3, 20))
    assert astronomical.start > civil.start
    assert astronomical.end < civil.end


def test_offsets_shift_the_window():
    base = window_for_night(solar(), date(2026, 3, 20))
    shifted = window_for_night(solar(start_offset_min=-30, end_offset_min=15), date(2026, 3, 20))
    assert (base.start - shifted.start).total_seconds() == pytest.approx(1800)
    assert (shifted.end - base.end).total_seconds() == pytest.approx(900)


def test_fixed_mode_crosses_midnight():
    config = ScheduleConfig(
        mode=ScheduleMode.FIXED,
        fixed_start="22:15",
        fixed_end="05:45",
        timezone="Europe/Madrid",
    )
    window = window_for_night(config, date(2026, 2, 1))
    assert window.start == datetime(2026, 2, 1, 22, 15, tzinfo=MADRID)
    assert window.end == datetime(2026, 2, 2, 5, 45, tzinfo=MADRID)


def test_fixed_mode_same_day_window():
    config = ScheduleConfig(
        mode=ScheduleMode.FIXED, fixed_start="01:00", fixed_end="04:00", timezone="Europe/Madrid"
    )
    window = window_for_night(config, date(2026, 2, 1))
    assert window.start.date() == window.end.date() == date(2026, 2, 1)


def test_window_contains_respects_bounds():
    window = window_for_night(solar(), date(2026, 7, 15))
    assert window.contains(window.start)
    assert window.contains(window.start + (window.end - window.start) / 2)
    assert not window.contains(window.end)


def test_current_window_is_returned_while_active():
    config = solar()
    window = window_for_night(config, date(2026, 7, 15))
    inside = window.start + (window.end - window.start) / 2
    assert current_or_next_window(config, inside) == window


def test_next_window_is_returned_during_daytime():
    config = solar()
    noon = datetime(2026, 7, 15, 12, 0, tzinfo=MADRID)
    window = current_or_next_window(config, noon)
    assert window.night == date(2026, 7, 15)
    assert window.start > noon


def test_window_from_previous_night_is_detected_before_dawn():
    config = solar()
    early = datetime(2026, 7, 16, 2, 0, tzinfo=MADRID)
    window = current_or_next_window(config, early)
    assert window.night == date(2026, 7, 15)
    assert window.contains(early)


def test_polar_day_without_darkness_raises():
    config = solar(latitude=78.2, longitude=15.6, timezone="UTC")
    with pytest.raises(ValueError):
        window_for_night(config, date(2026, 6, 21))


def test_naive_reference_is_localized():
    config = solar()
    window = current_or_next_window(config, datetime(2026, 7, 15, 12, 0))
    assert window.night == date(2026, 7, 15)
