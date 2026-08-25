// The "Book a Free Demo" lead-capture form's submit handler. Kept as an
// external file (rather than an inline/bundled <script> in demo.astro) so
// it isn't blocked by the site's Content-Security-Policy, which has no
// 'unsafe-inline' for script-src -- see i18n-guard.js for the same
// pattern. apiUrl/businessId come from this script tag's own data-*
// attributes (set at build time by demo.astro from PUBLIC_API_URL /
// PUBLIC_MIELIKKIX_BUSINESS_ID) rather than Astro's define:vars, since
// define:vars only works on is:inline scripts, which is exactly what
// triggers the CSP block in the first place.
const { apiUrl, businessId } = document.currentScript.dataset;

const form = document.getElementById("demo-form");
const status = document.getElementById("demo-form-status");
const errorEl = document.getElementById("demo-form-error");
const submitButton = form?.querySelector('button[type="submit"]');

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorEl?.classList.add("hidden");

  const data = new FormData(form);
  const businessName = (data.get("business") || "").toString().trim();
  const website = (data.get("website") || "").toString().trim();
  const note = (data.get("message") || "").toString().trim();
  const messageParts = [`Business: ${businessName}`];
  if (website) messageParts.push(`Website: ${website}`);
  if (note) messageParts.push(note);

  if (submitButton) submitButton.disabled = true;
  try {
    const res = await fetch(`${apiUrl}/api/leads`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        business_id: businessId,
        name: data.get("name"),
        email: data.get("email"),
        phone: data.get("phone") || undefined,
        message: messageParts.join("\n"),
      }),
    });

    if (!res.ok) {
      throw new Error("request failed");
    }

    form.reset();
    form.classList.add("hidden");
    if (status) {
      status.textContent = "Thanks! We'll be in touch within one business day to schedule your demo.";
      status.classList.remove("hidden");
    }
  } catch {
    if (errorEl) {
      errorEl.textContent = "Something went wrong sending your request — please try again, or email us directly.";
      errorEl.classList.remove("hidden");
    }
  } finally {
    if (submitButton) submitButton.disabled = false;
  }
});
