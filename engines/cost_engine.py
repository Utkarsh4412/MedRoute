from typing import List, Optional

from engines.data_loader import get_comorbidity_weights, get_cost_matrix


def get_city_tier(city: str) -> str:
    metro_cities = ["mumbai", "delhi", "bangalore", "hyderabad", "chennai", "kolkata", "pune"]
    tier2_cities = ["nagpur", "ahmedabad", "jaipur", "lucknow", "indore", "surat", "bhopal", "coimbatore"]
    city_lower = city.lower()
    if city_lower in metro_cities:
        return "metro"
    elif city_lower in tier2_cities:
        return "tier2"
    else:
        return "tier3"


def compute_patient_multiplier(age: int, comorbidities: list[str]) -> float:
    weights = get_comorbidity_weights()

    # Age multiplier
    if age <= 40:
        age_mult = weights["age_multipliers"]["0_40"]
    elif age <= 60:
        age_mult = weights["age_multipliers"]["41_60"]
    elif age <= 75:
        age_mult = weights["age_multipliers"]["61_75"]
    else:
        age_mult = weights["age_multipliers"]["75_plus"]

    # Comorbidity additions (additive, not multiplicative, to avoid explosion)
    comorbidity_add = sum(
        weights["comorbidity_multipliers"].get(c.lower(), 0.0)
        for c in comorbidities
    )
    comorbidity_add = min(comorbidity_add, 0.50)  # cap at 50% extra

    return age_mult + comorbidity_add


def estimate_costs(
    procedure: str,
    city: str,
    age: int = 35,
    comorbidities: Optional[List[str]] = None,
    hospital_cost_tier: str = "mid"
) -> dict:
    if comorbidities is None:
        comorbidities = []

    matrix = get_cost_matrix()

    city_tier = get_city_tier(city)

    # Fallback to nearest procedure if exact not found
    if procedure not in matrix:
        procedure = "Consultation"

    base = matrix[procedure][city_tier]
    multiplier = compute_patient_multiplier(age, comorbidities)

    # Hospital tier adjustment
    tier_adj = {"budget": 0.75, "mid": 1.00, "premium": 1.40}.get(hospital_cost_tier, 1.00)

    def adj_range(rng):
        return [
            int(rng[0] * multiplier * tier_adj),
            int(rng[1] * multiplier * tier_adj)
        ]

    # Calculate each component
    stay_range = [
        int(base["stay_per_day"][0] * base["avg_stay_days"][0] * multiplier * tier_adj),
        int(base["stay_per_day"][1] * base["avg_stay_days"][1] * multiplier * tier_adj)
    ]

    proc_range = adj_range(base["procedure"])
    doc_range = adj_range(base["doctor_fee"])
    diag_pre = adj_range(base["diagnostics_pre"])
    diag_post = adj_range(base["diagnostics_post"])
    meds = adj_range(base["medicines"])

    # Subtotal
    subtotal = [
        proc_range[0] + doc_range[0] + stay_range[0] + diag_pre[0] + diag_post[0] + meds[0],
        proc_range[1] + doc_range[1] + stay_range[1] + diag_pre[1] + diag_post[1] + meds[1]
    ]

    # Contingency
    contingency = [
        int(subtotal[0] * base["contingency_pct"]),
        int(subtotal[1] * base["contingency_pct"])
    ]

    total = [subtotal[0] + contingency[0], subtotal[1] + contingency[1]]

    # Build comorbidity notes
    risk_notes = []
    lowered = [c.lower() for c in comorbidities]
    if "diabetes" in lowered:
        risk_notes.append("Diabetes may increase infection risk and extend recovery by 1-2 days")
    if "cardiac_history" in lowered:
        risk_notes.append("Cardiac history increases ICU likelihood — costs may exceed upper estimate")
    if "ckd" in lowered:
        risk_notes.append("Kidney disease affects anesthesia protocol; nephrology consult required")
    if age > 65:
        risk_notes.append("Age above 65 increases post-op care requirements")

    return {
        "procedure": procedure,
        "city_tier": city_tier,
        "breakdown": {
            "procedure_cost": proc_range,
            "doctor_fees": doc_range,
            "hospital_stay": stay_range,
            "diagnostics_pre": diag_pre,
            "diagnostics_post": diag_post,
            "medicines": meds,
            "contingency": contingency
        },
        "total_estimated_cost": total,
        "patient_multiplier": round(multiplier, 2),
        "risk_notes": risk_notes,
        "currency": "INR"
    }
