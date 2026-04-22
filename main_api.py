import logging
import sys
import time
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

sys.path.insert(0, "symptom_classifier")
sys.path.insert(0, "symtom_classifier")

# Import existing classifier
from app import predict as symptom_predict, PredictRequest

# Import new engines
from engines.provider_engine import rank_hospitals
from engines.cost_engine import estimate_costs
from engines.confidence_layer import compute_confidence, build_lender_signal, build_responsible_output
from engines.data_loader import get_cost_matrix, get_hospital_db, get_specialty_map

app = FastAPI(title="MedRoute — Healthcare Navigator API", version="1.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("medroute")

SPECIALTY_MAP = get_specialty_map()
VALID_CITY_TIERS = {
    "metro": ["mumbai", "delhi", "bangalore", "hyderabad", "chennai", "kolkata", "pune"],
    "tier2": ["nagpur", "ahmedabad", "jaipur", "lucknow", "indore", "surat", "bhopal", "coimbatore"],
}
ALL_KNOWN_CITIES = [city for cities in VALID_CITY_TIERS.values() for city in cities]
VALID_BUDGET_PREFS = {"budget", "mid", "premium", None}
VALID_COMORBIDITIES = {"diabetes", "hypertension", "cardiac_history", "ckd", "obesity", "copd", "cancer"}
HARD_EMERGENCY_KEYWORDS = {
    "heart attack", "stroke", "severe bleeding", "unconscious", "seizure", "collapse", "suicide"
}


class NavigateRequest(BaseModel):
    symptoms: str = Field(..., min_length=5, description="Natural language description of symptoms or condition")
    city: str = Field(..., description="City name in India")
    lat: Optional[float] = None
    lon: Optional[float] = None
    age: Optional[int] = Field(35, ge=0, le=120)
    comorbidities: Optional[List[str]] = None
    budget_preference: Optional[str] = None  # "budget" | "mid" | "premium"
    name: Optional[str] = "anonymous"


def validate_request(req: NavigateRequest):
    errors = []
    if len(req.symptoms.strip()) < 5:
        errors.append("symptoms must be at least 5 characters")
    if req.age is not None and not (0 <= req.age <= 120):
        errors.append("age must be between 0 and 120")
    if req.budget_preference not in VALID_BUDGET_PREFS:
        errors.append("budget_preference must be one of: budget, mid, premium")
    unknown_comorbidities = [c for c in (req.comorbidities or []) if c.lower() not in VALID_COMORBIDITIES]
    if unknown_comorbidities:
        errors.append(f"unknown comorbidities: {unknown_comorbidities}. Valid: {sorted(VALID_COMORBIDITIES)}")
    if errors:
        raise HTTPException(status_code=422, detail={"validation_errors": errors})


def classify_without_model(symptoms: str):
    text = symptoms.lower()
    if any(k in text for k in ("chest pain", "breathless", "palpitations")):
        specialty = "Cardiologist"
    elif any(k in text for k in ("knee", "joint", "back pain", "fracture")):
        specialty = "Orthopedist"
    elif any(k in text for k in ("stomach", "vomit", "abdominal", "acidity")):
        specialty = "Gastroenterologist"
    elif any(k in text for k in ("headache", "dizziness", "seizure", "migraine")):
        specialty = "Neurologist"
    elif any(k in text for k in ("cough", "breathing", "asthma")):
        specialty = "Pulmonologist"
    else:
        specialty = "General Physician"
    return specialty, {specialty: 0.7}


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 1)
    logger.info(
        f"req={request_id} method={request.method} path={request.url.path} "
        f"status={response.status_code} duration={duration_ms}ms"
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.post("/navigate")
async def navigate(req: NavigateRequest):
    """
    Full pipeline: symptoms → specialist → hospitals → costs → confidence
    """

    validate_request(req)

    # ─── Layer 1: Symptom Classification ───────────────────────────────
    predict_req = PredictRequest(
        name=req.name or "anonymous",
        age=req.age or 35,
        symptoms=req.symptoms,
        lat=req.lat,
        lon=req.lon
    )

    try:
        layer1 = await symptom_predict(predict_req)
    except Exception:
        fallback_specialty, fallback_probs = classify_without_model(req.symptoms)
        layer1 = {"primary_doctor": fallback_specialty, "probabilities": fallback_probs}

    # Emergency passthrough
    if layer1.get("primary_doctor") == "EMERGENCY" and any(
        keyword in req.symptoms.lower() for keyword in HARD_EMERGENCY_KEYWORDS
    ):
        return {
            "status": "EMERGENCY",
            "message": "Please call 112 immediately. This appears to be a medical emergency.",
            "confidence_score": 1.0
        }
    if layer1.get("primary_doctor") == "EMERGENCY":
        fallback_specialty, fallback_probs = classify_without_model(req.symptoms)
        layer1 = {"primary_doctor": fallback_specialty, "probabilities": fallback_probs}

    specialty = layer1["primary_doctor"]
    specialty_probability = max(layer1["probabilities"].values()) if layer1["probabilities"] else 0.5

    # Get mapped procedures and urgency
    spec_info = SPECIALTY_MAP.get(specialty, {})
    procedures = spec_info.get("procedures", ["Consultation"])
    primary_procedure = procedures[0]
    urgency = spec_info.get("urgency_level", "medium")

    # ─── Layer 2: Provider Discovery ───────────────────────────────────
    # Default lat/lon to city center if not provided
    city_coords = {
        "hyderabad": (17.3850, 78.4867),
        "mumbai": (19.0760, 72.8777),
        "delhi": (28.6139, 77.2090),
        "bangalore": (12.9716, 77.5946),
        "pune": (18.5204, 73.8567),
        "nagpur": (21.1458, 79.0882),
        "chennai": (13.0827, 80.2707),
        "kolkata": (22.5726, 88.3639),
        "ahmedabad": (23.0225, 72.5714),
        "jaipur": (26.9124, 75.7873),
        "indore": (22.7196, 75.8577),
        "lucknow": (26.8467, 80.9462),
        "bhopal": (23.2599, 77.4126),
        "surat": (21.1702, 72.8311),
        "coimbatore": (11.0168, 76.9558)
    }

    user_lat = req.lat or city_coords.get(req.city.lower(), (20.5937, 78.9629))[0]
    user_lon = req.lon or city_coords.get(req.city.lower(), (20.5937, 78.9629))[1]

    hospitals = rank_hospitals(
        specialty=specialty,
        city=req.city,
        user_lat=user_lat,
        user_lon=user_lon,
        budget_filter=req.budget_preference,
        top_n=3
    )

    hospital_cost_tier = hospitals[0]["cost_tier"] if hospitals else "mid"

    # ─── Layer 3: Cost Estimation ───────────────────────────────────────
    cost_result = estimate_costs(
        procedure=primary_procedure,
        city=req.city,
        age=req.age or 35,
        comorbidities=req.comorbidities or [],
        hospital_cost_tier=hospital_cost_tier
    )

    total_cost_range = cost_result["total_estimated_cost"]

    # ─── Layer 4: Confidence + Responsible Output ───────────────────────
    confidence = compute_confidence(
        specialty_probability=specialty_probability,
        hospital_match_count=len(hospitals),
        cost_data_completeness=1.0 if primary_procedure in get_cost_matrix() else 0.6,
        symptom_length=len(req.symptoms)
    )

    lender = build_lender_signal(confidence, total_cost_range, urgency)

    # Attach per-hospital cost estimate
    for h in hospitals:
        h_costs = estimate_costs(primary_procedure, req.city, req.age or 35, req.comorbidities or [], h["cost_tier"])
        h["estimated_cost_range"] = h_costs["total_estimated_cost"]

    output = build_responsible_output(
        condition=specialty,
        confidence=confidence,
        cost_range=total_cost_range,
        hospitals=hospitals,
        cost_breakdown=cost_result,
        lender_signal=lender,
        risk_notes=cost_result["risk_notes"]
    )

    # Add meta
    output["query_metadata"] = {
        "original_symptoms": req.symptoms,
        "city": req.city,
        "primary_procedure": primary_procedure,
        "icd_codes": spec_info.get("icd_codes", []),
        "all_suggested_procedures": procedures,
        "generated_at": datetime.utcnow().isoformat() + "Z"
    }

    return output


@app.get("/health")
async def health():
    return {"status": "ok", "service": "medroute-api", "version": "1.0.0"}


@app.get("/ready")
async def ready():
    checks = {
        "cost_matrix": len(get_cost_matrix()) > 0,
        "hospital_db": len(get_hospital_db()) > 0,
        "specialty_map": len(get_specialty_map()) > 0,
    }
    all_ok = all(checks.values())
    return {"ready": all_ok, "checks": checks}


@app.get("/procedures")
async def list_procedures():
    matrix = get_cost_matrix()
    return {"procedures": list(matrix.keys()), "count": len(matrix)}
