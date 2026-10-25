#!/usr/bin/env bash
# Builds build/lambda.zip: the code both Lambda functions run (api/, app/,
# etl/) plus its dependencies, installed for Lambda's Linux (x86_64, Python
# 3.12) rather than for this machine - psycopg2 contains compiled code, and a
# wheel built for the wrong platform fails only when Lambda imports it.
# boto3 isn't included: Lambda's Python runtime already has it.
#
# Run with: scripts/build_lambda.sh

set -euo pipefail
cd "$(dirname "$0")/.."

out=build/lambda
rm -rf build
mkdir -p "$out"

# The exact versions in uv.lock, without the dev tools (pytest, ruff).
uv export --frozen --no-dev --no-hashes --no-emit-project --quiet -o build/requirements.txt
uv pip install --quiet --target "$out" -r build/requirements.txt \
  --python-platform x86_64-manylinux2014 --python-version 3.12 --only-binary :all:

cp -r api app etl "$out"/
find "$out" -name __pycache__ -type d -prune -exec rm -rf {} +

(cd "$out" && zip -qr ../lambda.zip .)
echo "build/lambda.zip: $(du -h build/lambda.zip | cut -f1) zipped, $(du -sh "$out" | cut -f1) unzipped"
