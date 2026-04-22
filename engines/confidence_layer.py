def compute_confidence(
    specialty_probability: float,       # from LogReg model (0-1)
    hospital_match_count: int,          # how many hospitals matched
    cost_data_completeness: float,      # 1.0 if procedure in matrix, 0.6 if fallback
    symptom_length: int                 # longer symptoms = better signal
) -> float:
    # Component scores
    model_conf = min(specialty_probability * 1.2, 1.0)   # scale up but cap at 1
    provider_conf = min(hospital_match_count / 3.0, 1.0) # 3+ hospitals = full confidence
    data_conf = cost_data_completeness
    symptom_conf = min(symptom_length / 50, 1.0)          # 50+ chars = good signal

    # Weighted combination
    raw = (
        0.45 * model_conf +
        0.20 * provider_conf +
        0.25 * data_conf +
        0.10 * symptom_conf
    )

    # Hard cap: never claim > 0.92 confidence (responsible AI)
    return round(min(raw, 0.92), 2)


def build_lender_signal(
    confidence: float,
    total_cost_range: list,
    urgency_level: str
) -> dict:
    """
    This field is what makes us relevant to Poonawalla Fincorp.
    Converts our health assessment into a pre-underwriting signal.
    """
    max_cost = total_cost_range[1]

    if confidence >= 0.70 and max_cost <= 500000:
        signal = "pre_approve_eligible"
        message = "Cost range and clinical confidence support pre-approval up to ₹5L"
    elif confidence >= 0.55 and max_cost <= 1500000:
        signal = "soft_eligible"
        message = "Requires document verification before loan disbursement"
    else:
        signal = "needs_review"
        message = "Low confidence or high cost estimate — manual underwriting required"

    return {
        "signal": signal,
        "message": message,
        "max_loan_indicative": int(max_cost * 0.90),    # 90% LTV
        "urgency": urgency_level
    }


MANDATORY_DISCLAIMERS = [
    "This is a decision support tool, not medical advice. Consult a qualified physician before making treatment decisions.",
    "Cost estimates are indicative ranges based on synthetic benchmarks. Actual costs depend on your specific condition, doctor, and hospital.",
    "Hospital rankings are based on publicly available data and proximity. They do not constitute a medical endorsement.",
    "In case of emergency, call 112 immediately."
]


def build_responsible_output(
    condition: str,
    confidence: float,
    cost_range: list,
    hospitals: list,
    cost_breakdown: dict,
    lender_signal: dict,
    risk_notes: list
) -> dict:
    # Uncertainty label
    if confidence >= 0.75:
        certainty_label = "moderate_confidence"
    elif confidence >= 0.55:
        certainty_label = "low_confidence"
    else:
        certainty_label = "very_low_confidence"

    return {
        "condition_mapped": condition,
        "confidence_score": confidence,
        "certainty_label": certainty_label,
        "recommended_hospitals": hospitals,
        "cost_estimate": cost_breakdown,
        "lender_signal": lender_signal,
        "risk_notes": risk_notes,
        "disclaimers": MANDATORY_DISCLAIMERS,
        "generated_at": "UTC timestamp"
    }
