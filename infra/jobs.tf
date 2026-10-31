# The scheduled jobs: a second Lambda function from the same zip,
# entry point etl.lambda_jobs.handler, and the EventBridge schedules that invoke it.

locals {
  jobs_function_name = "vacation-budget-jobs"
  # The direct Neon URL and the SerpApi key, put there by hand.
  jobs_ssm_path = "/vacation-budget/jobs/"
}

resource "aws_cloudwatch_log_group" "jobs" {
  name              = "/aws/lambda/${local.jobs_function_name}"
  retention_in_days = 14
}

resource "aws_iam_role" "jobs" {
  name = "${local.jobs_function_name}-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Its own log group and its own parameters; not the API's (writing backups: backups.tf).
resource "aws_iam_role_policy" "jobs" {
  name = "logs-and-own-secrets"
  role = aws_iam_role.jobs.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.jobs.arn}:*"
      },
      {
        Effect   = "Allow"
        Action   = "ssm:GetParametersByPath"
        Resource = ["${local.ssm_arn}${trimsuffix(local.jobs_ssm_path, "/")}", "${local.ssm_arn}${local.jobs_ssm_path}*"]
      },
    ]
  })
}

resource "aws_lambda_function" "jobs" {
  function_name = local.jobs_function_name
  role          = aws_iam_role.jobs.arn
  runtime       = "python3.12"
  architectures = ["x86_64"]
  handler       = "etl.lambda_jobs.handler"
  filename      = "${path.module}/../build/lambda.zip"
  # Lambda's maximum. A flights shard takes 3-7 minutes; the rest, seconds.
  timeout = 900
  # The jobs wait on the network, not the CPU.
  memory_size = 512

  environment {
    variables = {
      SSM_PARAMETER_PATH = local.jobs_ssm_path
      BACKUP_BUCKET      = aws_s3_bucket.backups.bucket
    }
  }

  lifecycle {
    ignore_changes = [filename]
  }

  depends_on = [aws_iam_role_policy.jobs, aws_iam_role_policy.jobs_backups, aws_cloudwatch_log_group.jobs]
}

# The schedules invoke the function asynchronously, and by default Lambda then
# retries a failed run twice: at-least-once delivery. A second hotels run would
# spend SerpApi searches again, so a failure isn't retried: it's reported (4.7).
resource "aws_lambda_function_event_invoke_config" "jobs" {
  function_name          = aws_lambda_function.jobs.function_name
  maximum_retry_attempts = 0
}

output "jobs_function_name" {
  value = aws_lambda_function.jobs.function_name
}

# When each job runs, on Israel time. EventBridge cron fields: minutes, hours,
# day of month, month, day of week, year; one of the two "day" fields is "?".
locals {
  job_schedules = {
    # Measured 2026-10-26: ~6.5 minutes, then ~2.5. The second starts after the first is done.
    flights-months-0-3 = { cron = "cron(0 4 * * ? *)", input = { job = "flights", shard = 0 } }
    flights-months-4-6 = { cron = "cron(20 4 * * ? *)", input = { job = "flights", shard = 1 } }
    # The 2nd and the 16th, capped at 103 searches each (one per destination
    # today): 206 of the 250 monthly SerpApi searches. Any month-long quota
    # period holds exactly two runs. The cap holds the budget if destinations
    # are added: the oldest prices go first, so they'd just rotate.
    hotels         = { cron = "cron(0 5 2,16 * ? *)", input = { job = "hotels", max_searches = 103 } }
    exchange-rates = { cron = "cron(0 5 ? * SUN *)", input = { job = "exchange_rates" } }
    # Sundays, after that morning's collection.
    cleanup-flights  = { cron = "cron(10 5 ? * SUN *)", input = { job = "cleanup_flights" } }
    cleanup-hotels   = { cron = "cron(15 5 ? * SUN *)", input = { job = "cleanup_hotels" } }
    cleanup-searches = { cron = "cron(20 5 ? * SUN *)", input = { job = "cleanup_searches" } }
    # Nightly, after everything above (hotels ends by 05:15, the function's
    # timeout), so a night's new hotel prices are in that night's backup.
    backup = { cron = "cron(30 5 * * ? *)", input = { job = "backup" } }
  }
}

# The identity EventBridge Scheduler uses to invoke the function: only the
# scheduler service, only for this account, and only this one function.
resource "aws_iam_role" "scheduler" {
  name = "vacation-budget-scheduler-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id } }
    }]
  })
}

resource "aws_iam_role_policy" "scheduler" {
  name = "invoke-jobs"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.jobs.arn
    }]
  })
}

# One schedule per entry in job_schedules.
resource "aws_scheduler_schedule" "jobs" {
  for_each = local.job_schedules

  name                         = "vacation-budget-${each.key}"
  schedule_expression          = each.value.cron
  schedule_expression_timezone = "Asia/Jerusalem"

  # Run at the exact time, not anywhere within a window.
  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.jobs.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode(each.value.input)

    # Like the function's own setting: nothing runs twice. A run that never
    # happened shows up as missing data, which 4.7 alerts on.
    retry_policy {
      maximum_retry_attempts = 0
    }
  }
}
