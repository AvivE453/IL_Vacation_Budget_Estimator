# etl/common/config.py on Lambda: the secrets come from SSM Parameter Store
# instead of .env. A fake SSM client stands in for AWS, so nothing here leaves
# the machine.

import importlib
import sys
import types

import pytest

from etl.common import config


class FakeSSM:
    def __init__(self, pages):
        self.pages = pages
        self.asked_for = None

    def get_paginator(self, operation):
        assert operation == "get_parameters_by_path"
        return self

    def paginate(self, **kwargs):
        self.asked_for = kwargs
        return self.pages


def parameter(name, value):
    return {"Name": name, "Value": value, "Type": "SecureString"}


def test_parameters_are_read_decrypted_and_named_without_their_path():
    ssm = FakeSSM([
        {"Parameters": [parameter("/vacation-budget/DB_URL", "postgresql://neon")]},
        {"Parameters": [parameter("/vacation-budget/SERPAPI_KEY", "serp-key")]},
    ])

    values = config.fetch_ssm_parameters("/vacation-budget/", ssm)

    assert values == {"DB_URL": "postgresql://neon", "SERPAPI_KEY": "serp-key"}
    assert ssm.asked_for == {"Path": "/vacation-budget/", "WithDecryption": True}


# Reloads the module the way a Lambda cold start imports it, then reloads it
# again without SSM so the rest of the suite sees the normal config.
@pytest.fixture()
def reload_config(monkeypatch):
    yield lambda: importlib.reload(config)
    monkeypatch.undo()
    importlib.reload(config)


def test_on_lambda_the_constants_come_from_ssm(monkeypatch, reload_config):
    ssm = FakeSSM([{"Parameters": [
        parameter("/vacation-budget/DB_URL", "postgresql://neon"),
        parameter("/vacation-budget/TRAVELPAYOUTS_TOKEN", "tp-token"),
    ]}])
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=lambda service: ssm))
    monkeypatch.setenv("SSM_PARAMETER_PATH", "/vacation-budget/")
    # Restored by monkeypatch: the reload writes the SSM values into os.environ.
    monkeypatch.setenv("DB_URL", "postgresql://local")
    monkeypatch.setenv("TRAVELPAYOUTS_TOKEN", "")

    reloaded = reload_config()

    assert (reloaded.DB_URL, reloaded.TRAVELPAYOUTS_TOKEN) == ("postgresql://neon", "tp-token")
