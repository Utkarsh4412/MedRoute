import pytest
from engines.provider_engine import rank_hospitals, haversine_km


def test_haversine_same_point():
    assert haversine_km(17.38, 78.48, 17.38, 78.48) == 0.0


def test_haversine_known_distance():
    # Mumbai to Delhi is approx 1150km
    dist = haversine_km(19.076, 72.877, 28.614, 77.209)
    assert 1100 < dist < 1200


def test_rank_returns_list():
    result = rank_hospitals("Cardiologist", "Hyderabad", 17.385, 78.486)
    assert isinstance(result, list)


def test_rank_returns_at_most_3():
    result = rank_hospitals("Cardiologist", "Hyderabad", 17.385, 78.486, top_n=3)
    assert len(result) <= 3


def test_rank_sorted_by_score():
    result = rank_hospitals("Cardiologist", "Hyderabad", 17.385, 78.486)
    scores = [h["score"] for h in result]
    assert scores == sorted(scores, reverse=True)


def test_rank_result_has_required_fields():
    result = rank_hospitals("Cardiologist", "Hyderabad", 17.385, 78.486)
    if result:
        h = result[0]
        for field in ["name", "city", "rating", "cost_tier", "distance_km", "score", "strengths"]:
            assert field in h, f"Missing field: {field}"


def test_unknown_specialty_returns_empty_or_fallback():
    result = rank_hospitals("AlienDoctor", "Hyderabad", 17.385, 78.486)
    assert isinstance(result, list)  # Should not crash
