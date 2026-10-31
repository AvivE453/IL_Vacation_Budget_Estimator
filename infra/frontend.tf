# The site: the React build in a private S3 bucket, served with the API through
# one CloudFront distribution.

# Runs on every viewer request to the S3 behavior, at the edge.
resource "aws_cloudfront_function" "spa_rewrite" {
  name    = "vacation-budget-spa-rewrite"
  runtime = "cloudfront-js-2.0"
  comment = "Inner pages (no file extension) get index.html"
  code    = file("${path.module}/spa_rewrite.js")
  publish = true
}

# The React build (scripts/deploy.sh uploads it). Private: only the
# distribution below may read it, through Origin Access Control.
resource "aws_s3_bucket" "site" {
  bucket = "vacation-budget-site-${data.aws_caller_identity.current.account_id}"
  # Holds only build output, which the deploy script recreates: terraform
  # destroy may empty it rather than fail on a non-empty bucket.
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# CloudFront signs its requests to the bucket, and the bucket policy accepts
# only requests signed for this distribution.
resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "vacation-budget-site"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.site.arn}/*"
      Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.site.arn } }
    }]
  })
}

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

# Every viewer header, cookie and query string, except Host: API Gateway
# rejects a request whose Host is the CloudFront address.
data "aws_cloudfront_origin_request_policy" "all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

locals {
  site_origin = "site-bucket"
  api_origin  = "api-gateway"
}

# One address for the page and the API, so the session cookie works without
# CORS, like Vite's proxy in development.
resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  comment             = "IL Vacation Budget Estimator"
  default_root_object = "index.html"
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  # North America, Europe and Israel: the cheapest class that covers Israel.
  price_class = "PriceClass_100"

  origin {
    origin_id                = local.site_origin
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  origin {
    origin_id   = local.api_origin
    domain_name = replace(aws_apigatewayv2_api.api.api_endpoint, "https://", "")
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # /api/*: never cached, everything the API reads passed through.
  ordered_cache_behavior {
    path_pattern             = "/api/*"
    target_origin_id         = local.api_origin
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
    compress                 = true
  }

  # Everything else: the React build from S3. The cache follows each file's
  # Cache-Control, which the deploy script sets.
  default_cache_behavior {
    target_origin_id       = local.site_origin
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.caching_optimized.id
    compress               = true

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa_rewrite.arn
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # CloudFront's own certificate for *.cloudfront.net: HTTPS with nothing to set up.
  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

output "site_url" {
  value = "https://${aws_cloudfront_distribution.site.domain_name}/"
}

# Read by scripts/deploy.sh.
output "site_bucket" {
  value = aws_s3_bucket.site.bucket
}
