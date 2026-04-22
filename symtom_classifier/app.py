#!/usr/bin/env python3
"""
FastAPI backend for the Symptom Classifier.

Endpoints:
 - POST /predict
 - POST /session/finish
 - GET  /model/health

Behavior:
 - Auto-creates artifacts/, sessions/, outputs/
 - Uses the same clean_text function as training/eval
 - Appends each /predict call to sessions/<sanitized_name>_active.jsonl
 - Moves active session to outputs/<name>/session_<timestamp>.jsonl on /session/finish
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime
import re
import json
import joblib
import numpy as np
import os
import shutil
import uuid

# Directories (auto-created)
BASE_DIR = Path(__file__).resolve().parent
ARTIFACTS = BASE_DIR / "artifacts"
SESSIONS = BASE_DIR / "sessions"
OUTPUTS = BASE_DIR / "outputs"

for d in (ARTIFACTS, SESSIONS, OUTPUTS):
    d.mkdir(parents=True, exist_ok=True)

# Globals for artifacts (loaded lazily)
_clf = None
_le = None
_embedding_model = None
_metadata = {}
_specialty_to_procedure = {}

# Try to load artifacts now if present
def _try_load_artifacts():
    global _clf, _le, _embedding_model, _metadata
    try:
        if (ARTIFACTS / "clf.pkl").exists():
            _clf = joblib.load(ARTIFACTS / "clf.pkl")
        if (ARTIFACTS / "label_encoder.pkl").exists():
            _le = joblib.load(ARTIFACTS / "label_encoder.pkl")
        if (ARTIFACTS / "metadata.json").exists():
            with open(ARTIFACTS / "metadata.json", "r", encoding="utf-8") as f:
                _metadata = json.load(f)
        # load embedding model if metadata present
        if _metadata.get("embedding_model"):
            try:
                from sentence_transformers import SentenceTransformer
                _embedding_model = SentenceTransformer(_metadata["embedding_model"])
            except Exception:
                _embedding_model = None
    except Exception:
        # don't fail app startup; endpoints will return helpful errors
        _clf = None
        _le = None
        _embedding_model = None
        _metadata = {}

_try_load_artifacts()
try:
    with open(Path(__file__).resolve().parent.parent / "data" / "specialty_to_procedure.json", "r", encoding="utf-8") as _f:
        _specialty_to_procedure = json.load(_f)
except Exception:
    _specialty_to_procedure = {}

# Cleaning function MUST match training/eval
def clean_text(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def sanitize_name(name: str) -> str:
    # allow alnum, underscore, hyphen; replace others with underscore
    if not isinstance(name, str):
        return "unknown"
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name)

def check_emergency(text: str) -> bool:
    """
    Check for emergency keywords in the input text.
    Returns True if an emergency is detected.
    """
    # Simple keyword list for emergencies
    keywords = [
        "heart attack", "stroke", "chest pain", "difficulty breathing",
        "unconscious", "severe bleeding", "suicide", "seizure", "collapse"
    ]
    text_lower = text.lower()
    return any(k in text_lower for k in keywords)

def ensure_models_loaded():
    """
    Ensure classifier, label encoder and embedding model are loaded.
    Raises RuntimeError with advice if something is missing.
    """
    global _clf, _le, _embedding_model, _metadata
    if _clf is None or _le is None:
        raise RuntimeError("Model artifacts not found in ./artifacts. Run training to produce clf.pkl and label_encoder.pkl.")
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as e:
            raise RuntimeError(f"Failed to import sentence-transformers runtime: {e}")
        # try to load default embedding model from metadata or fallback to the required model
        model_name = _metadata.get("embedding_model", "sentence-transformers/all-MiniLM-L6-v2")
        try:
            _embedding_model = SentenceTransformer(model_name)
        except Exception as e:
            raise RuntimeError(f"Failed to load embedding model '{model_name}': {e}")

# Pydantic request model for predict
class PredictRequest(BaseModel):
    name: str = Field(...)
    age: int = Field(..., ge=0)
    symptoms: str = Field(...)
    lat: Optional[float] = None
    lon: Optional[float] = None

app = FastAPI(title="Symptom Classifier")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/model/health")
async def model_health():
    """
    Returns whether artifacts exist and some metadata.
    Useful for the frontend to detect readiness.
    """
    artifacts_exist = (ARTIFACTS / "clf.pkl").exists() and (ARTIFACTS / "label_encoder.pkl").exists()
    embedding = _metadata.get("embedding_model")
    return {
        "artifacts_exist": bool(artifacts_exist),
        "embedding_model": embedding,
        "num_classes": _metadata.get("num_classes"),
    }

@app.post("/predict")
async def predict(req: PredictRequest):
    """
    Predict primary doctor specialty and return probabilities.
    Appends one JSON line to sessions/<uuid>_active.jsonl
    """
    # Fix: Emergency check - return immediately if keywords found
    if check_emergency(req.symptoms):
        return {
            "primary_doctor": "EMERGENCY",
            "probabilities": {},
            "suggested_procedures": [],
            "icd_codes": [],
            "nearby": []
        }

    try:
        ensure_models_loaded()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Fix: Use UUID derived from name
    session_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, req.name))
    
    # Clean symptoms using the same function
    text = clean_text(req.symptoms)

    # Embed and predict
    try:
        emb = _embedding_model.encode([text], convert_to_numpy=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to encode text: {e}")

    try:
        probs = _clf.predict_proba(emb)[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to predict: {e}")

    top_idx = int(np.argmax(probs))
    primary = str(_le.classes_[top_idx])

    # Build probability map (string keys)
    prob_map = {str(label): float(p) for label, p in zip(_le.classes_, probs)}

    # Append to session file
    SESSIONS.mkdir(parents=True, exist_ok=True)
    session_file = SESSIONS / f"{session_uuid}_active.jsonl"
    
    # Fix: Remove logging of PHI (name, age, lat, lon)
    record = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        # "name": req.name, (Removed for privacy)
        # "age": req.age,   (Removed for privacy)
        "symptoms": req.symptoms,
        "primary_doctor": primary,
        "probabilities": prob_map,
        # "lat": req.lat,   (Removed for privacy)
        # "lon": req.lon,   (Removed for privacy)
    }
    try:
        with open(session_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write session file: {e}")

    procedures = _specialty_to_procedure.get(primary, {}).get("procedures", [])
    icd_codes = _specialty_to_procedure.get(primary, {}).get("icd_codes", [])
    return {
        "primary_doctor": primary,
        "probabilities": prob_map,
        "suggested_procedures": procedures,
        "icd_codes": icd_codes,
        "nearby": []
    }

@app.post("/session/finish")
async def session_finish(payload: Dict[str, Any]):
    """
    Move sessions/<uuid>_active.jsonl -> outputs/<uuid>/session_<timestamp>.jsonl
    Expects JSON: { "name": "..." }
    """
    name = payload.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Missing 'name' in payload")

    # Fix: Use UUID derived from name
    session_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, name))
    session_file = SESSIONS / f"{session_uuid}_active.jsonl"
    if not session_file.exists():
        raise HTTPException(status_code=404, detail="Active session file not found")

    out_dir = OUTPUTS / session_uuid
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dest = out_dir / f"session_{ts}.jsonl"
    try:
        shutil.move(str(session_file), str(dest))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to move session file: {e}")

    return {"moved_to": str(dest)}

# Helpful root
@app.get("/")
async def root():
    return {"status": "ok", "info": "Symptom Classifier API. Check /model/health"}
