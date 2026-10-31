# Automated deploys: the identity CI's deploy job uses.
#
# An IAM user with an access key, not OIDC: this account type's organization
# policy (managed by AWS) denies creating an OIDC provider. So the
# key is long-lived, and what limits it is elsewhere: this policy (deploying
# only), and GitHub's "production" environment, which hands the key only to
# runs on master. The key is created by hand and goes straight into that
# environment's secrets, never through Terraform, which would write it into
# the state.

resource "aws_iam_user" "deploy" {
  name = "vacation-budget-deploy"
}

# What deploy.sh does, and nothing else: ship both functions' code, upload the
# site (sync lists the bucket to compare; it never deletes), and read the
# database URL for the migrations.
resource "aws_iam_user_policy" "deploy" {
  name = "ship-code-and-site"
  user = aws_iam_user.deploy.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        # GetFunction is what "aws lambda wait function-updated-v2" polls;
        # GetFunctionConfiguration reads CodeSha256 to check what shipped.
        Action   = ["lambda:UpdateFunctionCode", "lambda:GetFunction", "lambda:GetFunctionConfiguration"]
        Resource = [aws_lambda_function.api.arn, aws_lambda_function.jobs.arn]
      },
      {
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = aws_s3_bucket.site.arn
      },
      {
        Effect   = "Allow"
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.site.arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = "ssm:GetParameter"
        Resource = "${local.ssm_arn}${local.jobs_ssm_path}DB_URL"
      },
    ]
  })
}
