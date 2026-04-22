import React, { useState } from "react";

/**
 * Complete App.js with:
 * - age required (empty initial)
 * - invalid symptom detection
 * - single-symptom -> top-1 (fever -> GP)
 * - multi-symptom -> top-3
 * - session logging via /predict and /session/finish
 */

/* ---------- Simple styles ---------- */
const containerStyle = {
  maxWidth: 900,
  margin: "28px auto",
  fontFamily:
    "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial",
  color: "#111",
  lineHeight: 1.4,
  padding: 16,
};
const cardStyle = {
  background: "#fff",
  border: "1px solid #e6e6e6",
  borderRadius: 8,
  padding: 18,
  boxShadow: "0 6px 18px rgba(20,20,20,0.04)",
};
const labelStyle = { display: "block", marginBottom: 6, fontWeight: 600 };
const inputStyle = { width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #ccc" };
const textareaStyle = { width: "100%", minHeight: 120, padding: "8px 10px", borderRadius: 6, border: "1px solid #ccc" };
const btn = { padding: "8px 12px", borderRadius: 6, cursor: "pointer", border: "none" };
const primaryBtn = { ...btn, background: "#0b76ff", color: "#fff" };
const ghostBtn = { ...btn, background: "#f2f5f9", color: "#111", marginLeft: 8 };

/* ---------- Helper utilities ---------- */
function normalizeSymptomsText(text) {
  return (text || "").trim().toLowerCase();
}

function countSymptoms(text) {
  if (!text || !text.trim()) return 0;
  const parts = text
    .split(/[\n,;]+| and /i)
    .map((p) => p.trim())
    .filter(Boolean);
  return parts.length;
}

function isFeverLike(text) {
  if (!text) return false;
  const s = normalizeSymptomsText(text);
  const feverTerms = ["fever", "feverish", "high temperature", "temperature", "raised temperature"];
  return feverTerms.includes(s);
}

/* Basic invalid symptom detection (frontend) */
function isInvalidSymptom(text) {
  if (!text) return true;
  const s = text.trim().toLowerCase();

  // too short
  if (s.length < 3) return true;

  // no alphabetic chars
  if (!/[a-z]/.test(s)) return true;

  // common garbage words (expand as needed)
  const garbage = ["hi", "hello", "ok", "hii", "hey", "yo", "asdf", "test", "typing", "okey","abcd","123","nothing","n/a","na","nil","none","symptoms","symptom", "data","info","information","sample","example","lorem ipsum","asdfghjkl","qwerty"," ","",".","..","...","????","!!!","??","!!"];
  if (garbage.includes(s)) return true;

  return false;
}

/* ---------- App component ---------- */
export default function App() {
  const [name, setName] = useState("");
  const [age, setAge] = useState(""); // empty so user must enter age
  const [symptoms, setSymptoms] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [displayResult, setDisplayResult] = useState(null); // what we show
  const [rawBackendResult, setRawBackendResult] = useState(null);

  async function handlePredict() {
    setError(null);
    setDisplayResult(null);

    // Basic validations
    if (!name.trim() || !symptoms.trim()) {
      setError("Please enter name and symptoms.");
      return;
    }

    // invalid symptom detection
    if (isInvalidSymptom(symptoms)) {
      setError("Invalid symptom. Please enter actual medical symptoms.");
      return;
    }

    // age validation: required and positive number
    if (!age || isNaN(Number(age)) || Number(age) <= 0) {
      setError("Please enter a valid age (number greater than 0).");
      return;
    }

    setLoading(true);

    const symCount = countSymptoms(symptoms);
    const singleFever = symCount === 1 && isFeverLike(symptoms);
    const singleSymptom = symCount === 1;

    try {
      // Call backend so session is logged
      const res = await fetch("/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, age: Number(age), symptoms }),
      });

      if (!res.ok) {
        const txt = await res.text();
        throw new Error(txt || `HTTP ${res.status}`);
      }

      const data = await res.json();
      setRawBackendResult(data);

      // Decide what to display
      if (singleFever) {
        // override UI: show GP for single fever-like symptom
        setDisplayResult({
          primary_doctor: "General Physician",
          probabilities: { "General Physician": 1.0 },
        });
        return;
      }

      const entries = Object.entries(data.probabilities || {});
      entries.sort((a, b) => b[1] - a[1]);

      if (singleSymptom) {
        // Show top-1 only
        const top1 = entries[0];
        const top1Map = top1 ? { [top1[0]]: top1[1] } : {};
        setDisplayResult({
          primary_doctor: top1 ? top1[0] : data.primary_doctor,
          probabilities: top1Map,
        });
      } else {
        // multiple symptoms -> top-3
        const top3 = entries.slice(0, 3);
        const top3Map = Object.fromEntries(top3);
        setDisplayResult({
          primary_doctor: data.primary_doctor,
          probabilities: top3Map,
        });
      }
    } catch (err) {
      setError(String(err));
      setRawBackendResult(null);
      setDisplayResult(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleExit() {
    setError(null);
    if (!name.trim()) {
      setError("Enter name to finish session.");
      return;
    }
    try {
      const res = await fetch("/session/finish", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(txt || `HTTP ${res.status}`);
      }
      setDisplayResult(null);
      setName("");
      setAge("");
      setSymptoms("");
      alert("Session finished and moved to outputs/");
    } catch (err) {
      setError(String(err));
    }
  }

  const shownTop = displayResult
    ? Object.entries(displayResult.probabilities).sort((a, b) => b[1] - a[1])
    : [];

  return (
    <div style={containerStyle}>
      <div style={cardStyle}>
        <h1 style={{ margin: 0, marginBottom: 8 }}>Symptom Classifier</h1>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 120px", gap: 12, alignItems: "start" }}>
          <div>
            <label style={labelStyle}>Name</label>
            <input
              style={inputStyle}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Your name"
            />
          </div>

          <div>
            <label style={labelStyle}>Age</label>
            <input
              style={inputStyle}
              type="number"
              value={age}
              onChange={(e) => setAge(e.target.value)}
              placeholder="Enter age"
            />
          </div>
        </div>

        <div style={{ marginTop: 12 }}>
          <label style={labelStyle}>Symptoms</label>
          <textarea
            style={textareaStyle}
            placeholder="List symptoms separated by commas or new lines (e.g. fever, cough)"
            value={symptoms}
            onChange={(e) => setSymptoms(e.target.value)}
          />
          <div style={{ marginTop: 10 }}>
            <button style={primaryBtn} onClick={handlePredict} disabled={loading}>
              {loading ? "Requesting..." : "Get Recommendation"}
            </button>
            <button style={ghostBtn} onClick={handleExit}>
              Exit Session
            </button>
          </div>
        </div>

        {error && (
          <div style={{ marginTop: 12, color: "#b00020", fontWeight: 600 }}>
            Error: {error}
          </div>
        )}

        {displayResult && (
          <div style={{ marginTop: 18 }}>
            <h3 style={{ marginBottom: 6 }}>
              Primary Doctor: <span style={{ color: "#0b76ff" }}>{displayResult.primary_doctor}</span>
            </h3>

            <div style={{ marginTop: 6 }}>
              <strong>Top suggestion{shownTop.length > 1 ? "s" : ""}:</strong>
              <ul>
                {shownTop.map(([label, prob]) => (
                  <li key={label}>
                    <strong>{label}</strong>: {Number(prob).toFixed(3)}
                  </li>
                ))}
              </ul>
            </div>

            <div style={{ marginTop: 8, color: "#666", fontSize: 13 }}>
              <em>
                Note: results shown are {shownTop.length === 1 ? "the top suggestion" : "the top 3 suggestions"} (
                model predicted: {rawBackendResult ? rawBackendResult.primary_doctor : "—"}).
              </em>
            </div>
          </div>
        )}

        <div style={{ marginTop: 16, color: "#666", fontSize: 13 }}>
          Tip: separate multiple symptoms with commas or new lines for better suggestions.
        </div>
      </div>
    </div>
  );
}
