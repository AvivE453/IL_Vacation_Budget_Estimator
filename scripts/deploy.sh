#!/usr/bin/env bash
# Ships the code to the AWS resources Terraform created (ROADMAP 4.4, 4.9):
# migrations and seed data to Neon, the zip to both Lambda functions, the React
# build to the site bucket, then smoke tests against the live site.
# Terraform owns the resources and their settings; this script only ships code.
#
# From the laptop: an AWS session (aws login) and an initialized infra/, which
# gives the names. From CI's deploy job: the names come from the environment
# (SITE_BUCKET, SITE_URL, API_FUNCTION, JOBS_FUNCTION), and SKIP_BUILD=1, since
# an earlier step without the AWS key built everything.
#
# Run with: scripts/deploy.sh

set -euo pipefail
cd "$(dirname "$0")/.."

# Both builds read the files on disk, so an uncommitted change would go live
# untested. Gitignored files (.env, ROADMAP.md...) don't count.
if [ -n "$(git status --porcelain)" ]; then
  echo "Uncommitted changes - commit or stash them first:" >&2
  git status --short >&2
  exit 1
fi

tf_output() { terraform -chdir=infra output -raw "$1"; }
# One assignment each: set -e stops on a failed $(...) only when it's the whole assignment.
bucket=${SITE_BUCKET:-$(tf_output site_bucket)}
site_url=${SITE_URL:-$(tf_output site_url)}
api_function=${API_FUNCTION:-$(tf_output api_function_name)}
jobs_function=${JOBS_FUNCTION:-$(tf_output jobs_function_name)}

# Both builds before anything ships: a failing one (a type error, say) must
# not leave a new API live behind the old site.
if [ -z "${SKIP_BUILD:-}" ]; then
  echo "== Build the API zip and the React app ($(git rev-parse --short HEAD))"
  scripts/build_lambda.sh
  (cd frontend && npm run build)
fi
zip_sha=$(openssl dgst -sha256 -binary build/lambda.zip | base64)

# Before any code ships, so a failing migration stops the deploy with the old
# code still live. The old code then runs against the new schema for a moment:
# a migration only adds, never drops what the running code still reads.
echo "== Migrations and seed data on Neon"
DB_URL=$(aws ssm get-parameter --name /vacation-budget/jobs/DB_URL --with-decryption --query Parameter.Value --output text)
if [ -n "${GITHUB_ACTIONS:-}" ]; then
  # GitHub hides these values wherever they'd appear in the public log; the
  # password on its own too, since an error message may quote just that.
  echo "::add-mask::$DB_URL"
  echo "::add-mask::$(python3 -c 'import sys, urllib.parse; print(urllib.parse.urlsplit(sys.argv[1]).password)' "$DB_URL")"
fi
export DB_URL
uv run python -m etl.loaders.run_migrations
uv run python -m etl.loaders.load_airports
uv run python -m etl.loaders.load_destinations_seed

update_lambda() {
  echo "== Lambda: update $1"
  aws lambda update-function-code --function-name "$1" --zip-file fileb://build/lambda.zip --output text --query CodeSize >/dev/null
  aws lambda wait function-updated-v2 --function-name "$1"
  if [ "$(aws lambda get-function-configuration --function-name "$1" --query CodeSha256 --output text)" != "$zip_sha" ]; then
    echo "$1 doesn't run the zip just built" >&2
    exit 1
  fi
}

update_lambda "$api_function"

# Order matters: the new assets go up before the index.html that points at
# them, so no visitor ever gets a page whose files aren't there yet. Old
# assets stay, for anyone still on the previous index.html.
echo "== Site: upload to $bucket"
# Their names carry a hash of their content, so a file never changes: cache it for a year.
aws s3 sync frontend/dist/assets "s3://$bucket/assets" --cache-control "public, max-age=31536000, immutable" --only-show-errors
# Anything else at the top level (icons...): an hour.
aws s3 sync frontend/dist "s3://$bucket" --exclude "assets/*" --exclude "index.html" --cache-control "public, max-age=3600" --only-show-errors
# no-cache: browsers and CloudFront check S3 for a newer one on every load
# (CloudFront answers RefreshHit after its 1-second minimum), so a deploy
# shows up at once - no CloudFront invalidation needed.
aws s3 cp frontend/dist/index.html "s3://$bucket/index.html" --cache-control "no-cache" --only-show-errors

# Last: no visitor sees it, so a failure here leaves the API and the site matched.
update_lambda "$jobs_function"

scripts/smoke_test.sh "$site_url"
echo "Deployed $(git rev-parse --short HEAD): $site_url"
