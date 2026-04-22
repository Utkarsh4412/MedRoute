from fastapi.testclient import TestClient
from main_api import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready():
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["ready"] == True


def test_navigate_cardiac():
    r = client.post("/navigate", json={
        "symptoms": "chest pain while walking upstairs, breathless easily",
        "city": "Hyderabad",
        "age": 55,
        "comorbidities": ["diabetes"]
    })
    assert r.status_code == 200
    body = r.json()
    assert "confidence_score" in body
    assert "recommended_hospitals" in body
    assert "cost_estimate" in body
    assert body["confidence_score"] <= 0.92
    total = body["cost_estimate"]["total_estimated_cost"]
    assert total[0] < total[1]


def test_navigate_emergency():
    r = client.post("/navigate", json={
        "symptoms": "heart attack severe chest pain radiating to arm",
        "city": "Mumbai"
    })
    assert r.status_code == 200
    assert r.json()["status"] == "EMERGENCY"


def test_navigate_invalid_age():
    r = client.post("/navigate", json={
        "symptoms": "knee pain",
        "city": "Delhi",
        "age": 999
    })
    assert r.status_code == 422


def test_navigate_short_symptoms():
    r = client.post("/navigate", json={
        "symptoms": "ow",
        "city": "Mumbai"
    })
    assert r.status_code == 422


def test_navigate_unknown_comorbidity():
    r = client.post("/navigate", json={
        "symptoms": "knee pain for several months",
        "city": "Pune",
        "comorbidities": ["dragon_blood_disease"]
    })
    assert r.status_code == 422


def test_navigate_tier2_city():
    r = client.post("/navigate", json={
        "symptoms": "severe stomach pain vomiting",
        "city": "Nagpur",
        "age": 45
    })
    assert r.status_code == 200
    assert "cost_estimate" in r.json()


def test_navigate_has_lender_signal():
    r = client.post("/navigate", json={
        "symptoms": "chest pain while climbing stairs shortness of breath",
        "city": "Hyderabad",
        "age": 50
    })
    body = r.json()
    assert "lender_signal" in body
    assert body["lender_signal"]["signal"] in ["pre_approve_eligible", "soft_eligible", "needs_review"]


def test_navigate_has_disclaimers():
    r = client.post("/navigate", json={
        "symptoms": "persistent headache and dizziness for two weeks",
        "city": "Bangalore"
    })
    body = r.json()
    assert "disclaimers" in body
    assert len(body["disclaimers"]) >= 4
