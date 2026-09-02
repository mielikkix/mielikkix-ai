// The /demo/seo-copywriter page's logic. External file (not an inline
// <script>) for the same Content-Security-Policy reason every other
// website/public/*.js file is -- see voice-receptionist.js's own comment
// on this.
const { apiUrl } = document.currentScript.dataset;

const nameInput = document.getElementById("nameInput");
const categoryInput = document.getElementById("categoryInput");
const descriptionInput = document.getElementById("descriptionInput");
const generateBtn = document.getElementById("generateBtn");
const resultWrap = document.getElementById("resultWrap");

document.querySelectorAll(".example-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    nameInput.value = btn.dataset.text;
    nameInput.focus();
  });
});

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function renderResult(data) {
  resultWrap.innerHTML = `
    <div class="rounded-3xl border border-slate-100 bg-white p-6 shadow-sm">
      <p class="text-sm font-semibold text-slate-700">Rewritten description</p>
      <p class="mt-2 rounded-2xl bg-slate-50 p-3.5 text-sm text-slate-800">${escapeHtml(data.description)}</p>
    </div>
    <div class="rounded-3xl border border-slate-100 bg-white p-6 shadow-sm">
      <p class="text-sm font-semibold text-slate-700">SEO title tag</p>
      <p class="mt-2 rounded-2xl bg-slate-50 p-3.5 text-sm text-slate-800">${escapeHtml(data.seo_title)}</p>
      <p class="mt-4 text-sm font-semibold text-slate-700">Meta description</p>
      <p class="mt-2 rounded-2xl bg-slate-50 p-3.5 text-sm text-slate-800">${escapeHtml(data.meta_description)}</p>
      <p class="mt-3 text-xs text-slate-400">A human always reviews a before/after diff and approves before anything like this overwrites live product copy.</p>
    </div>
  `;
  resultWrap.classList.remove("hidden");
}

generateBtn.addEventListener("click", async () => {
  const name = nameInput.value.trim();
  if (!name) {
    nameInput.focus();
    return;
  }

  generateBtn.disabled = true;
  generateBtn.textContent = "Generating...";
  resultWrap.classList.add("hidden");

  try {
    const resp = await fetch(`${apiUrl}/api/agents/seo/demo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        category: categoryInput.value.trim() || null,
        description: descriptionInput.value.trim() || null,
      }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || `Request failed (${resp.status})`);
    renderResult(data);
  } catch (err) {
    console.error("SEO Copywriter demo error:", err);
    resultWrap.innerHTML = `<div class="rounded-3xl border border-red-100 bg-red-50 p-6 text-sm text-red-700">Sorry, something went wrong reaching the server. Please try again.</div>`;
    resultWrap.classList.remove("hidden");
  } finally {
    generateBtn.disabled = false;
    generateBtn.textContent = "Generate SEO copy";
  }
});
