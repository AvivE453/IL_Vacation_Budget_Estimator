# Loads config/secrets from .env into these constants - imported by both
# app/ and etl/ code that needs the DB URL or an API key.

import os

from dotenv import load_dotenv


# {name: value} for every parameter under path, decrypted: /vacation-budget/DB_URL
# becomes DB_URL. get_parameters_by_path returns 10 parameters per call, so it's paged.
def fetch_ssm_parameters(path, ssm_client):
    pages = ssm_client.get_paginator("get_parameters_by_path").paginate(Path=path, WithDecryption=True)
    return {param["Name"].rsplit("/", 1)[-1]: param["Value"] for page in pages for param in page["Parameters"]}


load_dotenv()

# On Lambda there's no .env: the secrets are SSM Parameter Store SecureStrings
# under SSM_PARAMETER_PATH, loaded once per cold start, before the constants
# below read them. boto3 comes with Lambda's Python runtime, so it isn't a
# project dependency and is imported only here.
if ssm_path := os.environ.get("SSM_PARAMETER_PATH"):
    import boto3

    os.environ.update(fetch_ssm_parameters(ssm_path, boto3.client("ssm")))

DB_URL = os.environ["DB_URL"]
TRAVELPAYOUTS_TOKEN = os.environ.get("TRAVELPAYOUTS_TOKEN", "")
TRAVELPAYOUTS_MARKER = os.environ.get("TRAVELPAYOUTS_MARKER", "")
# "off" makes destination views use collected data only, with no call to
# Travelpayouts - for the end-to-end tests (fixed answers) and offline work.
LIVE_FLIGHT_SEARCH = os.environ.get("LIVE_FLIGHT_SEARCH", "on") != "off"
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
# Where the nightly backup goes (etl/backup/backup.py); set on the jobs Lambda only.
BACKUP_BUCKET = os.environ.get("BACKUP_BUCKET", "")
# "on" marks the session cookie Secure (sent over HTTPS only) - for the site
# behind CloudFront. Off by default: local development runs over plain http,
# where a browser would drop a Secure cookie and every request would start a
# new session.
SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "off") == "on"
