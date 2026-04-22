from math import radians, cos, sin, asin, sqrt

from engines.data_loader import get_hospital_db

METRO_CITIES = {"mumbai", "delhi", "bangalore", "hyderabad", "chennai", "kolkata", "pune"}


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


def rank_hospitals(
    specialty: str,
    city: str,
    user_lat: float,
    user_lon: float,
    budget_filter: str = None,  # "budget" | "mid" | "premium" | None
    top_n: int = 3
) -> list[dict]:
    df = get_hospital_db()

    # Filter by city (exact match first, fallback to city_tier)
    city_df = df[df["city"].str.lower() == city.lower()]
    if len(city_df) < 3:
        target_tier = "metro" if city.lower() in METRO_CITIES else "tier2"
        city_df = df[df["city_tier"] == target_tier]

    # Filter specialty match
    def has_specialty(spec_str):
        return specialty.lower() in str(spec_str).lower()

    city_df = city_df[city_df["specialties"].apply(has_specialty)]

    if budget_filter:
        city_df = city_df[city_df["cost_tier"] == budget_filter]

    if city_df.empty:
        return []

    # Scoring
    results = []
    for _, row in city_df.iterrows():
        distance = haversine_km(user_lat, user_lon, row["lat"], row["lon"])

        # Specialty match score (1.0 if exact, 0.5 if partial)
        specialty_score = 1.0 if specialty in row["specialties"] else 0.5

        # Distance decay (0km=1.0, 10km=0.5, 30km=0.1)
        distance_score = 1 / (1 + distance / 8)

        # Reputation score
        rating_score = (row["rating"] - 3.0) / 2.0  # normalize 3-5 → 0-1
        review_weight = min(row["review_count"] / 2000, 1.0)  # cap at 2000 reviews
        reputation_score = rating_score * 0.7 + review_weight * 0.3

        # Accreditation bonus
        nabh_bonus = 0.15 if row["nabh_accredited"] == True else 0.0

        # Final weighted score
        final_score = (
            0.40 * specialty_score +
            0.25 * distance_score +
            0.25 * reputation_score +
            0.10 * nabh_bonus
        )

        # Key strengths (derive dynamically)
        strengths = []
        if row["nabh_accredited"]:
            strengths.append("NABH Accredited")
        if row["rating"] >= 4.5:
            strengths.append("Highly rated")
        if distance < 5:
            strengths.append("Nearby")
        if row["cost_tier"] == "budget":
            strengths.append("Affordable")
        if row["bed_count"] > 250:
            strengths.append("Large facility")

        results.append({
            "hospital_id": row["hospital_id"],
            "name": row["hospital_name"],
            "city": row["city"],
            "rating": float(row["rating"]),
            "cost_tier": row["cost_tier"],
            "distance_km": round(distance, 1),
            "nabh": bool(row["nabh_accredited"]),
            "strengths": strengths[:3],
            "score": round(final_score, 3),
            "description": row["description"]
        })

    # Sort by score, return top N
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]
