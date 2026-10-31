# The API: a Lambda function (api.lambda_handler.handler) behind an API Gateway
# HTTP API. This file starts with what the function needs before it exists: its
# log group and the role it runs as.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  api_function_name = "vacation-budget-api"
  # Where the API's secrets live in SSM, put there by hand.
  api_ssm_path = "/vacation-budget/api/"
  ssm_arn      = "arn:aws:ssm:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:parameter"
}

# Created here rather than by Lambda on first run, so the retention is set and
# the log group goes away with terraform destroy.
resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.api_function_name}"
  retention_in_days = 14
}

# The identity the function runs as. Only the Lambda service may take it on.
resource "aws_iam_role" "api" {
  name = "${local.api_function_name}-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Everything the role may do: write to its own log group, and read its own
# SSM parameters - nothing else. The SecureStrings are encrypted with the
# AWS-managed aws/ssm key, whose key policy already lets the account use it
# through SSM, so no KMS permission is needed.
resource "aws_iam_role_policy" "api" {
  name = "logs-and-own-secrets"
  role = aws_iam_role.api.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.api.arn}:*"
      },
      {
        Effect   = "Allow"
        Action   = "ssm:GetParametersByPath"
        Resource = ["${local.ssm_arn}${trimsuffix(local.api_ssm_path, "/")}", "${local.ssm_arn}${local.api_ssm_path}*"]
      },
    ]
  })
}

# Needs build/lambda.zip (scripts/build_lambda.sh) when it's first created.
# After that Terraform owns the function's settings and the deploy script
# ships its code, so a new zip alone never shows up as a Terraform change.
resource "aws_lambda_function" "api" {
  function_name = local.api_function_name
  role          = aws_iam_role.api.arn
  runtime       = "python3.12"
  architectures = ["x86_64"]
  handler       = "api.lambda_handler.handler"
  filename      = "${path.module}/../build/lambda.zip"
  # More memory also means more CPU, so a faster cold start.
  memory_size = 1024
  # The live flight call gives up after 5 s; API Gateway waits at most 30.
  timeout = 15

  environment {
    variables = {
      SSM_PARAMETER_PATH = local.api_ssm_path
      # API Gateway and CloudFront serve HTTPS only.
      SECURE_COOKIES = "on"
    }
  }

  lifecycle {
    ignore_changes = [filename]
  }

  # Its permissions and log group exist before its first run.
  depends_on = [aws_iam_role_policy.api, aws_cloudwatch_log_group.api]
}

# The public address. One $default route sends every request to the function,
# which routes it itself (FastAPI), so new endpoints need no change here.
resource "aws_apigatewayv2_api" "api" {
  name          = local.api_function_name
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "api" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

# Throttling: past ~10 requests a second (bursts of 20) API Gateway answers
# 429 itself, before the function runs. Approximate, not a hard cap: in a
# 1-second burst of 200 requests, 173 got through (measured 2026-10-25).
resource "aws_apigatewayv2_stage" "api" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit  = 10
    throttling_burst_limit = 20
  }
}

# Lets this API, and only it, invoke the function.
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowInvokeFromApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

output "api_url" {
  value = aws_apigatewayv2_stage.api.invoke_url
}

output "api_function_name" {
  value = aws_lambda_function.api.function_name
}
