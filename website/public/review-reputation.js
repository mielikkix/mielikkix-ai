// The /demo/review-reputation page's logic. External file (not an inline
// <script>) for the same Content-Security-Policy reason every other
// website/public/*.js file is -- see voice-receptionist.js's own comment
// on this.
const { apiUrl } = document.currentScript.dataset;

const reviewInput = document.getElementById("reviewInput");
const toneSelect = document.getElementById("toneSelect");
const analyzeBtn = document.getElementById("analyzeBtn");
const resultWrap = document.getElementById("resultWrap");

document.querySelectorAll(".example-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    reviewInput.value = btn.dataset.text;
    reviewInput.focus();
  });
});

const SENTIMENT_CLASSES = {
  positive: "bg-emerald-50 text-emerald-700",
  neutral: "bg-slate-100 text-slate-600",
  negative: "bg-red-50 text-red-700",
  mixed: "bg-amber-50 text-amber-700",
};

const PRIORITY_CLASSES = {
  low: "bg-slate-100 text-slate-500",
  medium: "bg-amber-50 text-amber-700",
  high: "bg-orange-50 text-orange-700",
  critical: "bg-red-100 text-red-800",
};

function badge(text, className) {
  return `<span class="rounded-full px-2.5 py-0.5 text-xs font-medium ${className}">${text}</span>`;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function renderResult(data) {
  const topicsLine = data.topics.length ? escapeHtml(data.topics.join(", ")) : "-";
  const positiveLine = data.positive_points.length
    ? `<p class="mt-1 text-sm text-slate-700"><span class="font-medium text-emerald-600">Positive:</span> ${escapeHtml(data.positive_points.join("; "))}</p>`
    : "";
  const negativeLine = data.negative_points.length
    ? `<p class="mt-1 text-sm text-slate-700"><span class="font-medium text-red-600">Negative:</span> ${escapeHtml(data.negative_points.join("; "))}</p>`
    : "";
  const escalationBox = data.requires_human_review
    ? `<div class="mt-3 rounded-xl bg-red-50 p-3 text-sm text-red-700">
         <strong>Flagged for a human</strong> -- escalation reason: <strong>${escapeHtml(data.escalation_reason || "unknown")}</strong>.
         This agent never tries to resolve something like this on its own.
       </div>`
    : "";

  resultWrap.innerHTML = `
    <div class="rounded-3xl border border-slate-100 bg-white p-6 shadow-sm">
      <div class="flex flex-wrap items-center gap-2">
        ${badge(data.sentiment, SENTIMENT_CLASSES[data.sentiment] || "bg-slate-100 text-slate-600")}
        ${badge(data.priority + " priority", PRIORITY_CLASSES[data.priority] || "bg-slate-100 text-slate-600")}
      </div>
      <p class="mt-3 text-sm text-slate-500"><span class="font-medium text-slate-600">Topics:</span> ${topicsLine}</p>
      ${data.primary_issue ? `<p class="text-sm text-slate-500"><span class="font-medium text-slate-600">Primary issue:</span> ${escapeHtml(data.primary_issue)}</p>` : ""}
      ${positiveLine}
      ${negativeLine}
      ${escalationBox}
    </div>
    <div class="rounded-3xl border border-slate-100 bg-white p-6 shadow-sm">
      <p class="text-sm font-semibold text-slate-700">Drafted response <span class="font-normal text-slate-400">(${escapeHtml(data.response_tone)} tone)</span></p>
      <p class="mt-2 rounded-2xl bg-slate-50 p-3.5 text-sm text-slate-800">${escapeHtml(data.response_text)}</p>
      <p class="mt-2 text-xs text-slate-400">A human always reviews and approves before anything like this goes out for real -- this agent never auto-publishes.</p>
    </div>
  `;
  resultWrap.classList.remove("hidden");
}

analyzeBtn.addEventListener("click", async () => {
  const text = reviewInput.value.trim();
  if (!text) {
    reviewInput.focus();
    return;
  }

  analyzeBtn.disabled = true;
  analyzeBtn.textContent = "Analyzing...";
  resultWrap.classList.add("hidden");

  try {
    const resp = await fetch(`${apiUrl}/api/agents/reviews/demo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ review_text: text, tone: toneSelect.value }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || `Request failed (${resp.status})`);
    renderResult(data);
  } catch (err) {
    console.error("Review demo error:", err);
    resultWrap.innerHTML = `<div class="rounded-3xl border border-red-100 bg-red-50 p-6 text-sm text-red-700">Sorry, something went wrong reaching the server. Please try again.</div>`;
    resultWrap.classList.remove("hidden");
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = "Analyze & draft a response";
  }
});
