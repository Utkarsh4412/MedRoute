import json
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"

with open(DATA_DIR / "cost_matrix.json", encoding="utf-8") as f:
    COST_MATRIX = json.load(f)

with open(DATA_DIR / "specialty_to_procedure.json", encoding="utf-8") as f:
    SPECIALTY_MAP = json.load(f)

with open(DATA_DIR / "comorbidity_weights.json", encoding="utf-8") as f:
    COMORBIDITY_WEIGHTS = json.load(f)

HOSPITAL_DB = pd.read_csv(DATA_DIR / "hospital_db.csv")


def get_cost_matrix():
    return COST_MATRIX


def get_specialty_map():
    return SPECIALTY_MAP


def get_comorbidity_weights():
    return COMORBIDITY_WEIGHTS


def get_hospital_db():
    return HOSPITAL_DB
