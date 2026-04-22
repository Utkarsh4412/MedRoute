const apiBase = "http://127.0.0.1:8000";
const resultEl = document.getElementById("result");
const submitBtn = document.getElementById("submitBtn");

function rupees(range) {
  if (!Array.isArray(range) || range.length !== 2) return "N/A";
  return `INR ${range[0].toLocaleString("en-IN")} - ${range[1].toLocaleString("en-IN")}`;
}

function lenderClass(signal) {
  if (signal === "pre_approve_eligible") return "green";
  if (signal === "soft_eligible") return "yellow";
  return "red";
}

function certaintyClass(label) {
  if (label === "moderate_confidence") return "green";
  if (label === "low_confidence") return "yellow";
  return "red";
}

function renderLenderSignal(signal) {
  const colors = {
    pre_approve_eligible: "#10B981",
    soft_eligible: "#F59E0B",
    needs_review: "#EF4444"
  };
  const safeSignal = signal || { signal: "needs_review", message: "", max_loan_indicative: 0 };
  return `
    <div id="lender-signal" class="card" style="border-left:4px solid ${colors[safeSignal.signal] || "#666"}">
      <h3>Lender Signal</h3>
      <div class="signal-badge" style="color:${colors[safeSignal.signal] || "#666"}">
        ${(safeSignal.signal || "needs_review").replace(/_/g, " ").toUpperCase()}
      </div>
      <p>${safeSignal.message || ""}</p>
      <p><strong>Max indicative loan: INR ${(safeSignal.max_loan_indicative || 0).toLocaleString("en-IN")}</strong></p>
    </div>
  `;
}

function renderCostBreakdown(costEstimate) {
  if (!costEstimate) {
    return `<div class="card"><h3>Cost Breakdown</h3><p>N/A</p></div>`;
  }
  const breakdown = costEstimate.breakdown || {};
  const rows = Object.entries(breakdown)
    .map(([key, range]) => `<tr><td>${key.replace(/_/g, " ")}</td><td>${rupees(range)}</td></tr>`)
    .join("");
  return `
    <div class="card">
      <details open>
        <summary>Cost breakdown accordion</summary>
        <table style="width:100%; border-collapse:collapse;">
          <thead><tr><th style="text-align:left">Component</th><th style="text-align:left">Range</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
        <p><b>Total estimated:</b> ${rupees(costEstimate.total_estimated_cost)}</p>
      </details>
    </div>
  `;
}

function renderResponse(data) {
  if (data.status === "EMERGENCY") {
    resultEl.innerHTML = `<div class="card"><h3>Emergency</h3><p>${data.message}</p></div>`;
    return;
  }

  const hospitalsHtml = (data.recommended_hospitals || []).map((h) => `
    <div class="card">
      <h4>${h.name}</h4>
      <div class="row">
        <span class="badge">${h.cost_tier}</span>
        <span class="badge">${h.nabh ? "NABH" : "Non-NABH"}</span>
      </div>
      <p>Rating: <b>${h.rating}</b> | Distance: <b>${h.distance_km} km</b></p>
      <p>Estimated cost: <b>${rupees(h.estimated_cost_range)}</b></p>
      <p class="small">${h.description}</p>
      <ul>${(h.strengths || []).map((s) => `<li>${s}</li>`).join("")}</ul>
    </div>
  `).join("");

  resultEl.innerHTML = `
    <div class="card">
      <h3>Condition Card</h3>
      <p>Mapped condition: <b>${data.condition_mapped}</b></p>
      <p>ICD codes: <b>${(data.query_metadata?.icd_codes || []).join(", ") || "N/A"}</b></p>
      <div class="row">
        <span class="badge ${certaintyClass(data.certainty_label)}">${data.certainty_label}</span>
        <span class="badge">confidence: ${data.confidence_score}</span>
      </div>
    </div>

    <div class="grid">${hospitalsHtml}</div>

    ${renderCostBreakdown(data.cost_estimate)}
    ${renderLenderSignal(data.lender_signal)}

    <div class="card">
      <h3>Risk Notes</h3>
      <ul>${(data.risk_notes || []).map((n) => `<li>${n}</li>`).join("") || "<li>None</li>"}</ul>
    </div>

    <div class="card small">
      <h3>Disclaimers</h3>
      <ul>${(data.disclaimers || []).map((d) => `<li>${d}</li>`).join("")}</ul>
    </div>
  `;
}

submitBtn.addEventListener("click", async () => {
  submitBtn.disabled = true;
  resultEl.innerHTML = `<div class="card">Loading...</div>`;
  try {
    const payload = {
      symptoms: document.getElementById("symptoms").value,
      city: document.getElementById("city").value,
      age: Number(document.getElementById("age").value || 35),
      name: document.getElementById("name").value || "anonymous",
      comorbidities: (document.getElementById("comorbidities").value || "").split(",").map((s) => s.trim()).filter(Boolean),
      budget_preference: document.getElementById("budget").value || null
    };
    const res = await fetch(`${apiBase}/navigate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      let errBody = {};
      try {
        errBody = await res.json();
      } catch (_) {
        errBody = {};
      }
      throw new Error(errBody.detail ? JSON.stringify(errBody.detail) : `HTTP ${res.status}`);
    }
    const data = await res.json();
    renderResponse(data);
  } catch (err) {
    resultEl.innerHTML = `<div class="card">Request failed: ${err.message}</div>`;
  } finally {
    submitBtn.disabled = false;
  }
});
