from engines.confidence_layer import compute_confidence, build_lender_signal


def test_confidence_never_exceeds_0_92():
    # Even with perfect inputs
    conf = compute_confidence(1.0, 10, 1.0, 200)
    assert conf <= 0.92


def test_confidence_is_float_between_0_and_1():
    conf = compute_confidence(0.8, 3, 1.0, 60)
    assert 0.0 <= conf <= 1.0


def test_lender_pre_approve_high_confidence_low_cost():
    result = build_lender_signal(0.80, [100000, 400000], "high")
    assert result["signal"] == "pre_approve_eligible"


def test_lender_needs_review_low_confidence():
    result = build_lender_signal(0.40, [100000, 300000], "low")
    assert result["signal"] == "needs_review"


def test_lender_signal_has_required_fields():
    result = build_lender_signal(0.75, [200000, 500000], "medium")
    for field in ["signal", "message", "max_loan_indicative", "urgency"]:
        assert field in result
