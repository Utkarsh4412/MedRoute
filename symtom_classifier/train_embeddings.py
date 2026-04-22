#!/usr/bin/env python3
"""
Train embeddings + Logistic Regression classifier.
Saves artifacts/clf.pkl, artifacts/label_encoder.pkl, artifacts/metadata.json

Usage example:
python train_embeddings.py --csv symptoms_doctor_50k.csv --out artifacts --text-col symptoms --label-col doctor_specialty --test-size 0.2
"""
import argparse
import os
import re
import json
from time import time
from pathlib import Path

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import joblib


def clean_text(s: str) -> str:
    """Lowercase, remove special chars (keep alphanumerics and spaces), collapse spaces."""
    if not isinstance(s, str):
        return ""
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def batch_encode(model: SentenceTransformer, texts, batch_size=64):
    """Encode texts in batches and return stacked numpy array."""
    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        emb = model.encode(batch, show_progress_bar=False, convert_to_numpy=True)
        embeddings.append(emb)
    if embeddings:
        return np.vstack(embeddings)
    # If no texts, return empty with correct dimension
    return np.zeros((0, model.get_sentence_embedding_dimension()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Path to CSV file")
    parser.add_argument("--out", default="artifacts", help="Output artifacts directory")
    parser.add_argument("--text-col", default="symptoms", help="Text column name (must be 'symptoms')")
    parser.add_argument("--label-col", default="doctor_specialty", help="Label column name (must be 'doctor_specialty')")
    parser.add_argument("--test-size", type=float, default=0.2, help="Test size fraction")
    parser.add_argument("--batch-size", type=int, default=64, help="Embedding batch size")
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    # enforce required column names
    if args.text_col not in df.columns or args.label_col not in df.columns:
        raise SystemExit(f"CSV must contain columns: {args.text_col}, {args.label_col}")

    # Clean text using the same function required by the spec
    df[args.text_col] = df[args.text_col].fillna("").astype(str).map(clean_text)

    X = df[args.text_col].tolist()
    y = df[args.label_col].astype(str).tolist()

    # Label encoding
    le = LabelEncoder()
    y_enc = le.fit_transform(y)

    # Train/test split (stratify to preserve label distribution)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y_enc, test_size=args.test_size, stratify=y_enc, random_state=42
    )

    print("Loading embedding model: sentence-transformers/all-MiniLM-L6-v2")
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    print("Encoding train set...")
    t0 = time()
    X_train_emb = batch_encode(model, X_train, batch_size=args.batch_size)
    X_test_emb = batch_encode(model, X_test, batch_size=args.batch_size)
    print(f"Embeddings done in {time()-t0:.1f}s")

    print("Training LogisticRegression(max_iter=1000, class_weight='balanced')")
    clf = LogisticRegression(max_iter=1000, class_weight="balanced")
    clf.fit(X_train_emb, y_train)

    y_pred = clf.predict(X_test_emb)

    acc = accuracy_score(y_test, y_pred)
    print(f"Test accuracy: {acc:.4f}")
    print("Classification report:")
    # Print full report (may be large if many classes)
    print(classification_report(y_test, y_pred, target_names=le.classes_))

    # Save artifacts
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(clf, out_dir / "clf.pkl")
    joblib.dump(le, out_dir / "label_encoder.pkl")

    metadata = {
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        "classifier": "LogisticRegression(max_iter=1000, class_weight='balanced')",
        "text_col": args.text_col,
        "label_col": args.label_col,
        "test_size": args.test_size,
        "batch_size": args.batch_size,
        "num_classes": int(len(le.classes_)),
    }
    with open(out_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"Artifacts saved to {out_dir.resolve()}")


if __name__ == "__main__":
    main()
