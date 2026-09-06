// The /demo/review-reputation page's logic. External file (not an inline
// <script>) for the same Content-Security-Policy reason every other
// website/public/*.js file is -- see voice-receptionist.js's own comment
// on this.
const { apiUrl } = document.currentScript.dataset;

const reviewInput = document.getElementById("reviewInput");
const reviewError = document.getElementById("reviewError");
const analyzeBtn = document.getElementById("analyzeBtn");
const analyzeStatus = document.getElementById("analyzeStatus");
const resultWrap = document.getElementById("resultWrap");

document.querySelectorAll(".example-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    reviewInput.value = btn.dataset.text;
    reviewError.classList.add("hidden");
    reviewInput.focus();
  });
});

const SENTIMENT_LABELS = { positive: "Positive", neutral: "Neutral", negative: "Negative", mixed: "Mixed" };
const SENTIMENT_CLASSES = {
  positive: "bg-emerald-50 text-emerald-700",
  neutral: "bg-slate-100 text-slate-600",
  negative: "bg-red-50 text-red-700",
  mixed: "bg-amber-50 text-amber-700",
};

// The real agent (app/services/review_service.py) analyzes sentiment,
// topics and priority but doesn't classify a review's "intent" -- this is
// a simple, honest heuristic over the same analysis the demo endpoint
// already returns (plus the raw review text, for the question check),
// never a second LLM call or fabricated data.
const INTENT_CLASSES = {
  Praise: "bg-emerald-50 text-emerald-700",
  Complaint: "bg-red-50 text-red-700",
  Question: "bg-blue-50 text-blue-700",
  Suggestion: "bg-amber-50 text-amber-700",
};

function detectIntent(reviewText, analysis) {
  const looksLikeQuestion =
    /\?/.test(reviewText) && /\b(what|how|why|when|where|is|are|do|does|can|could|would|will|should)\b/i.test(reviewText);
  if (looksLikeQuestion) return "Question";
  if (analysis.sentiment === "positive" && analysis.negative_points.length === 0) return "Praise";
  if (analysis.negative_points.length > 0 || analysis.primary_issue) return "Complaint";
  if (analysis.sentiment === "neutral") return "Suggestion";
  if (analysis.sentiment === "mixed") return "Complaint";
  return "Praise";
}

const ACTION_CLASSES = {
  red: "border-red-100 bg-red-50 text-red-700",
  amber: "border-amber-100 bg-amber-50 text-amber-700",
  emerald: "border-emerald-100 bg-emerald-50 text-emerald-700",
  slate: "border-slate-100 bg-slate-50 text-slate-600",
};

// A short business recommendation grounded only in fields the demo
// endpoint already returned (requires_human_review, priority, sentiment) --
// same "never invent data" convention review_service.py's own insights/
// trends functions follow, just applied to a single review's recommended
// next step instead of an aggregate stat.
function recommendedAction(analysis) {
  if (analysis.requires_human_review) {
    const reason = analysis.escalation_reason && analysis.escalation_reason !== "unknown"
      ? ` (flagged as: ${analysis.escalation_reason.replace(/_/g, " ")})`
      : "";
    return {
      label: "Investigate before responding",
      text: `Don't rely on an automated reply here -- have a team member look into this directly${reason}.`,
      tone: "red",
    };
  }
  if (analysis.sentiment === "positive") {
    return {
      label: "Thank the customer",
      text: "Post the response publicly and thank them -- great feedback like this is worth sharing with the team.",
      tone: "emerald",
    };
  }
  if (analysis.sentiment === "negative" || analysis.sentiment === "mixed") {
    if (analysis.priority === "high" || analysis.priority === "critical") {
      return {
        label: "Follow up privately & resolve",
        text: "Reach out to the customer directly to make it right, then post the response publicly.",
        tone: "amber",
      };
    }
    return {
      label: "Offer to resolve the issue",
      text: "Post the response, and follow up directly if the customer replies.",
      tone: "amber",
    };
  }
  return {
    label: "Acknowledge the feedback",
    text: "Post the response, and note this as a small opportunity to improve.",
    tone: "slate",
  };
}

