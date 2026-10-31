# etl/lambda_jobs.py's dispatcher: an event picks a job and passes its
# arguments through. Every job's main() is replaced, so nothing here reaches
# an outside API or the database.

import datetime
import json
import re
from pathlib import Path

import pytest

from etl import lambda_jobs
from etl.backup import backup
from etl.collectors import flights_collector, hotels_collector


@pytest.fixture()
def calls(monkeypatch):
    seen = []

    def flights(months):
        seen.append(("flights", months))
        return {"inserted": 1330, "skipped_no_offer": 231, "skipped_no_search_date": 0, "errors": 2,
                "hit_results_limit": 0}

    def hotels(max_searches):
        seen.append(("hotels", max_searches))
        return {"updated": 100, "skipped_no_results": 3, "errors": 0}

    monkeypatch.setattr(flights_collector, "main", flights)
    monkeypatch.setattr(hotels_collector, "main", hotels)
    monkeypatch.setattr(backup, "main", lambda: seen.append(("backup",)))
    return seen


def printed_metrics(capsys):
    return json.loads(capsys.readouterr().out.splitlines()[-1])


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


# CloudWatch ignores a malformed EMF line without any error, and the alarm
# then sees missing data: so the structure is pinned down here.
def test_flights_job_prints_its_metrics_in_embedded_metric_format(calls, capsys):
    lambda_jobs.handler({"job": "flights", "shard": 0}, None)

    line = printed_metrics(capsys)
    [directive] = line["_aws"]["CloudWatchMetrics"]
    assert directive["Namespace"] == lambda_jobs.METRICS_NAMESPACE
    assert directive["Dimensions"] == [["Job"]]
    assert directive["Metrics"] == [{"Name": "FlightsInserted", "Unit": "Count"}]
    assert isinstance(line["_aws"]["Timestamp"], int)
    assert (line["Job"], line["FlightsInserted"]) == ("flights", 1330)


@pytest.mark.parametrize("event, expected", [
    ({"job": "hotels", "max_searches": 103}, {"HotelsUpdated": 100}),
    ({"job": "backup"}, {"BackupsCompleted": 1}),
])
def test_hotels_and_backup_jobs_print_their_metrics(calls, capsys, event, expected):
    lambda_jobs.handler(event, None)

    line = printed_metrics(capsys)
    assert [m["Name"] for m in line["_aws"]["CloudWatchMetrics"][0]["Metrics"]] == list(expected)
    assert {name: line[name] for name in expected} == expected
    assert line["Job"] == event["job"]


# alarms.tf names the jobs' metrics as plain strings. An alarm on a name no
# job prints sees only missing data, with no error anywhere, so both sides are
# compared here: every printed metric has an alarm, and every alarm a metric.
def test_the_alarms_watch_exactly_the_metrics_the_jobs_print(calls, capsys):
    alarms_tf = (Path(__file__).parent.parent / "infra" / "alarms.tf").read_text()
    printed = set()
    for event in ({"job": "flights", "shard": 0}, {"job": "hotels"}, {"job": "backup"}):
        lambda_jobs.handler(event, None)
        line = printed_metrics(capsys)
        printed |= {(m["Name"], line["Job"]) for m in line["_aws"]["CloudWatchMetrics"][0]["Metrics"]}

    namespace = re.search(r'metrics_namespace\s*=\s*"(\w+)"', alarms_tf).group(1)
    watched = set(re.findall(
        r'namespace\s*=\s*local\.metrics_namespace\s+metric_name\s*=\s*"(\w+)"\s+'
        r'dimensions\s*=\s*\{\s*Job\s*=\s*"(\w+)"\s*\}',
        alarms_tf,
    ))

    assert namespace == lambda_jobs.METRICS_NAMESPACE
    assert watched == printed


def test_a_job_that_fails_prints_no_metrics(monkeypatch, capsys):
    def crash(months):
        raise RuntimeError("database unreachable")

    monkeypatch.setattr(flights_collector, "main", crash)

    with pytest.raises(RuntimeError):
        lambda_jobs.handler({"job": "flights", "shard": 0}, None)

    assert "_aws" not in capsys.readouterr().out


def test_a_collector_that_exits_fails_with_its_message(monkeypatch):
    def missing_token(months):
        raise SystemExit("TRAVELPAYOUTS_TOKEN is not set")

    monkeypatch.setattr(flights_collector, "main", missing_token)

    with pytest.raises(RuntimeError, match="flights stopped: TRAVELPAYOUTS_TOKEN is not set"):
        lambda_jobs.handler({"job": "flights", "shard": 0}, None)
