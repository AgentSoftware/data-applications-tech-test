from datetime import date

import pytest

from psc_pipeline.normalise import date_from_filename, is_uk, normalise_number, parse_date


# spec 02, table 1.1
@pytest.mark.parametrize("raw, expected", [
    ("09090984", "09090984"),
    (" 10333133", "10333133"),
    ("13405766 ", "13405766"),
    ("9906121", "09906121"),
    ("oc330146", "OC330146"),
    ("Sc19230", "SC019230"),
    ("ZC202", "ZC000202"),
    ("SC 034970", "SC034970"),
    ("R0000134", "R0000134"),
    ("123456789", None),
    ("ABC123", None),
    ("Zc", None),
    ("", None),
    (None, None),
    (12345678, None),
    ("١٢٣٤٥٦٧٨", None),  # non-ASCII digits pass str.isdigit
])
def test_normalise_number(raw, expected):
    assert normalise_number(raw) == expected


@pytest.mark.parametrize("key", ["09090984", "OC330146", "SC019230", "R0000134", "NI043691"])
def test_valid_keys_are_unchanged(key):
    # ADR 0005: every key in the output must normalise to itself
    assert normalise_number(key) == key


@pytest.mark.parametrize("country, place, expected", [
    ("United Kingdom (Scotland)", None, True),
    ("England And Wales", "", True),
    (None, "Companies House, Cardiff", True),
    ("UK", None, True),
    ("Northern Ireland", None, True),
    ("Delaware", "Delaware Secretary Of State", False),
    ("Jersey", None, False),
    ("Ukraine", None, False),   # 'uk' must be a whole word
    (None, None, None),
    ("  ", "", None),
])
def test_is_uk(country, place, expected):
    assert is_uk(country, place) == expected


@pytest.mark.parametrize("raw, expected", [
    ("2020-01-31", (date(2020, 1, 31), None)),
    ("2021-03-04T00:00:00", (date(2021, 3, 4), "date_timestamp_truncated")),
    ("2021-02-30", (None, "invalid_date")),
    ("31/01/2020", (None, "invalid_date")),
    ("2020-1-5", (None, "invalid_date")),
    ("2020-W01-1", (None, "invalid_date")),  # ISO week date: fromisoformat would accept it
    ("20200131", (None, "invalid_date")),
    (20200131, (None, "invalid_date")),
    (None, (None, None)),
])
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


def test_date_from_filename():
    assert date_from_filename("data/persons-with-significant-control-snapshot-2026-10-29-sample.txt.gz") == date(2026, 10, 29)
    assert date_from_filename("snapshot.txt") is None
