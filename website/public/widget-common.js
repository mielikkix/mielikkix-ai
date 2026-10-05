// Small helpers shared by every website/public/*.js conversation widget
// (voice-receptionist.js, booking-assistant.js, support-triage.js,
// support-chat-widget.js). Exposed as window.MlxWidget rather than an ES
// module, since these are all loaded as plain <script src> tags (not
// type="module") for the same Content-Security-Policy reason each of
// those files' own comment explains -- a <script type="module"> import
// graph would work too, but every file already assumes a global scope.
//
// Loaded via its own <script src="/widget-common.js"> tag, before the
// page-specific script that uses it.
window.MlxWidget = (function () {
  async function postJSON(apiUrl, path, body) {
    const resp = await fetch(`${apiUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || `${path} returned ${resp.status}`);
    return data;
  }

  // The site language: "no" on a /no/ page or once Norsk was chosen (same
  // localStorage key translationService.ts uses), else "en". Every demo
  // script picks its own strings with this (QA 2026-10-05, BUG-05..09).
  function lang() {
    if (location.pathname === "/no" || location.pathname.startsWith("/no/")) return "no";
    try {
      return localStorage.getItem("mielikkix:lang") === "no" ? "no" : "en";
    } catch (_e) {
      return "en";
    }
  }

  // "tir. 13. okt., 09:00" in Norwegian, "Tue, Oct 13, 9:00 AM" in English.
  function formatSlot(startISO) {
    const no = lang() === "no";
    return new Date(startISO).toLocaleString(no ? "nb-NO" : "en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: no ? "2-digit" : "numeric",
      minute: "2-digit",
    });
  }

  return { postJSON, formatSlot, lang };
})();
