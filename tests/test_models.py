"""Tests for observation validation."""

import pytest

from custom_components.irminsul_health.models import (
    ObservationValidationError,
    parse_observation,
)


def test_parse_uric_acid_umol() -> None:
    """Normalize a micromole observation."""
    observation = parse_observation(
        {
            "metric": "uric_acid",
            "value": 426,
            "unit": "μmol/L",
            "observed_at": "2026-09-05T08:30:00+08:00",
            "external_id": "meter-1",
        }
    )

    assert observation.value == 426
    assert observation.unit == "µmol/L"
    assert observation.observed_at == "2026-09-05T00:30:00+00:00"


def test_parse_uric_acid_mg_dl() -> None:
    """Convert milligrams per deciliter to micromoles per liter."""
    observation = parse_observation(
        {
            "metric": "uric_acid",
            "value": 7.2,
            "unit": "mg/dL",
            "observed_at": "2026-09-05T00:00:00Z",
        }
    )

    assert observation.value == 428.26


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("metric", "weight"),
        ("value", float("nan")),
        ("unit", "mmol/L"),
        ("observed_at", "2026-09-05T08:30:00"),
    ],
)
def test_reject_invalid_observation(field: str, value: object) -> None:
    """Reject unsupported or ambiguous input."""
    payload = {
        "metric": "uric_acid",
        "value": 426,
        "unit": "µmol/L",
        "observed_at": "2026-09-05T08:30:00+08:00",
    }
    payload[field] = value

    with pytest.raises(ObservationValidationError):
        parse_observation(payload)
