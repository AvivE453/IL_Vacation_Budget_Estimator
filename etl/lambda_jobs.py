# AWS Lambda's entry point for the scheduled jobs. Each
# EventBridge schedule invokes it with an event naming one job, e.g.
#   {"job": "flights", "shard": 0}
# and it runs that job's main(), the same one the command line runs.

import json
import time

from etl.backup import backup
from etl.collectors import flights_collector, hotels_collector
from etl.loaders import cleanup_old_flights, cleanup_old_hotels, cleanup_old_searches, refresh_exchange_rates

# A full flights run takes ~9 minutes, close to Lambda's 15-minute limit, so it
# runs as two shards of the collector's months (measured: ~6.5 and ~2.5 minutes;
# the nearer months have far more prices).
FLIGHT_SHARDS = ([0, 1, 2, 3], [4, 5, 6])

# The CloudWatch namespace of the jobs' metrics; infra/alarms.tf's alarms read them.
METRICS_NAMESPACE = "VacationBudget"


# A job returns the numbers its alarms (infra/alarms.tf) watch, or nothing.
def run_flights(event):
    counts = flights_collector.main(FLIGHT_SHARDS[event["shard"]])
    return {"FlightsInserted": counts["inserted"]}


def run_hotels(event):
    counts = hotels_collector.main(event.get("max_searches", hotels_collector.DEFAULT_MAX_SEARCHES_PER_RUN))
    return {"HotelsUpdated": counts["updated"]}


def run_backup(event):
    # main() raises if any table fails, so getting here means all of them are in S3.
    backup.main()
    return {"BackupsCompleted": 1}


JOBS = {
    "flights": run_flights,
    "hotels": run_hotels,
    "exchange_rates": lambda event: refresh_exchange_rates.main(),
    "cleanup_flights": lambda event: cleanup_old_flights.main(),
    "cleanup_hotels": lambda event: cleanup_old_hotels.main(),
    "cleanup_searches": lambda event: cleanup_old_searches.main(),
    "backup": run_backup,
}


# One log line in CloudWatch's Embedded Metric Format: CloudWatch reads the
# "_aws" block and records each named value as a metric, with the job as its
# dimension (an alarm matches both). No API call, so no permission beyond
# writing logs.
def print_metrics(job, metrics):
    print(json.dumps({
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": METRICS_NAMESPACE,
                "Dimensions": [["Job"]],
                "Metrics": [{"Name": name, "Unit": "Count"} for name in metrics],
            }],
        },
        "Job": job,
        **metrics,
    }))


def handler(event, context):
    job = JOBS.get(event["job"])
    if job is None:
        raise ValueError(f"unknown job {event['job']!r}; known jobs: {', '.join(JOBS)}")
    # The collectors stop with SystemExit when a key is missing - a clean
    # message on the command line, but on Lambda it kills the runtime process,
    # and the invocation fails as Runtime.ExitError with the message lost.
    try:
        metrics = job(event)
    except SystemExit as exc:
        raise RuntimeError(f"{event['job']} stopped: {exc}") from exc
    if metrics:
        print_metrics(event["job"], metrics)
