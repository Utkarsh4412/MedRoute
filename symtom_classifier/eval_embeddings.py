#!/usr/bin/env python3
"""
Evaluate the trained classifier + embeddings.
Creates:
 - evaluation_report.json
 - confusion_matrix.png
 - misclassified_samples.csv (optional)

Usage:
python eval_embeddings.py --csv symptoms_doctor_50k.csv --artifacts artifacts --batch-size 64 --save-misclassified
"""
import argparse
import re
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
import joblib
import matplotlib.pyplot as plt


def clean_text(s: str) -> str:
    """Same cleaning function used during training."""
    if not isinstance(s, str):
        return ""
    s = s.lower()
    s = re.sub(r"[^a-z0-9\\s]", " ", s)
    s = re.sub(r"\\s+", " ", s).strip()
    return s


def batch_encode(model: SentenceTransformer, texts, batch_size=64):
    """Batch embedding for large datasets."""
    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        emb = model.encode(batch, show_progress_bar=False, convert_to_numpy=True)
        embeddings.append(emb)
    if embeddings:
        return np.vstack(embeddings)
    return np.zeros((0, model.get_sentence_embedding_dimension()))


def plot_confusion(cm, labels, out_path):
    plt.figure(figsize=(10, 8))
    plt.imshow(cm, interpolation="nearest", cmap="Blues")
    plt.title("Confusion Matrix")
    plt.colorbar()
    plt.xticks(range(len(labels)), labels, rotation=90)
    plt.yticks(range(len(labels)), labels)
    plt.xlabel("Predicted")
    plt.ylabel("True")
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight")
    plt.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--artifacts", default="artifacts")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--save-misclassified", action="store_true")
    args = parser.parse_args()

    art = Path(args.artifacts)
    if not art.exists():
        raise SystemExit("Artifacts directory not found")

    # Load artifacts
    clf = joblib.load(art / "clf.pkl")
    le = joblib.load(art / "label_encoder.pkl")

    with open(art / "metadata.json") as f:
        metadata = json.load(f)

    model_name = metadata.get("embedding_model", "sentence-transformers/all-MiniLM-L6-v2")
    model = SentenceTransformer(model_name)

    df = pd.read_csv(args.csv)
    text_col = metadata.get("text_col", "symptoms")
    label_col = metadata.get("label_col", "doctor_specialty")

    if text_col not in df.columns or label_col not in df.columns:
        raise SystemExit(f"CSV must contain columns: {text_col}, {label_col}")

    df[text_col] = df[text_col].fillna("").astype(str).map(clean_text)

    X = df[text_col].tolist()
    y = le.transform(df[label_col].astype(str).tolist())

    # Encode
    X_emb = batch_encode(model, X, batch_size=args.batch_size)

    # Predict
    y_pred = clf.predict(X_emb)
    try:
        y_prob = clf.predict_proba(X_emb)
    except Exception:
        y_prob = None

    acc = accuracy_score(y, y_pred)
    crep = classification_report(y, y_pred, target_names=le.classes_, output_dict=True)

    # Save evaluation report
    report = {
        "accuracy": acc,
        "classification_report": crep,
        "num_samples": int(len(X)),
    }
    with open(art / "evaluation_report.json", "w") as f:
        json.dump(report, f, indent=2)

    # Confusion matrix
    cm = confusion_matrix(y, y_pred)
    plot_confusion(cm, list(le.classes_), art / "confusion_matrix.png")

    # Save misclassified samples (optional)
    if args.save_misclassified:
        rows = []
        for i, (txt, true, pred) in enumerate(zip(X, y, y_pred)):
            if true != pred:
                row = {
                    "symptoms": txt,
                    "true_label": le.classes_[true],
                    "pred_label": le.classes_[pred],
                }
                if y_prob is not None:
                    row["pred_prob"] = float(max(y_prob[i]))
                rows.append(row)

        pd.DataFrame(rows).to_csv(art / "misclassified_samples.csv", index=False)

    print(f"Accuracy: {acc:.4f}")
    print("Saved evaluation_report.json + confusion_matrix.png")


if __name__ == "__main__":
    main()
