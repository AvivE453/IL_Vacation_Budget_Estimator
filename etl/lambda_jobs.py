# AWS Lambda's entry point for the scheduled jobs (ROADMAP 4.2). Each
# EventBridge schedule invokes it with an event naming one job, e.g.
#   {"job": "flights", "shard": 0}
# and it runs that job's main(), the same one the command line runs.

from etl.backup import backup
from etl.collectors import flights_collector, hotels_collector
from etl.loaders import cleanup_old_flights, cleanup_old_hotels, cleanup_old_searches, refresh_exchange_rates

# A full flights run takes ~9 minutes, close to Lambda's 15-minute limit, so it
# runs as two shards of the collector's months (measured: ~6.5 and ~2.5 minutes;
# the nearer months have far more prices).
FLIGHT_SHARDS = ([0, 1, 2, 3], [4, 5, 6])

JOBS = {
    "flights": lambda event: flights_collector.main(FLIGHT_SHARDS[event["shard"]]),
    "hotels": lambda event: hotels_collector.main(
        event.get("max_searches", hotels_collector.DEFAULT_MAX_SEARCHES_PER_RUN)
    ),
    "exchange_rates": lambda event: refresh_exchange_rates.main(),
    "cleanup_flights": lambda event: cleanup_old_flights.main(),
    "cleanup_hotels": lambda event: cleanup_old_hotels.main(),
    "cleanup_searches": lambda event: cleanup_old_searches.main(),
    "backup": lambda event: backup.main(),
}


def handler(event, context):
    job = JOBS.get(event["job"])
    if job is None:
        raise ValueError(f"unknown job {event['job']!r}; known jobs: {', '.join(JOBS)}")
    # The collectors stop with SystemExit when a key is missing - a clean
    # message on the command line, but on Lambda it kills the runtime process,
    # and the invocation fails as Runtime.ExitError with the message lost.
    try:
        job(event)
    except SystemExit as exc:
        raise RuntimeError(f"{event['job']} stopped: {exc}") from exc