function badge(text, className) {
  return `<span class="rounded-full px-2.5 py-1 text-xs font-semibold ${className}">${text}</span>`;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function bulletList(items, className) {
  return `<ul class="mt-1.5 space-y-1">${items
    .map((item) => `<li class="flex gap-1.5 text-sm text-slate-700"><span class="${className}">&bull;</span>${escapeHtml(item)}</li>`)
    .join("")}</ul>`;
}

function renderResult(reviewText, analysis, responseText, responseTone) {
  const intent = detectIntent(reviewText, analysis);
  const action = recommendedAction(analysis);

  const hasIssues = Boolean(analysis.primary_issue) || analysis.negative_points.length > 0;
  const hasHighlights = analysis.positive_points.length > 0;

  // One "AI Review Insights" block, with a sub-heading per side that's
  // actually present -- both can show for a mixed review, only one for a
  // purely positive/negative one. Same underlying positive_points/
  // negative_points/primary_issue the backend already returns; this is
  // presentation only, no new analysis.
  const highlightsSubBlock = hasHighlights
    ? `<div class="mt-2.5">
         <p class="text-xs font-semibold text-emerald-600">What they liked</p>
         ${bulletList(analysis.positive_points, "text-emerald-500")}
       </div>`
    : "";

  const issuesSubBlock = hasIssues
    ? `<div class="mt-3">
         <p class="text-xs font-semibold text-red-600">What needs attention</p>
         ${analysis.primary_issue ? `<p class="mt-1.5 text-sm font-medium text-slate-800">${escapeHtml(analysis.primary_issue)}</p>` : ""}
         ${analysis.negative_points.length ? bulletList(analysis.negative_points, "text-red-500") : ""}
       </div>`
    : "";

  const insightsBlock = `
    <div class="mt-4">
      <p class="text-xs font-semibold uppercase tracking-wide text-slate-400">AI Review Insights</p>
      ${highlightsSubBlock}
      ${issuesSubBlock}
      ${!hasIssues && !hasHighlights ? `<p class="mt-1.5 text-sm text-slate-500">No specific issues or highlights were called out in this review.</p>` : ""}
    </div>`;

  resultWrap.innerHTML = `
    <div class="rounded-3xl border border-slate-100 bg-white p-6 shadow-sm">
      <div class="flex flex-wrap gap-4">
        <div>
          <p class="text-xs font-semibold uppercase tracking-wide text-slate-400">Sentiment</p>
          <div class="mt-1.5">${badge(SENTIMENT_LABELS[analysis.sentiment] || analysis.sentiment, SENTIMENT_CLASSES[analysis.sentiment] || "bg-slate-100 text-slate-600")}</div>
        </div>
        <div>
          <p class="text-xs font-semibold uppercase tracking-wide text-slate-400">Customer intent</p>
          <div class="mt-1.5">${badge(intent, INTENT_CLASSES[intent])}</div>
        </div>
      </div>

      ${insightsBlock}

      <div class="mt-5 border-t border-slate-100 pt-5">
        <div class="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
          <p class="text-xs font-semibold uppercase tracking-wide text-slate-400">AI-drafted response <span class="normal-case text-slate-400">(${escapeHtml(responseTone)} tone)</span></p>
          <div class="flex shrink-0 gap-2">
            <button id="editResponseBtn" type="button" class="text-xs font-semibold text-violet-600 hover:text-violet-700">Edit Response</button>
            <button id="copyResponseBtn" type="button" class="text-xs font-semibold text-violet-600 hover:text-violet-700">Copy Response</button>
          </div>
        </div>
        <p class="mt-1 text-xs italic text-slate-400">Personalized to this review's sentiment and the specific details detected above -- not a generic template.</p>
        <p id="responseText" class="mt-2 rounded-2xl bg-slate-50 p-3.5 text-sm leading-relaxed text-slate-800">${escapeHtml(responseText)}</p>
        <textarea id="responseEditArea" class="mt-2 hidden w-full rounded-2xl border border-violet-200 p-3.5 text-sm leading-relaxed text-slate-800 outline-none" rows="3"></textarea>
      </div>

      <div class="mt-5 rounded-2xl border p-4 ${ACTION_CLASSES[action.tone]}">
        <p class="text-xs font-semibold uppercase tracking-wide opacity-80">Recommended action &middot; ${escapeHtml(action.label)}</p>
        <p class="mt-1 text-sm leading-relaxed">${escapeHtml(action.text)}</p>
      </div>
    </div>
  `;
  resultWrap.classList.remove("hidden");

  const responseTextEl = document.getElementById("responseText");
  const responseEditArea = document.getElementById("responseEditArea");
  const editBtn = document.getElementById("editResponseBtn");
  const copyBtn = document.getElementById("copyResponseBtn");

  editBtn.addEventListener("click", () => {
    const editing = !responseEditArea.classList.contains("hidden");
    if (editing) {
      responseTextEl.textContent = responseEditArea.value.trim() || responseTextEl.textContent;
      responseEditArea.classList.add("hidden");
      responseTextEl.classList.remove("hidden");
      editBtn.textContent = "Edit Response";
    } else {
      responseEditArea.value = responseTextEl.textContent;
      responseTextEl.classList.add("hidden");
      responseEditArea.classList.remove("hidden");
      responseEditArea.focus();
      editBtn.textContent = "Done Editing";
    }
  });

  copyBtn.addEventListener("click", async () => {
    const text = responseEditArea.classList.contains("hidden") ? responseTextEl.textContent : responseEditArea.value;
    try {
      await navigator.clipboard.writeText(text);
      const original = copyBtn.textContent;
      copyBtn.textContent = "Copied!";
      setTimeout(() => (copyBtn.textContent = original), 1500);
    } catch (err) {
      console.error("Copy failed:", err);
    }
  });
}

const ANALYSIS_STEPS = [
  "Reading the review…",
  "Detecting sentiment & intent…",
  "Identifying key issues…",
  "Drafting your response…",
];

let statusInterval = null;

function startAnalyzingStatus() {
  let i = 0;
  analyzeStatus.textContent = ANALYSIS_STEPS[0];
  analyzeStatus.classList.remove("hidden");
  statusInterval = setInterval(() => {
    i = (i + 1) % ANALYSIS_STEPS.length;
    analyzeStatus.textContent = ANALYSIS_STEPS[i];
  }, 900);
}

function stopAnalyzingStatus() {
  if (statusInterval) clearInterval(statusInterval);
  statusInterval = null;
  analyzeStatus.classList.add("hidden");
}

analyzeBtn.addEventListener("click", async () => {
  const text = reviewInput.value.trim();
  if (!text) {
    reviewError.classList.remove("hidden");
    reviewInput.focus();
    return;
  }
  reviewError.classList.add("hidden");

  analyzeBtn.disabled = true;
  analyzeBtn.textContent = "Analyzing...";
  resultWrap.classList.add("hidden");
  startAnalyzingStatus();

  try {
    const resp = await fetch(`${apiUrl}/api/agents/reviews/demo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ review_text: text, tone: "professional" }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || `Request failed (${resp.status})`);
    renderResult(text, data, data.response_text, data.response_tone);
  } catch (err) {
    console.error("Review demo error:", err);
    resultWrap.innerHTML = `<div class="rounded-3xl border border-red-100 bg-red-50 p-6 text-sm text-red-700">Sorry, something went wrong reaching the server. Please try again.</div>`;
    resultWrap.classList.remove("hidden");
  } finally {
    stopAnalyzingStatus();
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = "Analyze Review & Draft Response";
  }
});
