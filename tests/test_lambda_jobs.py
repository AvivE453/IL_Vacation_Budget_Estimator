# etl/lambda_jobs.py's dispatcher: an event picks a job and passes its
# arguments through. Every job's main() is replaced, so nothing here reaches
# an outside API or the database.

import datetime

import pytest

from etl import lambda_jobs
from etl.collectors import flights_collector, hotels_collector


@pytest.fixture()
def calls(monkeypatch):
    seen = []
    monkeypatch.setattr(flights_collector, "main", lambda months: seen.append(("flights", months)))
    monkeypatch.setattr(hotels_collector, "main", lambda max_searches: seen.append(("hotels", max_searches)))
    return seen


# Together the shards must ask for exactly what one full run asks for: no
# month missed, none twice - also after MONTH_OFFSETS changes.
def test_flight_shards_add_up_to_a_full_run():
    today = datetime.date(2026, 11, 20)

    pairs = [flights_collector.target_month_pairs(today, shard) for shard in lambda_jobs.FLIGHT_SHARDS]

    assert sum(pairs, []) == flights_collector.target_month_pairs(today)


def test_flights_job_collects_its_shards_months(calls):
    lambda_jobs.handler({"job": "flights", "shard": 1}, None)

    assert calls == [("flights", [4, 5, 6])]


@pytest.mark.parametrize("event", [{"job": "flights"}, {"job": "flights", "shard": 2}])
def test_flights_job_without_a_valid_shard_fails(calls, event):
    with pytest.raises((KeyError, IndexError)):
        lambda_jobs.handler(event, None)

    assert calls == []


def test_hotels_job_passes_its_search_cap(calls):
    lambda_jobs.handler({"job": "hotels", "max_searches": 1}, None)

    assert calls == [("hotels", 1)]


def test_unknown_job_fails(calls):
    with pytest.raises(ValueError, match="unknown job 'flight'"):
        lambda_jobs.handler({"job": "flight"}, None)

    assert calls == []


def test_a_collector_that_exits_fails_with_its_message(monkeypatch):
    def missing_token(months):
        raise SystemExit("TRAVELPAYOUTS_TOKEN is not set")

    monkeypatch.setattr(flights_collector, "main", missing_token)

    with pytest.raises(RuntimeError, match="flights stopped: TRAVELPAYOUTS_TOKEN is not set"):
        lambda_jobs.handler({"job": "flights", "shard": 0}, None)
