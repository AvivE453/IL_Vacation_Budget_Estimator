# Monitoring: CloudWatch alarms on the jobs' and the API's
# metrics, sent by email through SNS.

# The repository is public, so the address isn't in it: its value is in the
# gitignored infra/terraform.tfvars, which Terraform reads on its own.
variable "alert_email" {
  description = "Where the alarms' emails go"
  type        = string
}

locals {
  # Where the jobs' own metrics are: METRICS_NAMESPACE in etl/lambda_jobs.py.
  metrics_namespace = "VacationBudget"
}

# Every alarm publishes to this topic, and SNS emails each message to its
# subscribers. Not encrypted with KMS: CloudWatch can't publish to a topic
# under the AWS-managed aws/sns key, and an own key costs $1 a month.
resource "aws_sns_topic" "alerts" {
  name = "vacation-budget-alerts"
}

# Created as "pending confirmation": SNS emails a link, and nothing is
# delivered until it's clicked.
resource "aws_sns_topic_subscription" "alert_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Lambda counts every invocation that raised or timed out in Errors on its
# own. The collectors swallow request errors, so a run that fetched nothing
# isn't an error here: the flights and hotels alarms below catch that.
resource "aws_cloudwatch_metric_alarm" "job_failed" {
  alarm_name        = "vacation-budget-job-failed"
  alarm_description = "A scheduled job (flights, hotels, backup, exchange rates or a cleanup) failed. Its traceback is in the log group /aws/lambda/vacation-budget-jobs."

  namespace   = "AWS/Lambda"
  metric_name = "Errors"
  dimensions  = { FunctionName = aws_lambda_function.jobs.function_name }
  statistic   = "Sum"
  period      = 300

  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  # Lambda sends no Errors datapoint while nothing runs: that's not a failure.
  treat_missing_data = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
}

# API Gateway's count of 5xx responses, not the API function's Errors: when
# the database fails, FastAPI catches the exception and answers 500, so for
# Lambda the invocation succeeded. 4.3's dead-connection 500 is in this metric.
resource "aws_cloudwatch_metric_alarm" "api_errors" {
  alarm_name        = "vacation-budget-api-5xx"
  alarm_description = "The API answered with a 5xx error. The traceback is in the log group /aws/lambda/vacation-budget-api; a database error usually means Neon or the DB_URL in SSM."

  namespace   = "AWS/ApiGateway"
  metric_name = "5xx"
  dimensions  = { ApiId = aws_apigatewayv2_api.api.id }
  statistic   = "Sum"
  period      = 300

  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  # No requests, no datapoint: a quiet site isn't an error.
  treat_missing_data = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
}

# A flights run that inserted nothing. It isn't an error to Lambda: a revoked
# token fails every request, and the collector counts them and finishes. It
# can also happen with nothing broken, if no price changed (measured runs
# insert 90-2,400), so the email names both causes.
resource "aws_cloudwatch_metric_alarm" "flights_inserted_nothing" {
  alarm_name        = "vacation-budget-flights-inserted-nothing"
  alarm_description = "A flights run inserted 0 rows. In its summary line (log group /aws/lambda/vacation-budget-jobs): many request errors mean the Travelpayouts token or API failed; 0 request errors mean Travelpayouts returned no new prices."

  namespace   = local.metrics_namespace
  metric_name = "FlightsInserted"
  dimensions  = { Job = "flights" }
  # Each run is one datapoint. The shards end ~17 minutes apart, so they're
  # in different windows; Minimum still catches a 0 if two runs share one.
  statistic = "Minimum"
  period    = 300

  evaluation_periods  = 1
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  # No run in a window is normal; a run that never happened is the
  # "no flights run" alarm's job.
  treat_missing_data = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
}

# No flights run reported at all: the schedule didn't fire, the function
# couldn't start, or every run crashed. The July 2026 laptop cron failed this
# way, silently. Hourly windows, and the alarm fires only when every one of
# the last 25 is empty: missing data counts as breaching, and SampleCount is
# at least 1 in any window a run reported in, whatever it inserted.
resource "aws_cloudwatch_metric_alarm" "no_flights_run" {
  alarm_name        = "vacation-budget-no-flights-run"
  alarm_description = "No flights run has reported in 25 hours. Check the flights schedules (EventBridge Scheduler) and the log group /aws/lambda/vacation-budget-jobs. An OK email follows once a run reports again."

  namespace   = local.metrics_namespace
  metric_name = "FlightsInserted"
  dimensions  = { Job = "flights" }
  statistic   = "SampleCount"
  period      = 3600

  # 25, not 24: the schedules are on Israel time, so the night the clocks go
  # back the runs are 25 hours apart.
  evaluation_periods  = 25
  datapoints_to_alarm = 25
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  treat_missing_data  = "breaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  # Here OK does mean fixed: a run reported again.
  ok_actions = [aws_sns_topic.alerts.arn]
}

# No backup completed: the nightly backup failed (the job-failed alarm fires
# too) or never ran. Built like no_flights_run: run_backup reports
# BackupsCompleted only after all nine tables are in S3.
resource "aws_cloudwatch_metric_alarm" "no_backup" {
  alarm_name        = "vacation-budget-no-backup"
  alarm_description = "No backup has completed in 25 hours. Check the backup schedule and the log group /aws/lambda/vacation-budget-jobs. An OK email follows once a backup completes again."

  namespace   = local.metrics_namespace
  metric_name = "BackupsCompleted"
  dimensions  = { Job = "backup" }
  statistic   = "SampleCount"
  period      = 3600

  # 25, not 24, for the night the clocks go back (see no_flights_run).
  evaluation_periods  = 25
  datapoints_to_alarm = 25
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  treat_missing_data  = "breaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# A hotels run that updated no destination: like flights_inserted_nothing,
# it finishes without an error when every SerpApi search failed. Runs are
# two weeks apart, longer than an alarm can look back, so a hotels run that
# never happened isn't caught here (no_flights_run covers a broken scheduler).
resource "aws_cloudwatch_metric_alarm" "hotels_updated_nothing" {
  alarm_name        = "vacation-budget-hotels-updated-nothing"
  alarm_description = "A hotels run updated 0 destinations. In its summary line (log group /aws/lambda/vacation-budget-jobs): request errors mean the SerpApi key or quota failed; \"no priced results\" for every city means SerpApi returned no prices."

  namespace   = local.metrics_namespace
  metric_name = "HotelsUpdated"
  dimensions  = { Job = "hotels" }
  statistic   = "Minimum"
  period      = 300

  evaluation_periods  = 1
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
}
