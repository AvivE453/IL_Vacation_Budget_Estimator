import pytest

from etl.common.currency import from_usd, get_usd_per_unit, to_usd


class FakeCursor:
    def __init__(self, rate_row):
        self._rate_row = rate_row
        self.last_query = None

    def execute(self, query, params):
        self.last_query = (query, params)

    def fetchone(self):
        return self._rate_row


def test_usd_rate_is_one_without_a_query():
    cur = FakeCursor(rate_row=None)
    assert get_usd_per_unit(cur, "USD") == 1.0
    assert cur.last_query is None


def test_rate_read_from_exchange_rates():
    cur = FakeCursor(rate_row={"usd_per_unit": 0.27})
    assert get_usd_per_unit(cur, "ILS") == 0.27
    assert cur.last_query[1] == ("ILS",)


def test_rate_lookup_raises_when_rate_missing():
    cur = FakeCursor(rate_row=None)
    with pytest.raises(ValueError):
        get_usd_per_unit(cur, "GEL")


def test_to_usd_converts_using_rate():
    assert to_usd(100, 1.1) == 110.0


def test_from_usd_converts_using_rate():
    assert from_usd(100, 0.27) == pytest.approx(370.37, abs=0.01)
