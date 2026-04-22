import pytest
from engines.cost_engine import estimate_costs, get_city_tier, compute_patient_multiplier


def test_city_tier_metro():
    assert get_city_tier("Mumbai") == "metro"
    assert get_city_tier("hyderabad") == "metro"


def test_city_tier_tier2():
    assert get_city_tier("Nagpur") == "tier2"
    assert get_city_tier("Jaipur") == "tier2"


def test_city_tier_unknown():
    assert get_city_tier("SomeRandomVillage") == "tier3"


def test_cost_estimate_returns_range():
    result = estimate_costs("Angioplasty", "Hyderabad", age=55, comorbidities=["diabetes"])
    total = result["total_estimated_cost"]
    assert len(total) == 2
    assert total[0] < total[1]  # low < high
    assert total[0] > 0


def test_cost_breakdown_has_7_components():
    result = estimate_costs("Angioplasty", "Hyderabad")
    breakdown = result["breakdown"]
    assert "procedure_cost" in breakdown
    assert "doctor_fees" in breakdown
    assert "hospital_stay" in breakdown
    assert "diagnostics_pre" in breakdown
    assert "diagnostics_post" in breakdown
    assert "medicines" in breakdown
    assert "contingency" in breakdown


def test_diabetes_increases_cost():
    base = estimate_costs("Angioplasty", "Hyderabad", age=40, comorbidities=[])
    with_diabetes = estimate_costs("Angioplasty", "Hyderabad", age=40, comorbidities=["diabetes"])
    assert with_diabetes["total_estimated_cost"][0] > base["total_estimated_cost"][0]


def test_patient_multiplier_increases_with_age():
    young = compute_patient_multiplier(30, [])
    old = compute_patient_multiplier(70, [])
    assert old > young


def test_mutable_default_not_shared():
    # Calling twice should not accumulate comorbidities
    r1 = estimate_costs("Angioplasty", "Mumbai")
    r2 = estimate_costs("Angioplasty", "Mumbai")
    assert r1["total_estimated_cost"] == r2["total_estimated_cost"]
