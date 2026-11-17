"""Presentation boundaries: currency units and unavailable financial results."""

import pytest

from frontend.components import delta_text, eur


@pytest.mark.parametrize(
    "value,precision,expected",
    [
        (48107.54670458674, 1, "€48.1m"),
        (48107.54670458674, 2, "€48.11m"),
        (-1234.5, 2, "−€1.23m"),
        (0, 1, "€0.0m"),
        (None, 1, "Unavailable"),
        (float("nan"), 1, "Unavailable"),
        (float("inf"), 1, "Unavailable"),
    ],
)
def test_financial_display_units_and_missing_values(value, precision, expected):
    assert eur(value, precision) == expected


def test_native_metric_delta_has_unambiguous_direction():
    assert delta_text(-8800, "reference scenario") == "-€8.8m vs reference scenario"
    assert delta_text(20700, "ranked list") == "+€20.7m vs ranked list"
