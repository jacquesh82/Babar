"""Tests unitaires du parseur/évaluateur cron (purs)."""

from __future__ import annotations

from datetime import datetime

import pytest

from consolidation.cron import matches, next_run, parse_cron, seconds_until_next


def test_parse_and_match_daily_3am():
    cron = parse_cron("0 3 * * *")
    assert matches(datetime(2026, 7, 2, 3, 0), cron)
    assert not matches(datetime(2026, 7, 2, 3, 1), cron)
    assert not matches(datetime(2026, 7, 2, 4, 0), cron)


def test_step_and_range_fields():
    cron = parse_cron("*/15 9-17 * * *")
    assert matches(datetime(2026, 7, 2, 9, 0), cron)
    assert matches(datetime(2026, 7, 2, 17, 45), cron)
    assert not matches(datetime(2026, 7, 2, 8, 0), cron)
    assert not matches(datetime(2026, 7, 2, 12, 10), cron)


def test_day_of_week():
    # Cron dimanche=0 ; le 2026-07-05 est un dimanche.
    cron = parse_cron("0 0 * * 0")
    assert matches(datetime(2026, 7, 5, 0, 0), cron)
    assert not matches(datetime(2026, 7, 6, 0, 0), cron)  # lundi


def test_next_run_is_strictly_after():
    cron = parse_cron("0 3 * * *")
    nxt = next_run(datetime(2026, 7, 2, 3, 0, 30), cron)
    assert nxt == datetime(2026, 7, 3, 3, 0)


def test_seconds_until_next_non_negative():
    cron = parse_cron("*/5 * * * *")
    assert seconds_until_next(datetime(2026, 7, 2, 3, 2, 0), cron) == pytest.approx(180.0)


@pytest.mark.parametrize("expr", ["", "1 2 3", "60 0 * * *", "0 0 0 * *", "* * * * 8"])
def test_invalid_expressions_raise(expr):
    with pytest.raises(ValueError):
        parse_cron(expr)
