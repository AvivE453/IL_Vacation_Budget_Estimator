# The nightly backups (ROADMAP 4.6): etl/backup/backup.py writes each table as
# backups/YYYY-MM-DD/<table>.csv.gz. The jobs function may only add files here;
# reading them back is restore.py's job, from this machine.

resource "aws_s3_bucket" "backups" {
  bucket = "vacation-budget-backups-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "backups" {
  bucket                  = aws_s3_bucket.backups.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Write access can still overwrite a file. With versions on, an overwritten
# backup keeps its old version, which the jobs role can't delete.
resource "aws_s3_bucket_versioning" "backups" {
  bucket = aws_s3_bucket.backups.id
  versioning_configuration {
    status = "Enabled"
  }
}

# S3 itself deletes old files once a day; nobody's permissions are involved.
resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id

  rule {
    id     = "expire-old-backups"
    status = "Enabled"
    filter {
      prefix = "backups/"
    }
    # ~710 KB a night (2026-10-26): 90 days is ~65 MB.
    expiration {
      days = 90
    }
    # An overwritten or expired version: a month to notice and restore it.
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }

  # With versions on, expiring a file only hides it behind a "delete marker";
  # once its old version is gone too, this removes the marker, so nothing
  # piles up.
  rule {
    id     = "remove-expired-delete-markers"
    status = "Enabled"
    filter {
      prefix = "backups/"
    }
    expiration {
      expired_object_delete_marker = true
    }
  }

  depends_on = [aws_s3_bucket_versioning.backups]
}

# Added to the jobs role: write new backup files, nothing else in the bucket.
resource "aws_iam_role_policy" "jobs_backups" {
  name = "write-backups"
  role = aws_iam_role.jobs.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "s3:PutObject"
      Resource = "${aws_s3_bucket.backups.arn}/backups/*"
    }]
  })
}

output "backup_bucket" {
  value = aws_s3_bucket.backups.bucket
}
