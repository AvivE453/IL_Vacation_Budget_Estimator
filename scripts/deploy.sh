#!/usr/bin/env bash
# Ships the code to the AWS resources Terraform created (ROADMAP 4.4):
# the React build to the site bucket, and the zip to the API function.
# Terraform owns the resources and their settings; this script only ships code.
# Needs an AWS session (aws login) and an initialized infra/.
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
bucket=$(tf_output site_bucket)
function=$(tf_output api_function_name)

# Both builds before anything ships: a failing one (a type error, say) must
# not leave a new API live behind the old site.
echo "== Build the API zip and the React app ($(git rev-parse --short HEAD))"
scripts/build_lambda.sh
(cd frontend && npm run build)

echo "== API: update $function"
aws lambda update-function-code --function-name "$function" --zip-file fileb://build/lambda.zip --output text --query CodeSize >/dev/null
aws lambda wait function-updated-v2 --function-name "$function"

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

echo "Deployed $(git rev-parse --short HEAD): $(tf_output site_url)"
